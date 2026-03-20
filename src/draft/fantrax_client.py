"""
Fantrax API client for polling draft transactions.

Integrates with Fantrax endpoints:
- getDraftResults: Primary source for draft picks
- getLeagueInfo: Team and player mappings (fetch once, cache)
"""

import logging
import time
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime
from fuzzywuzzy import fuzz, process

from .league_schema import DraftEvent

logger = logging.getLogger(__name__)


class FantraxClient:
    """Client for polling Fantrax draft API."""

    def __init__(
        self,
        league_id: str,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None
    ):
        """
        Initialize Fantrax client.

        Args:
            league_id: Fantrax league identifier
            api_key: API authentication key (can also use session cookies)
            cache_dir: Directory for caching mappings (default: data/mappings)
        """
        self.base_url = "https://www.fantrax.com/fxea/general"
        self.league_id = league_id
        self.api_key = api_key

        # Caching
        self.cache_dir = cache_dir or Path('data/mappings')
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Mappings (loaded from getLeagueInfo)
        self.team_id_to_name: Dict[str, str] = {}
        self.fantrax_player_to_name: Dict[str, str] = {}
        self._mappings_loaded = False

        # Session for connection pooling
        self.session = requests.Session()
        if self.api_key:
            self.session.headers['Authorization'] = f'Bearer {self.api_key}'

    def _deprecated_fetch_draft_results(self) -> Dict:
        """
        Deprecated: use roster-based polling instead (fetch_rosters + roster_diff_to_events).

        Poll Fantrax API for current draft state.

        Returns:
            Raw JSON response from Fantrax getDraftResults endpoint

        Raises:
            requests.RequestException: On API failure
        """
        endpoint = f"{self.base_url}/getDraftResults"
        params = {'leagueId': self.league_id}

        try:
            response = self._make_request(endpoint, params)
            logger.debug(f"Fetched draft results: {len(response.get('draftPicks', []))} picks")
            return response
        except requests.RequestException as e:
            logger.error(f"Failed to fetch draft results: {e}")
            raise

    def fetch_league_info(self) -> Dict:
        """
        Fetch team and player mappings from Fantrax.

        Returns:
            Raw JSON response from Fantrax getLeagueInfo endpoint

        This should be called once at session start and cached.
        """
        endpoint = f"{self.base_url}/getLeagueInfo"
        params = {'leagueId': self.league_id}

        try:
            response = self._make_request(endpoint, params)
            logger.info("Fetched league info from Fantrax")
            return response
        except requests.RequestException as e:
            logger.error(f"Failed to fetch league info: {e}")
            raise
    def fetch_rosters(self) -> Dict:
        """
        Fetch all team rosters from Fantrax, including salary/contract data.

        Returns:
            Raw JSON response from Fantrax getTeamRosters endpoint
        """
        endpoint = f"{self.base_url}/getTeamRosters"
        params = {'leagueId': self.league_id}

        try:
            response = self._make_request(endpoint, params)
            logger.info(f"Fetched team rosters from Fantrax")
            return response
        except requests.RequestException as e:
            logger.error(f"Failed to fetch team rosters: {e}")
            raise

    def load_player_id_map(self, force_refresh: bool = False) -> Dict[str, str]:
        """
        Download and cache the SFBB player ID cross-reference CSV.

        Returns a dict mapping Fantrax player ID -> player name.
        Cache is refreshed weekly.
        """
        import pandas as pd
        from .. import config

        cache_file = Path(config.PLAYERID_MAP_CACHE)
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Use cache if fresh (< 7 days old)
        if not force_refresh and cache_file.exists():
            age_days = (datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)).days
            if age_days < 7:
                try:
                    df = pd.read_csv(cache_file)
                    mapping = {
                        str(row['FANTRAXID']).strip().strip('*'): str(row['PLAYERNAME']).strip()
                        for _, row in df.iterrows()
                        if str(row.get('FANTRAXID', '')).strip().strip('*') not in ('', 'nan')
                        and str(row.get('PLAYERNAME', '')).strip() not in ('', 'nan')
                    }
                    logger.info(f"Loaded cached player ID map: {len(mapping)} entries")
                    return mapping
                except Exception as e:
                    logger.warning(f"Failed to load cached player ID map: {e}")

        # Download fresh copy
        logger.info("Downloading SFBB player ID map...")
        try:
            import io
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; fantasy-baseball-auction/1.0)'}
            resp = requests.get(config.PLAYERID_MAP_URL, headers=headers, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            df.to_csv(cache_file, index=False)
            mapping = {
                str(row['FANTRAXID']).strip(): str(row['PLAYERNAME']).strip()
                for _, row in df.iterrows()
                if str(row.get('FANTRAXID', '')).strip() not in ('', 'nan')
                and str(row.get('PLAYERNAME', '')).strip() not in ('', 'nan')
            }
            logger.info(f"Downloaded player ID map: {len(mapping)} entries -> {cache_file}")
            return mapping
        except Exception as e:
            logger.error(f"Failed to download player ID map: {e}")
            return {}

    def parse_rosters_to_keepers(
        self,
        raw_data: Dict,
        fangraphs_players_df=None
    ) -> List[Dict]:
        """
        Parse getTeamRosters response into keeper records.

        Each record contains:
            player_id   - FanGraphs player ID (fuzzy matched from name)
            player_name - Player name from Fantrax
            team_id     - Fantrax team ID
            team_name   - Team name
            keeper_salary - Salary from Fantrax contract data

        Args:
            raw_data: Raw JSON from getTeamRosters endpoint
            fangraphs_players_df: FanGraphs projections for player ID matching

        Returns:
            List of keeper dicts ready for KeeperInitializer
        """
        keepers = []

        # Log top-level keys to help diagnose unexpected formats
        logger.info(f"getTeamRosters response keys: {list(raw_data.keys())}")

        # Fantrax typically nests rosters under 'rosters' or 'teamRosters'
        roster_data = raw_data.get('rosters', raw_data.get('teamRosters', {}))

        if not roster_data:
            logger.warning(
                f"Could not find roster data in response. "
                f"Full response keys: {list(raw_data.keys())}. "
                f"Dumping raw response for inspection."
            )
            import json
            logger.warning(json.dumps(raw_data, indent=2)[:3000])
            return []

        # Load Fantrax ID -> player name map for roster items that lack a name field
        player_id_map = self.load_player_id_map()

        # Load manual minors overrides (players Fantrax marks ACTIVE but should be MINORS)
        # and roster overrides (players Fantrax marks MINORS but are on a roster)
        from .. import config
        import json as _json
        minors_overrides: set = set()
        roster_overrides: set = set()
        overrides_file = Path(config.DRAFT_BUDGETS_DIR) / f"minors_overrides_{config.LEAGUE_SEASON}.json"
        if overrides_file.exists():
            try:
                with open(overrides_file) as _f:
                    data = _json.load(_f)
                    minors_overrides = set(data.get('fantrax_ids', []))
                    roster_overrides = set(data.get('roster_overrides', {}).get('fantrax_ids', []))
                logger.info(f"Loaded {len(minors_overrides)} minors overrides, {len(roster_overrides)} roster overrides")
            except Exception as _e:
                logger.warning(f"Failed to load minors overrides: {_e}")

        for team_id, team_data in roster_data.items():
            team_name = self.team_id_to_name.get(team_id, team_data.get('name', team_id))

            # Players may be under 'rosterItems', 'players', or similar
            players = (
                team_data.get('rosterItems') or
                team_data.get('players') or
                team_data.get('roster') or
                []
            )

            for player in players:
                fantrax_id = player.get('id', '')
                player_name = (
                    player.get('name') or
                    player.get('playerName') or
                    player_id_map.get(fantrax_id, '')
                )
                salary = player.get('salary', player.get('contractSalary', player.get('cost', 0)))

                if not player_name:
                    continue

                # Skip minor league players — they don't count against draft dollars
                # Exception: roster_overrides are MINORS-status players actually on a roster
                status = player.get('status', '')
                is_roster_override = fantrax_id in roster_overrides
                if (status == 'MINORS' or fantrax_id in minors_overrides) and not is_roster_override:
                    logger.debug(f"Skipping {player_name} (minor league)")
                    continue

                # Only include players with a non-zero salary (actual keepers)
                # Roster overrides may have $0 salary (stashed on MINORS reserve)
                if not is_roster_override and (not salary or salary == 0):
                    logger.debug(f"Skipping {player_name} (no salary)")
                    continue

                # Fuzzy match to FanGraphs player ID
                fangraphs_id = self._match_to_fangraphs(player_name, fangraphs_players_df)

                keepers.append({
                    'player_id': fangraphs_id,
                    'player_name': player_name,
                    'team_id': team_id,
                    'team_name': team_name,
                    'keeper_salary': float(salary),
                    'fantrax_position': player.get('position', ''),
                    'fantrax_id': fantrax_id,
                })

        logger.info(f"Parsed {len(keepers)} keepers from Fantrax rosters")
        return keepers

    def roster_diff_to_events(
        self,
        raw_data: Dict,
        known_fantrax_ids: Set[str],
        fangraphs_players_df=None,
        pick_counter_start: int = 1
    ) -> Tuple[List[DraftEvent], Set[str]]:
        """
        Diff current Fantrax rosters against a known snapshot to detect new picks.

        Args:
            raw_data: Raw JSON from getTeamRosters endpoint
            known_fantrax_ids: Set of Fantrax player IDs already accounted for
            fangraphs_players_df: FanGraphs projections for player ID matching
            pick_counter_start: Pick number to assign to the first new event

        Returns:
            Tuple of (new_events, updated_known_fantrax_ids) where
            updated_known_fantrax_ids contains ALL IDs seen in this poll.
        """
        from .. import config
        import json as _json

        roster_data = raw_data.get('rosters', raw_data.get('teamRosters', {}))
        if not roster_data:
            logger.warning("roster_diff_to_events: no roster data found in response")
            return [], known_fantrax_ids

        player_id_map = self.load_player_id_map()

        minors_overrides: set = set()
        roster_overrides: set = set()
        overrides_file = Path(config.DRAFT_BUDGETS_DIR) / f"minors_overrides_{config.LEAGUE_SEASON}.json"
        if overrides_file.exists():
            try:
                with open(overrides_file) as _f:
                    data = _json.load(_f)
                    minors_overrides = set(data.get('fantrax_ids', []))
                    roster_overrides = set(data.get('roster_overrides', {}).get('fantrax_ids', []))
            except Exception as _e:
                logger.warning(f"Failed to load minors overrides: {_e}")

        new_events: List[DraftEvent] = []
        all_seen_ids: Set[str] = set(known_fantrax_ids)
        pick_counter = pick_counter_start

        for team_id, team_data in roster_data.items():
            players = (
                team_data.get('rosterItems') or
                team_data.get('players') or
                team_data.get('roster') or
                []
            )

            for player in players:
                fantrax_id = player.get('id', '')
                if not fantrax_id:
                    continue

                # Track all seen IDs to keep snapshot current
                all_seen_ids.add(fantrax_id)

                # Skip if already known
                if fantrax_id in known_fantrax_ids:
                    continue

                player_name = (
                    player.get('name') or
                    player.get('playerName') or
                    player_id_map.get(fantrax_id, '')
                )
                if not player_name:
                    logger.debug(f"roster_diff_to_events: no name for new fantrax_id {fantrax_id}, skipping")
                    continue

                # Skip minors (but not roster overrides — those are stashed on MINORS reserve)
                status = player.get('status', '')
                if (status == 'MINORS' or fantrax_id in minors_overrides) and fantrax_id not in roster_overrides:
                    logger.debug(f"Skipping new player {player_name} (minor league)")
                    continue

                salary = player.get('salary', player.get('contractSalary', player.get('cost', 0)))
                price = float(salary) if salary else float(config.MINIMUM_BID)
                if price == 0:
                    price = float(config.MINIMUM_BID)

                fangraphs_id = self._match_to_fangraphs(player_name, fangraphs_players_df)
                team_name = self.team_id_to_name.get(team_id, team_id)
                fantrax_pos = player.get('position', '')

                event = DraftEvent(
                    pick_number=pick_counter,
                    player_id=fangraphs_id,
                    player_name=player_name,
                    team_id=team_id,
                    price=price,
                    timestamp=datetime.now(),
                )
                new_events.append(event)
                logger.info(
                    f"New pick detected: {player_name} -> {team_name} (${price:.0f}, pick #{pick_counter})"
                )
                pick_counter += 1

        return new_events, all_seen_ids

    def load_mappings(self, force_refresh: bool = False) -> None:
        """
        Load team and player mappings from cache or Fantrax.

        Args:
            force_refresh: If True, re-fetch from Fantrax even if cache exists

        This populates:
        - self.team_id_to_name: Map Fantrax team IDs to manager/team names
        - self.fantrax_player_to_name: Map Fantrax player IDs to player names
        """
        cache_file = self.cache_dir / f"fantrax_mappings_{self.league_id}.json"

        # Try to load from cache
        if not force_refresh and cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                self.team_id_to_name = cached_data.get('teams', {})
                self.fantrax_player_to_name = cached_data.get('players', {})
                self._mappings_loaded = True

                logger.info(
                    f"Loaded cached mappings: {len(self.team_id_to_name)} teams, "
                    f"{len(self.fantrax_player_to_name)} players"
                )
                return
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load cached mappings: {e}, will re-fetch")

        # Fetch from Fantrax
        league_info = self.fetch_league_info()

        # Parse team mappings
        # teamInfo is a dict keyed by team ID with 'name' and 'id' fields
        team_info = league_info.get('teamInfo', {})
        if team_info and isinstance(team_info, dict):
            self.team_id_to_name = {
                tid: info.get('name', f"Team {tid}")
                for tid, info in team_info.items()
            }
        else:
            # Fallback: try legacy format
            teams = league_info.get('teams', [])
            self.team_id_to_name = {
                team['teamId']: team.get('teamName', team.get('ownerName', f"Team {team['teamId']}"))
                for team in teams
            }

        # Parse player mappings
        # playerInfo is a dict keyed by player ID with position/status info
        player_info = league_info.get('playerInfo', {})
        if player_info and isinstance(player_info, dict):
            self.fantrax_player_to_name = {}  # playerInfo doesn't include names
        else:
            players = league_info.get('players', [])
            self.fantrax_player_to_name = {
                player['playerId']: player['playerName']
                for player in players
            }

        self._mappings_loaded = True

        # Cache to disk
        cache_data = {
            'teams': self.team_id_to_name,
            'players': self.fantrax_player_to_name,
            'cached_at': datetime.now().isoformat(),
            'league_id': self.league_id
        }

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)

        logger.info(
            f"Loaded and cached mappings: {len(self.team_id_to_name)} teams, "
            f"{len(self.fantrax_player_to_name)} players -> {cache_file}"
        )

    def _deprecated_normalize_to_events(
        self,
        raw_data: Dict,
        fangraphs_players_df=None
    ) -> List[DraftEvent]:
        """
        Deprecated: use roster-based polling instead (fetch_rosters + roster_diff_to_events).

        Convert Fantrax draft results to DraftEvent objects.

        Args:
            raw_data: Raw JSON from getDraftResults endpoint
            fangraphs_players_df: Optional DataFrame with FanGraphs projections
                                  (used for fuzzy matching player_id)

        Returns:
            List of DraftEvents in chronological order

        The challenge: Fantrax uses different player IDs than FanGraphs.
        We use player names to fuzzy-match and find the FanGraphs player_id.
        """
        if not self._mappings_loaded:
            logger.warning("Mappings not loaded, calling load_mappings()")
            self.load_mappings()

        draft_picks = raw_data.get('draftPicks', [])
        events = []

        for pick_data in draft_picks:
            try:
                event = self._deprecated_parse_draft_pick(pick_data, fangraphs_players_df)
                events.append(event)
            except (KeyError, ValueError) as e:
                logger.error(f"Failed to parse draft pick: {e}\nData: {pick_data}")
                continue

        # Sort by pick number
        events.sort(key=lambda e: e.pick_number)

        logger.debug(f"Normalized {len(events)} draft picks to DraftEvent objects")
        return events

    def _deprecated_parse_draft_pick(
        self,
        pick_data: Dict,
        fangraphs_players_df=None
    ) -> DraftEvent:
        """
        Deprecated: use roster-based polling instead (fetch_rosters + roster_diff_to_events).

        Parse a single draft pick from Fantrax JSON.

        Args:
            pick_data: Single pick from Fantrax draftPicks array
            fangraphs_players_df: Optional FanGraphs projections for ID matching

        Returns:
            DraftEvent

        Raises:
            KeyError: If required fields missing
            ValueError: If data invalid
        """
        # Extract Fantrax data
        pick_number = pick_data['pick']
        fantrax_player_id = pick_data['playerId']
        fantrax_team_id = pick_data['teamId']
        price = int(pick_data['bid'])
        timestamp_str = pick_data.get('time', datetime.now().isoformat())

        # Get player name from mapping
        player_name = self.fantrax_player_to_name.get(
            fantrax_player_id,
            pick_data.get('playerName', 'Unknown Player')
        )

        # Map team ID to team name
        team_name = self.team_id_to_name.get(
            fantrax_team_id,
            fantrax_team_id  # Fallback to ID if name not found
        )

        # Try to find FanGraphs player_id via fuzzy matching
        fangraphs_player_id = self._match_to_fangraphs(
            player_name,
            fangraphs_players_df
        )

        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            timestamp = datetime.now()
            logger.warning(f"Invalid timestamp for pick {pick_number}, using current time")

        return DraftEvent(
            pick_number=pick_number,
            player_id=fangraphs_player_id,
            player_name=player_name,
            team_id=fantrax_team_id,  # Keep Fantrax team_id for consistency
            price=price,
            timestamp=timestamp
        )

    def _match_to_fangraphs(
        self,
        player_name: str,
        fangraphs_players_df=None
    ) -> str:
        """
        Match Fantrax player name to FanGraphs player_id via fuzzy matching.

        Args:
            player_name: Player name from Fantrax
            fangraphs_players_df: DataFrame with FanGraphs projections
                                  (must have 'player_name' and 'player_id' columns)

        Returns:
            FanGraphs player_id (or player_name as fallback if no match)
        """
        if fangraphs_players_df is None or len(fangraphs_players_df) == 0:
            logger.warning(f"No FanGraphs data for matching: {player_name}")
            return player_name  # Fallback to name

        if 'player_name' not in fangraphs_players_df.columns:
            logger.warning("FanGraphs DataFrame missing 'player_name' column")
            return player_name

        import unicodedata

        def _strip_accents(s) -> str:
            """Remove accent marks (e.g. Acuña -> Acuna) for fuzzy matching."""
            if not isinstance(s, str):
                return ''
            return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('ascii')

        # Normalize accents for matching (handles e.g. Acuña vs Acuna)
        normalized_query = _strip_accents(player_name)
        fg_names = fangraphs_players_df['player_name'].tolist()
        normalized_fg_names = [_strip_accents(n) for n in fg_names]

        # Try token_sort_ratio first, then token_set_ratio (handles Jr./Sr. suffix mismatches)
        best_score = 0
        best_norm_name = None
        for scorer in (fuzz.token_sort_ratio, fuzz.token_set_ratio):
            result = process.extractOne(normalized_query, normalized_fg_names, scorer=scorer)
            if result and result[1] > best_score:
                best_score = result[1]
                best_norm_name = result[0]

        if best_norm_name is None:
            logger.warning(f"No fuzzy match found for: {player_name}")
            return player_name

        # Map normalized name back to original FanGraphs name
        idx = normalized_fg_names.index(best_norm_name)
        matched_name = fg_names[idx]

        # Require high confidence (90%+)
        if best_score < 90:
            logger.warning(
                f"Low confidence match for '{player_name}' -> '{matched_name}' ({best_score}%)"
            )
            return player_name

        # Get FanGraphs player_id for matched name
        matched_row = fangraphs_players_df[
            fangraphs_players_df['player_name'] == matched_name
        ]

        if len(matched_row) == 0:
            logger.warning(f"Matched name '{matched_name}' not found in DataFrame")
            return player_name

        player_id = matched_row.iloc[0]['player_id']
        logger.debug(f"Matched: '{player_name}' -> '{matched_name}' (ID: {player_id}, {best_score}%)")

        return player_id

    def _make_request(
        self,
        endpoint: str,
        params: Dict,
        timeout: int = 10,
        max_retries: int = 3
    ) -> Dict:
        """
        Make HTTP request to Fantrax API with retries.

        Args:
            endpoint: Full URL endpoint
            params: Query parameters
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts on failure

        Returns:
            Parsed JSON response

        Raises:
            requests.RequestException: After all retries exhausted
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"GET {endpoint} (attempt {attempt}/{max_retries})")
                response = self.session.get(
                    endpoint,
                    params=params,
                    timeout=timeout
                )
                response.raise_for_status()

                # Log raw response for debugging
                logger.debug(f"Response status: {response.status_code}")

                return response.json()

            except requests.Timeout:
                logger.warning(f"Request timeout (attempt {attempt}/{max_retries})")
                if attempt == max_retries:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.RequestException as e:
                logger.error(f"Request failed (attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    raise
                time.sleep(2 ** attempt)

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()
