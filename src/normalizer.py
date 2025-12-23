"""
Normalize statistics using z-scores and calculate raw player values.
"""

import pandas as pd
import numpy as np
from scipy import stats

from . import config


class StatNormalizer:
    """Normalizes statistics using z-scores."""

    def __init__(self, df: pd.DataFrame, player_type: str):
        """
        Initialize the stat normalizer.

        Args:
            df: DataFrame with player projections (with converted rate stats)
            player_type: 'hitters' or 'pitchers'
        """
        self.df = df.copy()
        self.player_type = player_type

    def normalize(self, stat_columns: list) -> pd.DataFrame:
        """
        Calculate z-scores for specified stat columns.

        Args:
            stat_columns: List of column names to normalize

        Returns:
            DataFrame with added z-score columns and raw_value
        """
        zscore_columns = []

        for stat in stat_columns:
            if stat not in self.df.columns:
                print(f"Warning: Stat '{stat}' not found in DataFrame, skipping...")
                continue

            # Calculate z-score
            # Handle edge cases where std is 0 or NaN
            mean = self.df[stat].mean()
            std = self.df[stat].std()

            if std == 0 or pd.isna(std):
                print(f"Warning: Standard deviation for '{stat}' is {std}, setting z-scores to 0")
                self.df[f'{stat}_zscore'] = 0
            else:
                # Use scipy.stats.zscore for robust calculation
                self.df[f'{stat}_zscore'] = stats.zscore(
                    self.df[stat],
                    nan_policy='omit'
                )

                # Replace any NaN z-scores with 0
                self.df[f'{stat}_zscore'].fillna(0, inplace=True)

            zscore_columns.append(f'{stat}_zscore')

            # Print stats for debugging
            print(f"{stat}: mean={mean:.2f}, std={std:.2f}, "
                  f"z-score range=[{self.df[f'{stat}_zscore'].min():.2f}, "
                  f"{self.df[f'{stat}_zscore'].max():.2f}]")

        # Calculate raw_value as sum of z-scores
        if zscore_columns:
            self.df['raw_value'] = self.df[zscore_columns].sum(axis=1)
            print(f"\nCalculated raw_value for {len(self.df)} {self.player_type}")
            print(f"raw_value range: [{self.df['raw_value'].min():.2f}, "
                  f"{self.df['raw_value'].max():.2f}]")
        else:
            raise ValueError("No valid stat columns found for normalization")

        return self.df


def normalize_hitters(df: pd.DataFrame, stat_columns: list) -> pd.DataFrame:
    """
    Convenience function to normalize hitter stats.

    Args:
        df: Hitter projections DataFrame (with converted rate stats)
        stat_columns: List of stat columns to normalize

    Returns:
        DataFrame with z-score columns and raw_value
    """
    normalizer = StatNormalizer(df, 'hitters')
    return normalizer.normalize(stat_columns)


def normalize_pitchers(df: pd.DataFrame, stat_columns: list) -> pd.DataFrame:
    """
    Convenience function to normalize pitcher stats.

    Args:
        df: Pitcher projections DataFrame (with converted rate stats)
        stat_columns: List of stat columns to normalize

    Returns:
        DataFrame with z-score columns and raw_value
    """
    normalizer = StatNormalizer(df, 'pitchers')
    return normalizer.normalize(stat_columns)
