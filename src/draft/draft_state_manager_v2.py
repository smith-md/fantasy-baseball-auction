"""
Draft state management with v2 LeagueState schema.

Manages league state and applies draft events using the canonical
LeagueState schema defined in the PRD.

Key differences from v1 DraftStateManager:
- Position-based rosters (dict[position -> list[player_ids]])
- Complete player pool tracking (PlayerState dict)
- Real-time team stats aggregation
- Greedy position assignment during event application
- Gzip compressed checkpoints
"""

import logging
import json
import gzip
import pandas as pd
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .league_schema import LeagueState, DraftEvent
from .team_stats_aggregator import TeamStatsAggregator
from .position_assigner import PositionAssigner, determine_player_type
from .checkpoint_migrator import CheckpointMigrator

logger = logging.getLogger(__name__)


class DraftStateManagerV2:
    """Manages league state and applies draft events (v2 schema)."""

    def __init__(
        self,
        initial_state: LeagueState,
        hitters_df: pd.DataFrame,
        pitchers_df: pd.DataFrame
    ):
        """
        Initialize state manager with a v2 LeagueState.

        Args:
            initial_state: Starting league state (v2 schema)
            hitters_df: Hitter projections for stats aggregation
            pitchers_df: Pitcher projections for stats aggregation
        """
        self.state = initial_state
        self.event_history: List[DraftEvent] = []

        # Initialize stats aggregator
        self.stats_aggregator = TeamStatsAggregator(hitters_df, pitchers_df)

        # Initialize position assigner from current open_slots
        total_open_slots = {}
        for team in initial_state.teams.values():
            for pos, count in team.open_slots.items():
                total_open_slots[pos] = total_open_slots.get(pos, 0) + count

        self.position_assigner = PositionAssigner(total_open_slots)

        logger.debug(
            f"Initialized DraftStateManagerV2: "
            f"{len(initial_state.teams)} teams, "
            f"{len(initial_state.players)} players, "
            f"{initial_state.total_picks()} picks already made"
        )

    def apply_event(self, event: DraftEvent) -> None:
        """
        Apply a draft event to league state.

        Performs complete state updates:
        1. Validate player exists and not already drafted
        2. Assign position (greedy or use event.assigned_position if set)
        3. Update PlayerState (mark drafted, set team_id, price)
        4. Update TeamState (add to roster, update budget/slots, recalc stats)
        5. Update DraftState (append event, update last_processed_pick)
        6. Update Metadata (timestamp)
        7. Validate state consistency

        Args:
            event: DraftEvent to apply

        Raises:
            ValueError: If event is invalid or violates constraints
        """
        # 1. Validate player exists
        if event.player_id not in self.state.players:
            raise ValueError(f"Unknown player_id: {event.player_id}")

        player = self.state.players[event.player_id]

        # Validate player not already drafted
        if player.drafted:
            raise ValueError(
                f"Player {player.player_name} already drafted by {player.drafted_team_id}"
            )

        # Validate team exists
        if event.team_id not in self.state.teams:
            raise ValueError(f"Unknown team_id: {event.team_id}")

        team = self.state.teams[event.team_id]

        # 2. Assign position (if not already set)
        if not event.assigned_position:
            player_type = determine_player_type(player)
            event.assigned_position = self.position_assigner.assign_position(
                player, player_type
            )

        assigned_pos = event.assigned_position

        # Validate assigned position is valid for team
        if assigned_pos not in team.open_slots:
            raise ValueError(
                f"Invalid position {assigned_pos} for team {team.team_id}"
            )

        # Validate team has open slot at assigned position
        if team.open_slots[assigned_pos] <= 0:
            raise ValueError(
                f"Team {team.team_name} has no open slots at {assigned_pos}"
            )

        # Validate budget
        if event.price > team.budget_remaining:
            raise ValueError(
                f"Insufficient budget: team {team.team_name} has "
                f"${team.budget_remaining} but price is ${event.price}"
            )

        # 3. Update PlayerState
        player.drafted = True
        player.drafted_team_id = event.team_id
        player.price = event.price

        # 4. Update TeamState
        # Add player to roster
        team.roster[assigned_pos].append(event.player_id)

        # Update open slots
        team.open_slots[assigned_pos] -= 1

        # Update budget
        team.budget_spent += event.price

        # Recalculate team stats
        team.stats = self.stats_aggregator.aggregate_team_stats(
            team.roster,
            self.state.players
        )

        # 5. Update DraftState
        self.state.draft.events.append(event)
        self.state.draft.last_processed_pick = max(
            self.state.draft.last_processed_pick,
            event.pick_number
        )

        # 6. Update Metadata
        self.state.metadata.last_updated = datetime.now()

        # 7. Validate state consistency
        try:
            self.state.validate()
        except ValueError as e:
            logger.error(f"State validation failed after applying event: {e}")
            raise

        # Track in history
        self.event_history.append(event)

        logger.debug(
            f"Applied Pick {event.pick_number}: {event.player_name} → "
            f"{team.team_name} @ {assigned_pos} (${event.price}) | "
            f"{team.total_open_slots} slots, ${team.budget_remaining:.0f} remaining"
        )

    def apply_events(self, events: List[DraftEvent]) -> None:
        """
        Apply multiple events in chronological order.

        Args:
            events: List of DraftEvents to apply
        """
        for event in sorted(events, key=lambda e: e.pick_number):
            self.apply_event(event)

        if events:
            logger.info(
                f"Applied {len(events)} events | "
                f"Total picks: {self.state.total_picks()} | "
                f"Remaining: {sum(t.total_open_slots for t in self.state.teams.values())} slots"
            )

    def to_keeper_format(self) -> pd.DataFrame:
        """
        Convert current draft state to keeper format for pipeline integration.

        This is the KEY integration point. By representing drafted players
        as "keepers" with their auction prices as keeper salaries, we can
        reuse the existing keeper_handler.py without modifications.

        Returns:
            DataFrame with columns: player_id, keeper_salary

        The returned DataFrame can be passed directly to process_keepers()
        from keeper_handler.py.
        """
        keeper_data = []

        # Extract all drafted players from team rosters
        for team in self.state.teams.values():
            for position, player_ids in team.roster.items():
                for player_id in player_ids:
                    player = self.state.players[player_id]
                    keeper_data.append({
                        'player_id': player_id,
                        'keeper_salary': player.price
                    })

        df = pd.DataFrame(keeper_data)

        if len(df) > 0:
            logger.debug(
                f"Converted {len(df)} drafted players to keeper format "
                f"(total cost: ${df['keeper_salary'].sum():.0f})"
            )
        else:
            logger.debug("No players drafted yet - empty keeper DataFrame")

        return df

    def get_available_players(self, all_players_df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter player pool to only undrafted players.

        Args:
            all_players_df: DataFrame with all projected players
                           (must have player_id column)

        Returns:
            Filtered DataFrame with drafted players removed

        Raises:
            ValueError: If player_id column missing
        """
        if 'player_id' not in all_players_df.columns:
            raise ValueError("all_players_df must have 'player_id' column")

        # Get set of drafted player IDs from PlayerState
        drafted_ids = {
            player_id for player_id, player in self.state.players.items()
            if player.drafted
        }

        initial_count = len(all_players_df)
        filtered_df = all_players_df[
            ~all_players_df['player_id'].isin(drafted_ids)
        ]
        removed_count = initial_count - len(filtered_df)

        logger.debug(
            f"Filtered player pool: {initial_count} → {len(filtered_df)} "
            f"({removed_count} drafted players removed)"
        )

        return filtered_df

    def save_checkpoint(self, filepath: Path) -> None:
        """
        Save current state to compressed JSON for crash recovery.

        Uses gzip compression to reduce file size by ~80-90%.

        Args:
            filepath: Path for checkpoint file (will add .gz extension)
        """
        filepath.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            'state': self.state.to_dict(),
            'event_count': len(self.event_history),
            'checkpoint_time': datetime.now().isoformat()
        }

        # Atomic write with compression: write to temp file, then rename
        checkpoint_path = filepath.with_suffix('.json.gz')
        temp_path = filepath.with_suffix('.tmp.gz')

        with gzip.open(temp_path, 'wt', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2)

        temp_path.replace(checkpoint_path)

        logger.info(
            f"Saved checkpoint: {self.state.total_picks()} picks, "
            f"{sum(t.budget_remaining for t in self.state.teams.values()):.0f} budget remaining → "
            f"{checkpoint_path}"
        )

    @classmethod
    def load_checkpoint(
        cls,
        filepath: Path,
        hitters_df: pd.DataFrame,
        pitchers_df: pd.DataFrame,
        league_id: str = 'default'
    ) -> 'DraftStateManagerV2':
        """
        Load state from JSON checkpoint with auto-migration.

        Automatically detects v1 checkpoints and migrates to v2 schema.

        Args:
            filepath: Path to checkpoint file
            hitters_df: Hitter projections (needed for migration)
            pitchers_df: Pitcher projections (needed for migration)
            league_id: League identifier (for migration)

        Returns:
            DraftStateManagerV2 with loaded state

        Raises:
            FileNotFoundError: If checkpoint doesn't exist
            ValueError: If checkpoint is invalid
        """
        # Try .gz first, fallback to uncompressed
        checkpoint_path = filepath.with_suffix('.json.gz')
        if checkpoint_path.exists():
            logger.debug(f"Loading compressed checkpoint from {checkpoint_path}")
            with gzip.open(checkpoint_path, 'rt', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
        elif filepath.exists():
            logger.debug(f"Loading uncompressed checkpoint from {filepath}")
            with open(filepath, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
        else:
            raise FileNotFoundError(
                f"Checkpoint not found: {filepath} or {checkpoint_path}"
            )

        # Detect version and migrate if needed
        version = CheckpointMigrator.detect_version(checkpoint_data)

        if version == '1.0':
            logger.info("Detected v1 checkpoint - migrating to v2 schema...")
            state = CheckpointMigrator.migrate_v1_to_v2(
                checkpoint_data,
                hitters_df,
                pitchers_df,
                league_id
            )
            logger.info("Migration completed successfully")
        else:
            # v2 checkpoint - direct deserialization
            state = LeagueState.from_dict(checkpoint_data['state'])

        manager = cls(state, hitters_df, pitchers_df)

        logger.info(
            f"Loaded checkpoint: {state.total_picks()} picks, "
            f"{sum(t.budget_remaining for t in state.teams.values()):.0f} budget remaining ← "
            f"{filepath}"
        )

        return manager

    def get_team_summary(self) -> pd.DataFrame:
        """
        Get summary statistics for all teams.

        Returns:
            DataFrame with team stats including roster size, budget, etc.
        """
        summary_data = []

        for team_id, team in self.state.teams.items():
            rate_stats = team.stats.calculate_rate_stats()

            summary_data.append({
                'team_id': team_id,
                'team_name': team.team_name,
                'roster_size': team.total_roster_size,
                'budget_spent': team.budget_spent,
                'budget_remaining': team.budget_remaining,
                'open_slots': team.total_open_slots,
                # Counting stats
                'R': team.stats.counting.get('R', 0),
                'RBI': team.stats.counting.get('RBI', 0),
                'SB': team.stats.counting.get('SB', 0),
                'W_QS': team.stats.counting.get('W_QS', 0),
                'SV_HLD': team.stats.counting.get('SV_HLD', 0),
                'K': team.stats.counting.get('K', 0),
                # Rate stats
                'OBP': rate_stats.get('OBP', 0),
                'SLG': rate_stats.get('SLG', 0),
                'ERA': rate_stats.get('ERA', 0),
                'WHIP': rate_stats.get('WHIP', 0),
            })

        return pd.DataFrame(summary_data).sort_values('team_id')

    def get_event_log(self) -> pd.DataFrame:
        """
        Get complete event log as DataFrame.

        Returns:
            DataFrame with all draft events
        """
        event_data = []

        for event in self.state.draft.events:
            player = self.state.players.get(event.player_id)
            event_data.append({
                'pick_number': event.pick_number,
                'player_id': event.player_id,
                'player_name': event.player_name,
                'team_id': event.team_id,
                'price': event.price,
                'assigned_position': event.assigned_position,
                'timestamp': event.timestamp,
                'eligible_positions': player.eligible_positions if player else []
            })

        df = pd.DataFrame(event_data)

        if len(df) > 0:
            df = df.sort_values('pick_number')

        return df
