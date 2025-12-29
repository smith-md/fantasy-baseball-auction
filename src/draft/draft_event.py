"""
Core data structures for draft events and league state.

These dataclasses represent the state of a fantasy baseball auction draft,
including individual picks, team rosters, and overall league state.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Set, Optional
import json


@dataclass
class DraftEvent:
    """Represents a single draft pick in an auction draft."""

    pick_number: int          # Overall pick number (1-288 for 12 teams × 24 players)
    player_id: str            # FanGraphs player ID
    player_name: str          # Player name for human readability
    team_id: str              # Which team drafted the player
    price: int                # Auction price paid ($)
    timestamp: datetime       # When the pick occurred

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'pick_number': self.pick_number,
            'player_id': self.player_id,
            'player_name': self.player_name,
            'team_id': self.team_id,
            'price': self.price,
            'timestamp': self.timestamp.isoformat()
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
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> 'DraftEvent':
        """Create DraftEvent from JSON string."""
        return cls.from_dict(json.loads(json_str))


@dataclass
class TeamState:
    """Tracks a single team's draft state."""

    team_id: str                           # Unique team identifier
    team_name: str                         # Manager/team name
    budget_remaining: int = 500            # Starts at $500
    roster_spots_remaining: int = 24       # Starts at 24
    roster: List[DraftEvent] = field(default_factory=list)  # Players drafted

    def add_pick(self, event: DraftEvent) -> None:
        """
        Add a draft pick to this team.

        Args:
            event: DraftEvent to add

        Raises:
            ValueError: If budget or roster spots insufficient
        """
        if event.price > self.budget_remaining:
            raise ValueError(
                f"Insufficient budget: ${self.budget_remaining} < ${event.price}"
            )
        if self.roster_spots_remaining <= 0:
            raise ValueError("No roster spots remaining")

        self.roster.append(event)
        self.budget_remaining -= event.price
        self.roster_spots_remaining -= 1

    def total_spent(self) -> int:
        """Calculate total dollars spent so far."""
        return sum(pick.price for pick in self.roster)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'team_id': self.team_id,
            'team_name': self.team_name,
            'budget_remaining': self.budget_remaining,
            'roster_spots_remaining': self.roster_spots_remaining,
            'roster': [event.to_dict() for event in self.roster]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TeamState':
        """Create TeamState from dictionary."""
        roster = [DraftEvent.from_dict(e) for e in data.get('roster', [])]
        return cls(
            team_id=data['team_id'],
            team_name=data['team_name'],
            budget_remaining=data.get('budget_remaining', 500),
            roster_spots_remaining=data.get('roster_spots_remaining', 24),
            roster=roster
        )


@dataclass
class LeagueState:
    """Complete state of the auction draft."""

    teams: Dict[str, TeamState]                     # team_id -> TeamState
    drafted_players: Set[str] = field(default_factory=set)  # player_ids already drafted
    available_budget: int = 6000                    # Sum of all team budgets ($500 × 12)
    available_roster_spots: int = 288               # Sum of all roster spots (24 × 12)
    last_processed_pick: int = 0                    # Track progress through draft
    keeper_events: List[DraftEvent] = field(default_factory=list)  # Keepers as initial state

    def validate(self) -> None:
        """
        Validate league state consistency.

        Raises:
            ValueError: If state is inconsistent
        """
        # Validate budget tracking
        team_budgets = sum(t.budget_remaining for t in self.teams.values())
        if team_budgets != self.available_budget:
            raise ValueError(
                f"Budget mismatch: team budgets sum to ${team_budgets}, "
                f"but available_budget is ${self.available_budget}"
            )

        # Validate roster spot tracking
        team_spots = sum(t.roster_spots_remaining for t in self.teams.values())
        if team_spots != self.available_roster_spots:
            raise ValueError(
                f"Roster spot mismatch: team spots sum to {team_spots}, "
                f"but available_roster_spots is {self.available_roster_spots}"
            )

        # Validate drafted players set matches team rosters
        rostered_players = set()
        for team in self.teams.values():
            for pick in team.roster:
                if pick.player_id in rostered_players:
                    raise ValueError(
                        f"Player {pick.player_id} ({pick.player_name}) "
                        f"appears on multiple rosters"
                    )
                rostered_players.add(pick.player_id)

        if rostered_players != self.drafted_players:
            raise ValueError(
                "drafted_players set does not match rostered players"
            )

    def total_picks(self) -> int:
        """Count total picks made across all teams."""
        return sum(len(team.roster) for team in self.teams.values())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'teams': {tid: team.to_dict() for tid, team in self.teams.items()},
            'drafted_players': list(self.drafted_players),
            'available_budget': self.available_budget,
            'available_roster_spots': self.available_roster_spots,
            'last_processed_pick': self.last_processed_pick,
            'keeper_events': [event.to_dict() for event in self.keeper_events]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LeagueState':
        """Create LeagueState from dictionary."""
        teams = {
            tid: TeamState.from_dict(tdata)
            for tid, tdata in data['teams'].items()
        }
        keeper_events = [
            DraftEvent.from_dict(e)
            for e in data.get('keeper_events', [])
        ]
        return cls(
            teams=teams,
            drafted_players=set(data.get('drafted_players', [])),
            available_budget=data.get('available_budget', 6000),
            available_roster_spots=data.get('available_roster_spots', 288),
            last_processed_pick=data.get('last_processed_pick', 0),
            keeper_events=keeper_events
        )

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'LeagueState':
        """Create LeagueState from JSON string."""
        return cls.from_dict(json.loads(json_str))


def create_initial_league_state(
    num_teams: int = 12,
    budget_per_team: int = 500,
    roster_size: int = 24,
    team_names: Optional[Dict[str, str]] = None
) -> LeagueState:
    """
    Create an initial league state at the start of the draft.

    Args:
        num_teams: Number of teams in the league
        budget_per_team: Budget per team in dollars
        roster_size: Number of roster spots per team
        team_names: Optional mapping of team_id to team_name

    Returns:
        LeagueState initialized for draft start
    """
    teams = {}
    for i in range(1, num_teams + 1):
        team_id = f"team_{i:02d}"
        team_name = (team_names or {}).get(team_id, f"Team {i}")
        teams[team_id] = TeamState(
            team_id=team_id,
            team_name=team_name,
            budget_remaining=budget_per_team,
            roster_spots_remaining=roster_size
        )

    return LeagueState(
        teams=teams,
        drafted_players=set(),
        available_budget=num_teams * budget_per_team,
        available_roster_spots=num_teams * roster_size,
        last_processed_pick=0,
        keeper_events=[]
    )
