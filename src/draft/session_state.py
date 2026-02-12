"""
Runtime session control state for managing draft session lifecycle.

This module defines SessionState, which tracks the runtime state of a draft
session (active/paused/ended) separately from LeagueState (which tracks draft data).

SessionState is the control plane; LeagueState is the data plane.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import json


@dataclass
class SessionState:
    """
    Runtime session control state (separate from LeagueState).

    Tracks whether the polling loop should be active and provides metadata
    about the session for monitoring and debugging.

    Attributes:
        session_id: Unique session identifier (format: {league_id}_{timestamp})
        league_id: Fantrax league ID
        active: Whether session is running (False = ended permanently)
        paused: Whether polling is paused (True = active but not polling)

        started_at: When session started
        ended_at: When session ended (None if still active)
        last_poll_at: When last poll occurred (None if no polls yet)

        poll_interval_seconds: Seconds between Fantrax polls
        season: Projection season (e.g., 2026)
        num_teams: Number of teams in league

        total_polls: Count of polls executed
        total_picks_detected: Count of new picks detected across all polls
        last_valuation_time_seconds: Duration of last valuation recompute
    """
    session_id: str
    league_id: str
    active: bool
    paused: bool

    # Timestamps
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    last_poll_at: Optional[datetime] = None

    # Configuration
    poll_interval_seconds: int = 5
    season: int = 2026
    num_teams: int = 12

    # Performance tracking
    total_polls: int = 0
    total_picks_detected: int = 0
    last_valuation_time_seconds: float = 0.0

    def to_dict(self) -> dict:
        """
        Serialize to dictionary for JSON storage.

        Returns:
            Dictionary with schema_version tag for migration detection
        """
        return {
            'schema_version': '1.0',
            'session_id': self.session_id,
            'league_id': self.league_id,
            'active': self.active,
            'paused': self.paused,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'last_poll_at': self.last_poll_at.isoformat() if self.last_poll_at else None,
            'poll_interval_seconds': self.poll_interval_seconds,
            'season': self.season,
            'num_teams': self.num_teams,
            'total_polls': self.total_polls,
            'total_picks_detected': self.total_picks_detected,
            'last_valuation_time_seconds': self.last_valuation_time_seconds
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SessionState':
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary from to_dict() (must be v1.0 schema)

        Returns:
            SessionState instance

        Raises:
            ValueError: If schema version is not 1.0
        """
        schema_version = data.get('schema_version')
        if schema_version != '1.0':
            raise ValueError(
                f"Cannot deserialize schema version {schema_version}. "
                "Expected 1.0"
            )

        return cls(
            session_id=data['session_id'],
            league_id=data['league_id'],
            active=data['active'],
            paused=data['paused'],
            started_at=datetime.fromisoformat(data['started_at']) if data.get('started_at') else None,
            ended_at=datetime.fromisoformat(data['ended_at']) if data.get('ended_at') else None,
            last_poll_at=datetime.fromisoformat(data['last_poll_at']) if data.get('last_poll_at') else None,
            poll_interval_seconds=data['poll_interval_seconds'],
            season=data['season'],
            num_teams=data['num_teams'],
            total_polls=data.get('total_polls', 0),
            total_picks_detected=data.get('total_picks_detected', 0),
            last_valuation_time_seconds=data.get('last_valuation_time_seconds', 0.0)
        )

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'SessionState':
        """Create SessionState from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @property
    def is_polling(self) -> bool:
        """Check if session is actively polling (active and not paused)."""
        return self.active and not self.paused

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate session duration in seconds (None if not started)."""
        if not self.started_at:
            return None

        end_time = self.ended_at if self.ended_at else datetime.now()
        return (end_time - self.started_at).total_seconds()
