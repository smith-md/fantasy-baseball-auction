"""
Result caching for live draft valuations.

Provides JSON cache file that can be consumed by web UIs or other tools.
Uses atomic writes (temp file + rename) to ensure cache is never corrupted.
"""

import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
import pandas as pd

from .draft_event import LeagueState

logger = logging.getLogger(__name__)


class ResultCache:
    """Cache latest valuations for API/web consumption."""

    def __init__(self, cache_dir: Path):
        """
        Initialize result cache.

        Args:
            cache_dir: Directory for cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_file = self.cache_dir / "latest_valuations.json"
        self.backup_dir = self.cache_dir / "history"
        self.backup_dir.mkdir(exist_ok=True)

    def update(
        self,
        valuations_df: pd.DataFrame,
        league_state: LeagueState,
        timestamp: datetime
    ) -> None:
        """
        Update cache with latest valuations.

        Args:
            valuations_df: DataFrame with player valuations
            league_state: Current league state
            timestamp: When this valuation was computed

        Writes to temp file first, then atomically renames to ensure
        cache file is never left in corrupted state.
        """
        # Convert valuations DataFrame to list of player dicts
        players = self._dataframe_to_players(valuations_df)

        # Build cache structure
        cache_data = {
            "timestamp": timestamp.isoformat(),
            "last_pick": league_state.last_processed_pick,
            "total_picks": league_state.total_picks(),
            "available_budget": league_state.available_budget,
            "available_roster_spots": league_state.available_roster_spots,
            "num_players": len(players),
            "team_summary": self._get_team_summary(league_state),
            "players": players
        }

        # Atomic write: temp file + rename
        temp_file = self.cache_file.with_suffix('.tmp')

        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)

        temp_file.replace(self.cache_file)

        logger.info(f"Updated cache: {len(players)} players → {self.cache_file}")

        # Also save historical snapshot
        self._save_backup(cache_data, league_state.last_processed_pick)

    def get_latest(self) -> Optional[dict]:
        """
        Read latest cached results.

        Returns:
            Cached data dict or None if cache doesn't exist
        """
        if not self.cache_file.exists():
            logger.warning(f"Cache file does not exist: {self.cache_file}")
            return None

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read cache: {e}")
            return None

    def _dataframe_to_players(self, df: pd.DataFrame) -> list:
        """
        Convert valuations DataFrame to list of player dicts.

        Args:
            df: Valuations DataFrame

        Returns:
            List of player dicts with relevant fields
        """
        # Select key columns for cache
        # (avoid dumping ALL columns to keep cache size reasonable)
        core_columns = [
            'player_name', 'team', 'positions', 'assigned_position',
            'auction_value', 'overall_rank', 'position_rank',
            'raw_value', 'VAR', 'replacement_level'
        ]

        # Add stat columns based on player type
        stat_columns = []
        if 'PA' in df.columns:  # Hitter
            stat_columns = ['PA', 'AB', 'R', 'RBI', 'SB', 'OBP', 'SLG']
        elif 'IP' in df.columns:  # Pitcher
            stat_columns = ['IP', 'W_QS', 'SV_HLD', 'K', 'ERA', 'WHIP']

        # Combine columns (only include those that exist)
        columns_to_include = [
            col for col in (core_columns + stat_columns)
            if col in df.columns
        ]

        # Convert to records
        players = df[columns_to_include].to_dict('records')

        # Post-process to handle NaN and special types
        for player in players:
            # Convert numpy types to Python types
            for key, value in player.items():
                if pd.isna(value):
                    player[key] = None
                elif isinstance(value, (pd.Int64Dtype, pd.Float64Dtype)):
                    player[key] = float(value) if value is not None else None
                elif hasattr(value, 'item'):  # numpy types
                    player[key] = value.item()

        return players

    def _get_team_summary(self, league_state: LeagueState) -> list:
        """
        Generate team summary from league state.

        Args:
            league_state: Current league state

        Returns:
            List of team summary dicts
        """
        summary = []
        for team_id, team in league_state.teams.items():
            summary.append({
                "team_id": team_id,
                "team_name": team.team_name,
                "picks": len(team.roster),
                "spent": team.total_spent(),
                "budget_remaining": team.budget_remaining,
                "spots_remaining": team.roster_spots_remaining
            })

        # Sort by team_id for consistency
        summary.sort(key=lambda t: t['team_id'])
        return summary

    def _save_backup(self, cache_data: dict, pick_number: int) -> None:
        """
        Save historical snapshot of cache.

        Args:
            cache_data: Cache data to save
            pick_number: Pick number for filename
        """
        # Only save every 10 picks to avoid too many files
        if pick_number % 10 != 0:
            return

        backup_file = self.backup_dir / f"valuations_pick{pick_number:03d}.json"

        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Saved backup: {backup_file}")
        except IOError as e:
            logger.warning(f"Failed to save backup: {e}")

    def export_to_csv(self, output_path: Path) -> None:
        """
        Export latest cache to CSV format.

        Args:
            output_path: Path for CSV output
        """
        cache_data = self.get_latest()
        if not cache_data:
            logger.error("No cache data to export")
            return

        players = cache_data.get('players', [])
        if not players:
            logger.warning("No players in cache")
            return

        # Convert to DataFrame and save
        df = pd.DataFrame(players)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)

        logger.info(f"Exported {len(df)} players to {output_path}")

    def clear(self) -> None:
        """
        Clear cache files.

        WARNING: Deletes cache and backups. Use with caution.
        """
        if self.cache_file.exists():
            self.cache_file.unlink()
            logger.warning(f"Cleared cache: {self.cache_file}")

        # Clear backups
        for backup_file in self.backup_dir.glob("*.json"):
            backup_file.unlink()

        logger.warning(f"Cleared backup directory: {self.backup_dir}")
