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
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from fuzzywuzzy import fuzz, process

from .draft_event import DraftEvent

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

    def fetch_draft_results(self) -> Dict:
        """
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
        teams = league_info.get('teams', [])
        self.team_id_to_name = {
            team['teamId']: team.get('teamName', team.get('ownerName', f"Team {team['teamId']}"))
            for team in teams
        }

        # Parse player mappings
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
            f"{len(self.fantrax_player_to_name)} players → {cache_file}"
        )

    def normalize_to_events(
        self,
        raw_data: Dict,
        fangraphs_players_df=None
    ) -> List[DraftEvent]:
        """
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
                event = self._parse_draft_pick(pick_data, fangraphs_players_df)
                events.append(event)
            except (KeyError, ValueError) as e:
                logger.error(f"Failed to parse draft pick: {e}\nData: {pick_data}")
                continue

        # Sort by pick number
        events.sort(key=lambda e: e.pick_number)

        logger.debug(f"Normalized {len(events)} draft picks to DraftEvent objects")
        return events

    def _parse_draft_pick(
        self,
        pick_data: Dict,
        fangraphs_players_df=None
    ) -> DraftEvent:
        """
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

        # Get list of FanGraphs player names
        fg_names = fangraphs_players_df['player_name'].tolist()

        # Fuzzy match (using token_sort_ratio for robustness to ordering)
        match_result = process.extractOne(
            player_name,
            fg_names,
            scorer=fuzz.token_sort_ratio
        )

        if match_result is None:
            logger.warning(f"No fuzzy match found for: {player_name}")
            return player_name

        matched_name, score = match_result[0], match_result[1]

        # Require high confidence (90%+)
        if score < 90:
            logger.warning(
                f"Low confidence match for '{player_name}' → '{matched_name}' ({score}%)"
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
        logger.debug(f"Matched: '{player_name}' → '{matched_name}' (ID: {player_id}, {score}%)")

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
