"""
Combine multiple projection systems into a single consensus projection.
"""

from typing import Dict, List, Optional

import pandas as pd
import numpy as np

from . import config


class ProjectionCombiner:
    """Combines multiple projection systems into a single consensus projection."""

    def __init__(self, projections: Dict[str, pd.DataFrame]):
        """
        Initialize the projection combiner.

        Args:
            projections: Dictionary mapping projection system names to DataFrames
        """
        self.projections = projections

    @staticmethod
    def _standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names across different projection systems.

        Different sources may use different column names for the same stat.
        This function maps common variations to our standard names.
        """
        # Common column name mappings for FanGraphs API
        # Handle positions: prioritize minpos over Pos
        if 'minpos' in df.columns:
            df = df.rename(columns={'minpos': 'positions'})
            if 'Pos' in df.columns:
                df = df.drop(columns=['Pos'])  # Remove numeric Pos column
        elif 'Pos' in df.columns:
            df = df.rename(columns={'Pos': 'positions'})
        elif 'pos' in df.columns:
            df = df.rename(columns={'pos': 'positions'})
        elif 'Position' in df.columns:
            df = df.rename(columns={'Position': 'positions'})

        # Other column mappings
        column_mappings = {
            'playerid': 'player_id',
            'PlayerId': 'player_id',
            'PlayerID': 'player_id',
            'Team': 'team',
            'team': 'team',
            # Add more mappings as needed
        }

        # Rename columns if they exist
        df = df.rename(columns={k: v for k, v in column_mappings.items() if k in df.columns})

        # Handle player_name: prefer PlayerName, fall back to ShortName
        if 'PlayerName' in df.columns:
            df = df.rename(columns={'PlayerName': 'player_name'})
            if 'ShortName' in df.columns:
                df = df.drop(columns=['ShortName'])  # Remove duplicate
        elif 'ShortName' in df.columns:
            df = df.rename(columns={'ShortName': 'player_name'})
        elif 'Name' in df.columns:
            df = df.rename(columns={'Name': 'player_name'})

        return df

    @staticmethod
    def _parse_positions(positions_str: str) -> List[str]:
        """
        Parse position string into list of positions.

        Args:
            positions_str: Position string (e.g., "1B/OF", "SS, 2B", "C")

        Returns:
            List of position codes
        """
        if pd.isna(positions_str) or not positions_str:
            return []

        # Handle various delimiters
        positions_str = str(positions_str).replace(',', '/').replace(' ', '')

        # Split on '/' and filter empty strings
        positions = [pos.strip() for pos in positions_str.split('/') if pos.strip()]

        return positions

    @staticmethod
    def _merge_positions(position_lists: List[List[str]]) -> List[str]:
        """
        Merge multiple position lists into a single unique list (union).

        Args:
            position_lists: List of position lists from different projection systems

        Returns:
            Unique list of positions
        """
        all_positions = set()
        for pos_list in position_lists:
            if pos_list:
                all_positions.update(pos_list)

        return sorted(list(all_positions))

    def _identify_player_key(self, df: pd.DataFrame) -> str:
        """
        Identify which column to use as the player key for merging.

        Priority: player_id > playerid > player_name

        Args:
            df: DataFrame to check

        Returns:
            Column name to use as player key
        """
        if 'player_id' in df.columns:
            return 'player_id'
        elif 'playerid' in df.columns:
            return 'playerid'
        elif 'player_name' in df.columns:
            return 'player_name'
        elif 'Name' in df.columns:
            return 'Name'
        else:
            raise ValueError("No suitable player identifier column found")

    def combine(self, player_type: str, stat_columns: List[str]) -> pd.DataFrame:
        """
        Combine projections from multiple systems using simple mean.

        Args:
            player_type: 'hitters' or 'pitchers'
            stat_columns: List of stat columns to combine

        Returns:
            Combined DataFrame with consensus projections
        """
        if not self.projections:
            raise ValueError("No projections provided")

        # Standardize column names for all DataFrames
        # Skip empty DataFrames
        standardized = {}
        for system, df in self.projections.items():
            if df is None or len(df) == 0:
                print(f"Warning: Skipping {system} - no data available")
                continue
            df_std = self._standardize_column_names(df.copy())
            standardized[system] = df_std

        if not standardized:
            raise ValueError("No valid projection data available")

        # Determine player key
        first_df = next(iter(standardized.values()))
        player_key = self._identify_player_key(first_df)

        # Build list of DataFrames with consistent player keys
        dfs_to_merge = []

        for system, df in standardized.items():
            # Select relevant columns
            cols_to_keep = [player_key]

            # Add player name if available and not already the key
            if 'player_name' in df.columns and player_key != 'player_name':
                cols_to_keep.append('player_name')

            # Add positions if available
            if 'positions' in df.columns:
                cols_to_keep.append('positions')

            # Add team if available
            if 'team' in df.columns:
                cols_to_keep.append('team')

            # Add stat columns that exist
            for stat in stat_columns:
                if stat in df.columns:
                    cols_to_keep.append(stat)

            # Select columns and add suffix for stats
            df_selected = df[cols_to_keep].copy()

            # Add suffix to stat columns to distinguish systems during merge
            rename_dict = {}
            for stat in stat_columns:
                if stat in df_selected.columns:
                    rename_dict[stat] = f"{stat}_{system}"

            df_selected = df_selected.rename(columns=rename_dict)
            dfs_to_merge.append((system, df_selected))

        # Start with the first DataFrame
        _, combined = dfs_to_merge[0]

        # Merge with remaining DataFrames
        for system, df in dfs_to_merge[1:]:
            combined = combined.merge(
                df,
                on=player_key,
                how='outer',
                suffixes=('', f'_{system}')
            )

        # Calculate mean for each stat across projection systems
        for stat in stat_columns:
            # Find all columns for this stat (e.g., PA_steamer, PA_zips, PA_atc)
            stat_cols = [col for col in combined.columns if col.startswith(f"{stat}_")]

            if stat_cols:
                # Calculate mean, ignoring NaN values
                combined[stat] = combined[stat_cols].mean(axis=1, skipna=True)

                # Drop the individual system columns
                combined = combined.drop(columns=stat_cols)

        # Merge positions from all systems (union)
        position_cols = [col for col in combined.columns if col.startswith('positions')]
        if position_cols:
            # Parse and merge positions
            for col in position_cols:
                combined[col] = combined[col].apply(self._parse_positions)

            combined['positions'] = combined[position_cols].apply(
                lambda row: self._merge_positions([pos for pos in row if isinstance(pos, list)]),
                axis=1
            )

            # Drop individual position columns
            combined = combined.drop(columns=[col for col in position_cols if col != 'positions'])

        # Merge player names (use first non-null value)
        name_cols = [col for col in combined.columns if 'player_name' in col.lower() and col != 'player_name']
        if name_cols and 'player_name' not in combined.columns:
            combined['player_name'] = combined[name_cols].bfill(axis=1).iloc[:, 0]
            combined = combined.drop(columns=name_cols)

        # Merge team (use first non-null value)
        team_cols = [col for col in combined.columns if col.startswith('team_')]
        if team_cols:
            combined['team'] = combined[team_cols].bfill(axis=1).iloc[:, 0]
            combined = combined.drop(columns=team_cols)

        # Filter out players with insufficient playing time
        if player_type == 'hitters' and 'PA' in combined.columns:
            initial_count = len(combined)
            combined = combined[combined['PA'] >= config.MIN_PA_HITTERS]
            filtered = initial_count - len(combined)
            print(f"Filtered out {filtered} hitters with PA < {config.MIN_PA_HITTERS}")

        elif player_type == 'pitchers' and 'IP' in combined.columns:
            initial_count = len(combined)
            combined = combined[combined['IP'] >= config.MIN_IP_PITCHERS]
            filtered = initial_count - len(combined)
            print(f"Filtered out {filtered} pitchers with IP < {config.MIN_IP_PITCHERS}")

        # Add compound categories if components exist
        for compound, components in config.COMPOUND_CATEGORIES.items():
            if all(comp in combined.columns for comp in components):
                combined[compound] = sum(combined[comp] for comp in components)

        # Reset index
        combined = combined.reset_index(drop=True)

        # Add default positions for pitchers if not present
        if player_type == 'pitchers' and 'positions' not in combined.columns:
            combined['positions'] = combined.apply(lambda x: ['P'], axis=1)
            print(f"Added default 'P' position for all pitchers")
        elif player_type == 'pitchers' and 'positions' in combined.columns:
            # Ensure positions is a list
            def ensure_list(pos):
                if isinstance(pos, list) and len(pos) > 0:
                    return pos
                return ['P']
            combined['positions'] = combined['positions'].apply(ensure_list)

        print(f"Combined {len(self.projections)} projection systems into {len(combined)} {player_type}")

        return combined


def combine_hitter_projections(projections: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Convenience function to combine hitter projections.

    Args:
        projections: Dictionary mapping projection system names to DataFrames

    Returns:
        Combined hitter projections DataFrame
    """
    combiner = ProjectionCombiner(projections)

    # Define stats to combine
    stats = config.HITTER_STATS_REQUIRED + config.HITTER_STATS_OPTIONAL

    return combiner.combine('hitters', stats)


def combine_pitcher_projections(projections: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Convenience function to combine pitcher projections.

    Args:
        projections: Dictionary mapping projection system names to DataFrames

    Returns:
        Combined pitcher projections DataFrame
    """
    combiner = ProjectionCombiner(projections)

    # Define stats to combine (including components of compound categories)
    stats = config.PITCHER_STATS_REQUIRED + config.PITCHER_STATS_OPTIONAL

    return combiner.combine('pitchers', stats)
