"""
Convert rate statistics to playing-time-weighted contributions.

This module transforms rate stats (OBP, SLG, ERA, WHIP) into counting-style
contributions that can be normalized alongside other counting stats.
"""

import pandas as pd
import numpy as np

from . import config


class StatConverter:
    """Converts rate stats to playing-time-weighted contributions."""

    def __init__(self, df: pd.DataFrame, player_type: str):
        """
        Initialize the stat converter.

        Args:
            df: DataFrame with player projections
            player_type: 'hitters' or 'pitchers'
        """
        self.df = df.copy()
        self.player_type = player_type

    def convert_hitter_rate_stats(self) -> pd.DataFrame:
        """
        Convert hitter rate stats (OBP, SLG) to contributions.

        Formula:
        - OBP_contrib = (OBP_player - OBP_avg) × PA
        - SLG_contrib = (SLG_player - SLG_avg) × AB

        Returns:
            DataFrame with added contribution columns
        """
        if self.player_type != 'hitters':
            raise ValueError("This method is only for hitters")

        # Calculate league-average rate stats from the draftable pool
        obp_avg = self.df['OBP'].mean()
        slg_avg = self.df['SLG'].mean()

        print(f"League average OBP: {obp_avg:.3f}")
        print(f"League average SLG: {slg_avg:.3f}")

        # Convert OBP to contribution
        if 'OBP' in self.df.columns and 'PA' in self.df.columns:
            self.df['OBP_contrib'] = (self.df['OBP'] - obp_avg) * self.df['PA']
        else:
            raise ValueError("Missing required columns: OBP and/or PA")

        # Convert SLG to contribution
        if 'SLG' in self.df.columns and 'AB' in self.df.columns:
            self.df['SLG_contrib'] = (self.df['SLG'] - slg_avg) * self.df['AB']
        else:
            raise ValueError("Missing required columns: SLG and/or AB")

        return self.df

    def convert_pitcher_rate_stats(self) -> pd.DataFrame:
        """
        Convert pitcher rate stats (ERA, WHIP) to contributions.

        Formula (lower is better, so inverted):
        - ERA_contrib = (ERA_avg - ERA_player) × IP
        - WHIP_contrib = (WHIP_avg - WHIP_player) × IP

        Returns:
            DataFrame with added contribution columns
        """
        if self.player_type != 'pitchers':
            raise ValueError("This method is only for pitchers")

        # Calculate league-average rate stats from the draftable pool
        era_avg = self.df['ERA'].mean()
        whip_avg = self.df['WHIP'].mean()

        print(f"League average ERA: {era_avg:.2f}")
        print(f"League average WHIP: {whip_avg:.3f}")

        # Convert ERA to contribution (inverted: lower ERA is better)
        if 'ERA' in self.df.columns and 'IP' in self.df.columns:
            self.df['ERA_contrib'] = (era_avg - self.df['ERA']) * self.df['IP']
        else:
            raise ValueError("Missing required columns: ERA and/or IP")

        # Convert WHIP to contribution (inverted: lower WHIP is better)
        if 'WHIP' in self.df.columns and 'IP' in self.df.columns:
            self.df['WHIP_contrib'] = (whip_avg - self.df['WHIP']) * self.df['IP']
        else:
            raise ValueError("Missing required columns: WHIP and/or IP")

        return self.df

    def convert(self) -> pd.DataFrame:
        """
        Convert rate stats to contributions based on player type.

        Returns:
            DataFrame with converted rate stats
        """
        if self.player_type == 'hitters':
            return self.convert_hitter_rate_stats()
        elif self.player_type == 'pitchers':
            return self.convert_pitcher_rate_stats()
        else:
            raise ValueError(f"Invalid player_type: {self.player_type}")


def convert_hitter_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience function to convert hitter rate stats.

    Args:
        df: Hitter projections DataFrame

    Returns:
        DataFrame with OBP_contrib and SLG_contrib columns
    """
    converter = StatConverter(df, 'hitters')
    return converter.convert()


def convert_pitcher_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience function to convert pitcher rate stats.

    Args:
        df: Pitcher projections DataFrame

    Returns:
        DataFrame with ERA_contrib and WHIP_contrib columns
    """
    converter = StatConverter(df, 'pitchers')
    return converter.convert()


def get_hitter_categories_for_normalization() -> list:
    """
    Get the list of hitter categories to use for normalization.

    This replaces rate stats with their contribution versions.

    Returns:
        List of column names to normalize
    """
    categories = []

    for cat in config.HITTER_CATEGORIES:
        if cat in config.HITTER_RATE_STATS:
            # Use contribution version
            categories.append(f"{cat}_contrib")
        else:
            # Use raw stat
            categories.append(cat)

    return categories


def get_pitcher_categories_for_normalization() -> list:
    """
    Get the list of pitcher categories to use for normalization.

    This replaces rate stats with their contribution versions.
    Also maps FanGraphs column names (e.g., SO → K).

    Returns:
        List of column names to normalize
    """
    # FanGraphs uses 'SO' instead of 'K'
    stat_mapping = {'K': 'SO'}

    categories = []

    for cat in config.PITCHER_CATEGORIES:
        if cat in config.PITCHER_RATE_STATS:
            # Use contribution version
            categories.append(f"{cat}_contrib")
        else:
            # Use raw stat, with FanGraphs mapping
            mapped_stat = stat_mapping.get(cat, cat)
            categories.append(mapped_stat)

    return categories
