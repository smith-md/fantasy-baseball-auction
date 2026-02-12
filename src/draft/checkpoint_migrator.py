"""
Checkpoint migration from v1 to v2 schema.

Handles automatic detection and migration of old checkpoint format
to the new canonical LeagueState schema.
"""

import pandas as pd
from typing import Dict
import logging
from datetime import datetime

from .league_schema import (
    LeagueState,
    TeamState,
    TeamStats,
    DraftState,
    DraftEvent,
    ReplacementState,
    Metadata,
    create_initial_league_state_v2
)
from .player_pool_manager import PlayerPoolManager
from .. import config

logger = logging.getLogger(__name__)


class CheckpointMigrator:
    """Handles checkpoint version detection and migration."""

    @staticmethod
    def detect_version(checkpoint_data: dict) -> str:
        """
        Detect checkpoint schema version.

        Args:
            checkpoint_data: Checkpoint dictionary

        Returns:
            Version string ('1.0' or '2.0')
        """
        state = checkpoint_data.get('state', {})

        # Check for explicit schema_version field
        version = state.get('schema_version')
        if version:
            return version

        # Check for v2-specific structure (players dict)
        if 'players' in state:
            return '2.0'

        # Default to v1 if no version marker and no players dict
        return '1.0'

    @staticmethod
    def migrate_v1_to_v2(
        v1_checkpoint: dict,
        hitters_df: pd.DataFrame,
        pitchers_df: pd.DataFrame,
        league_id: str = 'default'
    ) -> LeagueState:
        """
        Convert v1 LeagueState to v2 schema.

        Strategy:
        1. Initialize full player pool from projections (all undrafted)
        2. Load v1 state (teams with List[DraftEvent] rosters)
        3. Extract events from v1 team rosters
        4. Create initial v2 LeagueState
        5. Replay events through DraftStateManagerV2
        6. Return reconstructed v2 LeagueState

        Args:
            v1_checkpoint: v1 checkpoint data
            hitters_df: Hitter projections for initializing player pool
            pitchers_df: Pitcher projections for initializing player pool
            league_id: League identifier

        Returns:
            Migrated LeagueState in v2 format

        Raises:
            ValueError: If migration fails
        """
        logger.info("Migrating v1 checkpoint to v2 schema...")

        v1_state = v1_checkpoint.get('state', {})

        # Step 1: Initialize player pool from projections
        logger.debug("Initializing player pool from projections...")
        player_pool_manager = PlayerPoolManager()
        players = player_pool_manager.initialize_player_pool(hitters_df, pitchers_df)

        # Step 2: Extract team information
        v1_teams = v1_state.get('teams', {})
        team_names = {
            team_id: team_data['team_name']
            for team_id, team_data in v1_teams.items()
        }

        # Step 3: Create initial v2 state with all players undrafted
        logger.debug("Creating initial v2 LeagueState...")
        v2_state = create_initial_league_state_v2(
            league_id=league_id,
            players=players,
            num_teams=len(v1_teams),
            budget_per_team=config.BUDGET_PER_TEAM,
            team_names=team_names
        )

        # Step 4: Extract all draft events from v1 rosters
        logger.debug("Extracting draft events from v1 rosters...")
        all_events = []

        for team_id, team_data in v1_teams.items():
            roster = team_data.get('roster', [])
            for event_data in roster:
                # v1 DraftEvent format
                event = DraftEvent(
                    pick_number=event_data.get('pick_number', 0),
                    player_id=event_data['player_id'],
                    player_name=event_data['player_name'],
                    team_id=team_data['team_id'],
                    price=event_data['price'],
                    timestamp=datetime.fromisoformat(event_data['timestamp']),
                    assigned_position=None  # Will be assigned during replay
                )
                all_events.append(event)

        # Include keeper events if present
        keeper_events = v1_state.get('keeper_events', [])
        for event_data in keeper_events:
            event = DraftEvent(
                pick_number=0,  # Keepers have pick_number=0
                player_id=event_data['player_id'],
                player_name=event_data['player_name'],
                team_id=event_data['team_id'],
                price=event_data['price'],
                timestamp=datetime.fromisoformat(event_data['timestamp']),
                assigned_position=None
            )
            all_events.append(event)

        # Sort events by pick_number
        all_events.sort(key=lambda e: e.pick_number)

        logger.info(f"Found {len(all_events)} events to replay")

        # Step 5: Replay events using DraftStateManagerV2
        # Import here to avoid circular dependency
        from .draft_state_manager_v2 import DraftStateManagerV2

        logger.debug("Replaying events to reconstruct state...")
        state_manager = DraftStateManagerV2(v2_state, hitters_df, pitchers_df)

        for event in all_events:
            try:
                state_manager.apply_event(event)
            except Exception as e:
                logger.error(
                    f"Failed to replay event {event.pick_number} "
                    f"({event.player_name} to {event.team_id}): {e}"
                )
                raise ValueError(f"Migration failed during event replay: {e}") from e

        # Update metadata
        state_manager.state.metadata.notes = (
            f"Migrated from v1 checkpoint at {datetime.now().isoformat()}"
        )

        logger.info("Migration completed successfully")

        return state_manager.state

    @staticmethod
    def needs_migration(checkpoint_data: dict) -> bool:
        """
        Check if checkpoint needs migration to v2.

        Args:
            checkpoint_data: Checkpoint dictionary

        Returns:
            True if migration needed, False if already v2
        """
        version = CheckpointMigrator.detect_version(checkpoint_data)
        return version == '1.0'

    @staticmethod
    def validate_v2_checkpoint(checkpoint_data: dict) -> None:
        """
        Validate that checkpoint is valid v2 format.

        Args:
            checkpoint_data: Checkpoint dictionary

        Raises:
            ValueError: If checkpoint is invalid
        """
        state = checkpoint_data.get('state', {})

        # Check schema version
        if state.get('schema_version') != '2.0':
            raise ValueError(
                f"Expected schema_version 2.0, got {state.get('schema_version')}"
            )

        # Check required top-level keys
        required_keys = ['league_id', 'teams', 'players', 'draft', 'replacement', 'metadata']
        missing = set(required_keys) - set(state.keys())
        if missing:
            raise ValueError(f"v2 checkpoint missing required keys: {missing}")

        # Validate players dict
        if not isinstance(state['players'], dict):
            raise ValueError("players must be a dict in v2 format")

        # Validate teams dict
        if not isinstance(state['teams'], dict):
            raise ValueError("teams must be a dict in v2 format")

        logger.debug("v2 checkpoint validation passed")

    @staticmethod
    def get_checkpoint_info(checkpoint_data: dict) -> Dict[str, any]:
        """
        Extract metadata about a checkpoint.

        Args:
            checkpoint_data: Checkpoint dictionary

        Returns:
            Dict with checkpoint info (version, event_count, timestamp, etc.)
        """
        version = CheckpointMigrator.detect_version(checkpoint_data)
        state = checkpoint_data.get('state', {})

        info = {
            'version': version,
            'event_count': checkpoint_data.get('event_count', 0),
            'checkpoint_time': checkpoint_data.get('checkpoint_time', 'unknown'),
        }

        if version == '2.0':
            info['total_picks'] = sum(
                len(player_ids)
                for team in state.get('teams', {}).values()
                for player_ids in team.get('roster', {}).values()
            )
            info['league_id'] = state.get('league_id', 'unknown')
            info['last_processed_pick'] = state.get('draft', {}).get('last_processed_pick', 0)
        elif version == '1.0':
            info['total_picks'] = sum(
                len(team.get('roster', []))
                for team in state.get('teams', {}).values()
            )
            info['last_processed_pick'] = state.get('last_processed_pick', 0)

        return info
