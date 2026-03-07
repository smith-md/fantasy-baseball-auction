"""
Canonical LeagueState schema (v2) as defined in the PRD.

This module implements the single source of truth for all draft state, including:
- Complete player pool (drafted and undrafted)
- Team rosters organized by position
- Aggregated team statistics
- Replacement-level baselines
- Draft events and metadata

Design Principles:
1. Single source of truth - all downstream calculations depend exclusively on LeagueState
2. Deterministic & replayable - replaying events yields identical state
3. ID-based, not name-based - internal references use IDs only
4. Explicit over implicit - derived values stored or easily derivable
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional
import json


@dataclass
class PlayerState:
    """
    Tracks availability and assignment for each player in the pool.

    Attributes:
        player_id: FanGraphs player ID
        player_name: Player name for human readability
        eligible_positions: List of positions player can fill
        drafted: Whether player has been drafted
        drafted_team_id: Team that drafted the player (None if undrafted)
        price: Auction price paid for player (None if undrafted)
    """
    player_id: str
    player_name: str
    eligible_positions: List[str]
    drafted: bool
    drafted_team_id: Optional[str] = None
    price: Optional[float] = None


@dataclass
class TeamStats:
    """
    Aggregated statistics for a team.

    Stores team-level stat totals used for projections and SGP.
    Rate stats (OBP, SLG, ERA, WHIP) are computed from numerators and denominators.

    Attributes:
        counting: Direct sum stats (R, RBI, SB, W_QS, SV_HLD, K)
        rate_numerators: Components for rate stat calculation
            - OBP_num: H + BB + HBP
            - SLG_num: Total Bases (TB)
            - ERA_num: Earned Runs (ER)
            - WHIP_num: H + BB
        rate_denominators: Denominators for rate stats
            - PA: Plate Appearances (for OBP)
            - AB: At Bats (for SLG)
            - IP: Innings Pitched (for ERA and WHIP)
    """
    counting: Dict[str, float] = field(default_factory=dict)
    rate_numerators: Dict[str, float] = field(default_factory=dict)
    rate_denominators: Dict[str, float] = field(default_factory=dict)

    def calculate_rate_stats(self) -> Dict[str, float]:
        """
        Calculate rate stats from numerators and denominators.

        Returns:
            Dict with OBP, SLG, ERA, WHIP values
        """
        rate_stats = {}

        # OBP = (H + BB + HBP) / PA
        if self.rate_denominators.get('PA', 0) > 0:
            rate_stats['OBP'] = self.rate_numerators.get('OBP_num', 0) / self.rate_denominators['PA']
        else:
            rate_stats['OBP'] = 0.0

        # SLG = TB / AB
        if self.rate_denominators.get('AB', 0) > 0:
            rate_stats['SLG'] = self.rate_numerators.get('SLG_num', 0) / self.rate_denominators['AB']
        else:
            rate_stats['SLG'] = 0.0

        # ERA = (ER / IP) * 9
        if self.rate_denominators.get('IP', 0) > 0:
            rate_stats['ERA'] = (self.rate_numerators.get('ERA_num', 0) / self.rate_denominators['IP']) * 9
        else:
            rate_stats['ERA'] = 0.0

        # WHIP = (H + BB) / IP
        if self.rate_denominators.get('IP', 0) > 0:
            rate_stats['WHIP'] = self.rate_numerators.get('WHIP_num', 0) / self.rate_denominators['IP']
        else:
            rate_stats['WHIP'] = 0.0

        return rate_stats


@dataclass
class TeamState:
    """
    Current state of a single team.

    Attributes:
        team_id: Unique team identifier
        team_name: Manager/team name
        budget_total: Total budget at draft start
        budget_spent: Dollars spent so far
        roster: Position-based roster structure (position -> [player_ids])
        open_slots: Remaining slots per position
        stats: Aggregated team statistics
    """
    team_id: str
    team_name: str
    budget_total: float
    budget_spent: float
    roster: Dict[str, List[str]]  # position -> [player_ids]
    open_slots: Dict[str, int]    # position -> remaining count
    stats: TeamStats

    def __post_init__(self):
        from .. import config
        for pos, count in self.open_slots.items():
            max_per_team = config.ROSTER_SLOTS_PER_TEAM.get(pos, 0)
            if count > max_per_team:
                raise ValueError(
                    f"TeamState {self.team_id}: open_slots[{pos}]={count} "
                    f"exceeds per-team max {max_per_team}"
                )

    @property
    def budget_remaining(self) -> float:
        """Calculate remaining budget."""
        return self.budget_total - self.budget_spent

    @property
    def total_roster_size(self) -> int:
        """Calculate total number of players on roster."""
        return sum(len(player_ids) for player_ids in self.roster.values())

    @property
    def total_open_slots(self) -> int:
        """Calculate total remaining roster slots."""
        return sum(self.open_slots.values())


@dataclass
class ReplacementProfile:
    """
    Replacement-level statistics for a position.

    Mirrors TeamStats structure for consistency.

    Attributes:
        counting: Counting stats at replacement level
        rate_numerators: Rate stat components
        rate_denominators: Rate stat denominators
    """
    counting: Dict[str, float] = field(default_factory=dict)
    rate_numerators: Dict[str, float] = field(default_factory=dict)
    rate_denominators: Dict[str, float] = field(default_factory=dict)


@dataclass
class ReplacementState:
    """
    Replacement-level profiles by position.

    Holds replacement-level profiles derived from the remaining player pool.

    Attributes:
        by_position: Mapping of position to replacement profile
    """
    by_position: Dict[str, ReplacementProfile] = field(default_factory=dict)


@dataclass
class DraftEvent:
    """
    Represents a single draft pick in an auction draft.

    Extended from v1 with assigned_position tracking for position-based rosters.

    Attributes:
        pick_number: Overall pick number (0 for keepers, 1-288 for draft)
        player_id: FanGraphs player ID
        player_name: Player name for human readability
        team_id: Team that drafted the player
        price: Auction price paid ($)
        timestamp: When the pick occurred
        assigned_position: Position player was assigned to in roster (NEW in v2)
    """
    pick_number: int
    player_id: str
    player_name: str
    team_id: str
    price: float
    timestamp: datetime
    assigned_position: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'pick_number': self.pick_number,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'team_id': self.team_id,
            'price': self.price,
            'timestamp': self.timestamp.isoformat(),
            'assigned_position': self.assigned_position
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DraftEvent':
        """Create DraftEvent from dictionary (JSON deserialization)."""
        return cls(
            pick_number=data['pick_number'],
            player_id=data['player_id'],
            player_name=data['player_name'],
            team_id=data['team_id'],
            price=data['price'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            assigned_position=data.get('assigned_position')
        )


@dataclass
class DraftState:
    """
    Tracks draft progression and ingestion state.

    Attributes:
        active: Whether draft is currently in progress
        last_processed_pick: Highest pick number processed
        events: All draft events (including keepers as pick_number=0)
    """
    active: bool
    last_processed_pick: int
    events: List[DraftEvent] = field(default_factory=list)


@dataclass
class Metadata:
    """
    Metadata for auditing and debugging.

    Attributes:
        last_updated: Timestamp of last state update
        source: Data source (e.g., 'fantrax', 'manual')
        notes: Optional notes or comments
    """
    last_updated: datetime
    source: str
    notes: Optional[str] = None


@dataclass
class LeagueState:
    """
    Complete state of the fantasy league.

    This is the canonical source of truth for all draft state.
    All valuation outputs must be deterministic given a LeagueState snapshot.

    Attributes:
        league_id: Unique league identifier
        teams: Mapping of team_id to TeamState
        players: Mapping of player_id to PlayerState (complete pool)
        draft: Draft progression state
        replacement: Replacement-level baselines
        metadata: Audit metadata
    """
    league_id: str
    teams: Dict[str, TeamState]
    players: Dict[str, PlayerState]
    draft: DraftState
    replacement: ReplacementState
    metadata: Metadata

    def validate(self) -> None:
        """
        Validate league state consistency.

        Raises:
            ValueError: If state violates any invariants
        """
        # Invariant 1: Budget consistency
        for team_id, team in self.teams.items():
            if team.budget_spent < 0:
                raise ValueError(f"Team {team_id} has negative budget_spent: {team.budget_spent}")
            if team.budget_spent > team.budget_total:
                raise ValueError(
                    f"Team {team_id} overspent: ${team.budget_spent} > ${team.budget_total}"
                )

        # Invariant 2: Roster consistency - all player_ids in rosters must exist in players dict
        for team_id, team in self.teams.items():
            for position, player_ids in team.roster.items():
                for player_id in player_ids:
                    if player_id not in self.players:
                        raise ValueError(
                            f"Team {team_id} roster has unknown player_id: {player_id}"
                        )

        # Invariant 3: Draft status consistency - players marked as drafted must be in team rosters
        drafted_in_rosters = set()
        for team in self.teams.values():
            for position, player_ids in team.roster.items():
                drafted_in_rosters.update(player_ids)

        drafted_in_players = {
            player_id for player_id, player in self.players.items() if player.drafted
        }

        if drafted_in_rosters != drafted_in_players:
            extra_in_rosters = drafted_in_rosters - drafted_in_players
            extra_in_players = drafted_in_players - drafted_in_rosters

            error_parts = []
            if extra_in_rosters:
                error_parts.append(f"In rosters but not marked drafted: {extra_in_rosters}")
            if extra_in_players:
                error_parts.append(f"Marked drafted but not in rosters: {extra_in_players}")

            raise ValueError("Draft status mismatch: " + "; ".join(error_parts))

        # Invariant 4: Roster size consistency - check open_slots calculations
        from .. import config  # Import here to avoid circular dependency

        for team_id, team in self.teams.items():
            for position, max_slots in config.ROSTER_SLOTS_PER_TEAM.items():
                filled_slots = len(team.roster.get(position, []))
                open_slots = team.open_slots.get(position, 0)

                if filled_slots + open_slots != max_slots:
                    raise ValueError(
                        f"Team {team_id} position {position}: "
                        f"{filled_slots} filled + {open_slots} open != {max_slots} total"
                    )

        # Invariant 5: Player team assignment consistency
        for player_id, player in self.players.items():
            if player.drafted:
                if not player.drafted_team_id:
                    raise ValueError(f"Player {player_id} marked drafted but no team_id")
                if player.price is None:
                    raise ValueError(f"Player {player_id} drafted but no price")
                if player.drafted_team_id not in self.teams:
                    raise ValueError(
                        f"Player {player_id} assigned to unknown team: {player.drafted_team_id}"
                    )
            else:
                if player.drafted_team_id is not None:
                    raise ValueError(
                        f"Player {player_id} not drafted but has team_id: {player.drafted_team_id}"
                    )
                if player.price is not None:
                    raise ValueError(f"Player {player_id} not drafted but has price: {player.price}")

    def total_picks(self) -> int:
        """Count total picks made across all teams."""
        return sum(team.total_roster_size for team in self.teams.values())

    def to_dict(self) -> dict:
        """
        Serialize to dictionary for JSON storage.

        Returns:
            Dictionary with schema_version tag for migration detection
        """
        return {
            'schema_version': '2.0',
            'league_id': self.league_id,
            'teams': {
                team_id: {
                    'team_id': team.team_id,
                    'team_name': team.team_name,
                    'budget_total': team.budget_total,
                    'budget_spent': team.budget_spent,
                    'roster': team.roster,
                    'open_slots': team.open_slots,
                    'stats': {
                        'counting': team.stats.counting,
                        'rate_numerators': team.stats.rate_numerators,
                        'rate_denominators': team.stats.rate_denominators
                    }
                }
                for team_id, team in self.teams.items()
            },
            'players': {
                player_id: asdict(player)
                for player_id, player in self.players.items()
            },
            'draft': {
                'active': self.draft.active,
                'last_processed_pick': self.draft.last_processed_pick,
                'events': [event.to_dict() for event in self.draft.events]
            },
            'replacement': {
                'by_position': {
                    pos: asdict(profile)
                    for pos, profile in self.replacement.by_position.items()
                }
            },
            'metadata': {
                'last_updated': self.metadata.last_updated.isoformat(),
                'source': self.metadata.source,
                'notes': self.metadata.notes
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LeagueState':
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict() (must be v2 schema)

        Returns:
            LeagueState instance

        Raises:
            ValueError: If schema version is not 2.0
        """
        schema_version = data.get('schema_version')
        if schema_version != '2.0':
            raise ValueError(
                f"Cannot deserialize schema version {schema_version}. "
                "Use CheckpointMigrator for v1 checkpoints."
            )

        # Deserialize teams
        teams = {}
        for team_id, team_data in data['teams'].items():
            teams[team_id] = TeamState(
                team_id=team_data['team_id'],
                team_name=team_data['team_name'],
                budget_total=team_data['budget_total'],
                budget_spent=team_data['budget_spent'],
                roster=team_data['roster'],
                open_slots=team_data['open_slots'],
                stats=TeamStats(
                    counting=team_data['stats']['counting'],
                    rate_numerators=team_data['stats']['rate_numerators'],
                    rate_denominators=team_data['stats']['rate_denominators']
                )
            )

        # Deserialize players
        players = {}
        for player_id, player_data in data['players'].items():
            players[player_id] = PlayerState(**player_data)

        # Deserialize draft
        draft = DraftState(
            active=data['draft']['active'],
            last_processed_pick=data['draft']['last_processed_pick'],
            events=[DraftEvent.from_dict(e) for e in data['draft']['events']]
        )

        # Deserialize replacement
        replacement = ReplacementState(
            by_position={
                pos: ReplacementProfile(**profile_data)
                for pos, profile_data in data['replacement']['by_position'].items()
            }
        )

        # Deserialize metadata
        metadata = Metadata(
            last_updated=datetime.fromisoformat(data['metadata']['last_updated']),
            source=data['metadata']['source'],
            notes=data['metadata'].get('notes')
        )

        return cls(
            league_id=data['league_id'],
            teams=teams,
            players=players,
            draft=draft,
            replacement=replacement,
            metadata=metadata
        )

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'LeagueState':
        """Create LeagueState from JSON string."""
        return cls.from_dict(json.loads(json_str))


def create_initial_league_state_v2(
    league_id: str,
    players: Dict[str, PlayerState],
    num_teams: int = 12,
    budget_per_team: float = 500.0,
    team_names: Optional[Dict[str, str]] = None
) -> LeagueState:
    """
    Create an initial league state at the start of the draft.

    Args:
        league_id: Unique league identifier
        players: Complete player pool (all undrafted)
        num_teams: Number of teams in the league
        budget_per_team: Budget per team in dollars
        team_names: Optional mapping of team_id to team_name

    Returns:
        LeagueState initialized for draft start with v2 schema
    """
    from .. import config  # Import here to avoid circular dependency

    teams = {}

    # Use actual team IDs/names from Fantrax if provided, otherwise generate defaults
    if team_names:
        team_entries = [(tid, name) for tid, name in team_names.items()]
    else:
        team_entries = [(f"team_{i:02d}", f"Team {i}") for i in range(1, num_teams + 1)]

    for team_id, team_name in team_entries:
        team_budget = config.TEAM_BUDGETS.get(team_id, budget_per_team)
        teams[team_id] = TeamState(
            team_id=team_id,
            team_name=team_name,
            budget_total=team_budget,
            budget_spent=0.0,
            roster={pos: [] for pos in config.ROSTER_SLOTS_PER_TEAM.keys()},
            open_slots=config.ROSTER_SLOTS_PER_TEAM.copy(),
            stats=TeamStats(
                counting={cat: 0.0 for cat in config.HITTER_CATEGORIES + config.PITCHER_CATEGORIES},
                rate_numerators={},
                rate_denominators={}
            )
        )

    state = LeagueState(
        league_id=league_id,
        teams=teams,
        players=players,
        draft=DraftState(active=True, last_processed_pick=0, events=[]),
        replacement=ReplacementState(by_position={}),
        metadata=Metadata(
            last_updated=datetime.now(),
            source='initialization',
            notes='Initial league state created'
        )
    )

    # Validate initial state to catch initialization bugs immediately
    state.validate()

    return state
