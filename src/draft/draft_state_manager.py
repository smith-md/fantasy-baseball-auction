"""
Manage league state and apply draft events.

The DraftStateManager is responsible for:
- Applying draft events to update league state
- Converting draft state to "keeper format" for pipeline integration
- Filtering player pools to exclude drafted players
- Checkpointing state for crash recovery
"""

import logging
import json
import pandas as pd
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .draft_event import DraftEvent, LeagueState

logger = logging.getLogger(__name__)


class DraftStateManager:
    """Manages league state and applies draft events."""

    def __init__(self, initial_state: LeagueState):
        """
        Initialize state manager with a league state.

        Args:
            initial_state: Starting league state (fresh or loaded from checkpoint)
        """
        self.state = initial_state
        self.event_history: List[DraftEvent] = []

    def apply_event(self, event: DraftEvent) -> None:
        """
        Apply a draft event to league state.

        This performs all state updates:
        1. Add player to team roster
        2. Decrement team budget by price
        3. Decrement roster spot count
        4. Add player_id to drafted_players set
        5. Update league-wide available_budget and available_roster_spots
        6. Append to event_history

        Args:
            event: DraftEvent to apply

        Raises:
            ValueError: If event is invalid (team doesn't exist, player already drafted, etc.)
        """
        # Validate team exists
        if event.team_id not in self.state.teams:
            raise ValueError(f"Unknown team_id: {event.team_id}")

        # Validate player not already drafted
        if event.player_id in self.state.drafted_players:
            raise ValueError(
                f"Player {event.player_id} ({event.player_name}) "
                f"already drafted at pick {self._find_pick_number(event.player_id)}"
            )

        # Get team
        team = self.state.teams[event.team_id]

        # Add pick to team (this validates budget/roster constraints)
        team.add_pick(event)

        # Update league-wide tracking
        self.state.drafted_players.add(event.player_id)
        self.state.available_budget -= event.price
        self.state.available_roster_spots -= 1
        self.state.last_processed_pick = max(
            self.state.last_processed_pick,
            event.pick_number
        )

        # Record event
        self.event_history.append(event)

        logger.debug(
            f"Applied Pick {event.pick_number}: {event.player_name} → "
            f"{team.team_name} (${event.price}) | "
            f"{self.state.available_roster_spots} spots, "
            f"${self.state.available_budget} remaining"
        )

        # Validate state consistency
        try:
            self.state.validate()
        except ValueError as e:
            logger.error(f"State validation failed after applying event: {e}")
            raise

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
                f"Remaining: {self.state.available_roster_spots} spots, "
                f"${self.state.available_budget}"
            )

    def to_keeper_format(self) -> pd.DataFrame:
        """
        Convert current draft state to keeper format.

        This is the KEY integration point. By representing drafted players
        as "keepers" with their auction prices as keeper salaries, we can
        reuse the existing keeper_handler.py without any modifications.

        Returns:
            DataFrame with columns: player_id, keeper_salary

        The returned DataFrame can be written to CSV and passed directly
        to process_keepers() from keeper_handler.py.
        """
        keeper_data = []

        # Convert all drafted players (from team rosters) to keepers
        for team in self.state.teams.values():
            for pick in team.roster:
                keeper_data.append({
                    'player_id': pick.player_id,
                    'keeper_salary': pick.price
                })

        # Also include pre-draft keepers if any
        for keeper_event in self.state.keeper_events:
            # Avoid duplicates (shouldn't happen, but be safe)
            if not any(k['player_id'] == keeper_event.player_id for k in keeper_data):
                keeper_data.append({
                    'player_id': keeper_event.player_id,
                    'keeper_salary': keeper_event.price
                })

        df = pd.DataFrame(keeper_data)

        if len(df) > 0:
            logger.debug(
                f"Converted {len(df)} drafted players to keeper format "
                f"(total cost: ${df['keeper_salary'].sum()})"
            )
        else:
            logger.debug("No players drafted yet - empty keeper DataFrame")

        return df

    def get_available_players(self, all_players_df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter player pool to only undrafted players.

        Args:
            all_players_df: DataFrame with all projected players (must have player_id column)

        Returns:
            Filtered DataFrame with drafted players removed

        Raises:
            ValueError: If player_id column missing
        """
        if 'player_id' not in all_players_df.columns:
            raise ValueError("all_players_df must have 'player_id' column")

        initial_count = len(all_players_df)
        filtered_df = all_players_df[
            ~all_players_df['player_id'].isin(self.state.drafted_players)
        ]
        removed_count = initial_count - len(filtered_df)

        logger.debug(
            f"Filtered player pool: {initial_count} → {len(filtered_df)} "
            f"({removed_count} drafted players removed)"
        )

        return filtered_df

    def save_checkpoint(self, filepath: Path) -> None:
        """
        Save current state to JSON for crash recovery.

        Args:
            filepath: Path for checkpoint file
        """
        filepath.parent.mkdir(parents=True, exist_ok=True)

        checkpoint_data = {
            'state': self.state.to_dict(),
            'event_count': len(self.event_history),
            'checkpoint_time': datetime.now().isoformat()
        }

        # Atomic write: write to temp file, then rename
        temp_path = filepath.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2)

        temp_path.replace(filepath)

        logger.info(
            f"Saved checkpoint: {self.state.total_picks()} picks, "
            f"${self.state.available_budget} remaining → {filepath}"
        )

    @classmethod
    def load_checkpoint(cls, filepath: Path) -> 'DraftStateManager':
        """
        Load state from JSON checkpoint.

        Args:
            filepath: Path to checkpoint file

        Returns:
            DraftStateManager with loaded state

        Raises:
            FileNotFoundError: If checkpoint doesn't exist
        """
        if not filepath.exists():
            raise FileNotFoundError(f"Checkpoint not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            checkpoint_data = json.load(f)

        state = LeagueState.from_dict(checkpoint_data['state'])
        manager = cls(state)

        logger.info(
            f"Loaded checkpoint: {state.total_picks()} picks, "
            f"${state.available_budget} remaining ← {filepath}"
        )

        return manager

    def get_team_summary(self) -> pd.DataFrame:
        """
        Get summary statistics for all teams.

        Returns:
            DataFrame with team_id, team_name, picks, spent, budget_remaining, spots_remaining
        """
        summary_data = []
        for team_id, team in self.state.teams.items():
            summary_data.append({
                'team_id': team_id,
                'team_name': team.team_name,
                'picks': len(team.roster),
                'spent': team.total_spent(),
                'budget_remaining': team.budget_remaining,
                'spots_remaining': team.roster_spots_remaining
            })

        return pd.DataFrame(summary_data).sort_values('team_id')

    def _find_pick_number(self, player_id: str) -> Optional[int]:
        """
        Find the pick number for a player (helper for error messages).

        Args:
            player_id: Player ID to find

        Returns:
            Pick number or None if not found
        """
        for team in self.state.teams.values():
            for pick in team.roster:
                if pick.player_id == player_id:
                    return pick.pick_number
        return None
