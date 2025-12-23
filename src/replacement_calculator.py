"""
Calculate replacement levels and value above replacement (VAR).

Replacement level is defined as the raw_value of the last player assigned
to each position.
"""

import pandas as pd
import numpy as np
from typing import Dict

from . import config


class ReplacementCalculator:
    """Calculates replacement levels and value above replacement."""

    def __init__(self, assignments_df: pd.DataFrame):
        """
        Initialize the replacement calculator.

        Args:
            assignments_df: DataFrame with position assignments and raw_value
        """
        self.assignments_df = assignments_df.copy()
        self.replacement_levels = {}

    def calculate_replacement_levels(self) -> Dict[str, float]:
        """
        Calculate replacement level for each position.

        Replacement level = raw_value of the last (worst) player assigned to that position.

        Returns:
            Dictionary mapping position to replacement level
        """
        print("\nCalculating replacement levels...")

        # Group by assigned position and find minimum raw_value
        # The minimum raw_value represents the replacement level for that position
        for position in config.ROSTER_SLOTS.keys():
            position_players = self.assignments_df[
                self.assignments_df['assigned_position'] == position
            ]

            if len(position_players) > 0:
                # Replacement level is the minimum raw_value assigned to this position
                replacement_level = position_players['raw_value'].min()
                self.replacement_levels[position] = replacement_level

                print(f"{position}: replacement level = {replacement_level:.2f} "
                      f"({len(position_players)} players)")
            else:
                # No players assigned to this position
                self.replacement_levels[position] = 0.0
                print(f"{position}: no players assigned, using 0.0")

        return self.replacement_levels

    def calculate_var(self) -> pd.DataFrame:
        """
        Calculate value above replacement (VAR) for each player.

        VAR = max(0, raw_value - replacement_level[assigned_position])

        Returns:
            DataFrame with added replacement_level and VAR columns
        """
        if not self.replacement_levels:
            self.calculate_replacement_levels()

        # Map replacement level to each player based on their assigned position
        self.assignments_df['replacement_level'] = self.assignments_df['assigned_position'].map(
            self.replacement_levels
        )

        # Calculate VAR
        self.assignments_df['VAR'] = (
            self.assignments_df['raw_value'] - self.assignments_df['replacement_level']
        )

        # Set floor at 0 (players below replacement get VAR = 0)
        self.assignments_df['VAR'] = self.assignments_df['VAR'].clip(lower=0)

        # Print summary statistics
        print(f"\nVAR calculation summary:")
        print(f"Total players: {len(self.assignments_df)}")
        print(f"Players with VAR > 0: {(self.assignments_df['VAR'] > 0).sum()}")
        print(f"Total VAR (hitters): {self.assignments_df[self.assignments_df['player_type'] == 'hitter']['VAR'].sum():.2f}")
        print(f"Total VAR (pitchers): {self.assignments_df[self.assignments_df['player_type'] == 'pitcher']['VAR'].sum():.2f}")
        print(f"VAR range: [{self.assignments_df['VAR'].min():.2f}, "
              f"{self.assignments_df['VAR'].max():.2f}]")

        return self.assignments_df

    def get_replacement_levels(self) -> Dict[str, float]:
        """
        Get the calculated replacement levels.

        Returns:
            Dictionary mapping position to replacement level
        """
        if not self.replacement_levels:
            self.calculate_replacement_levels()

        return self.replacement_levels


def calculate_replacement_and_var(assignments_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience function to calculate replacement levels and VAR.

    Args:
        assignments_df: DataFrame with position assignments and raw_value

    Returns:
        DataFrame with replacement_level and VAR columns added
    """
    calculator = ReplacementCalculator(assignments_df)
    return calculator.calculate_var()
