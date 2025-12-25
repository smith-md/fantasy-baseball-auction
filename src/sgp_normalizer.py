"""
SGP-based normalization - drop-in replacement for normalizer.py.

Provides the same interface as normalizer.py but uses SGP (Standings Gain Points)
instead of z-scores for player valuation.
"""

import logging
import pandas as pd

from . import config
from .sgp import load_historical_standings, calculate_sgp_values

logger = logging.getLogger(__name__)

# Cache standings data to avoid reloading for every call
_standings_cache = None


def _get_standings_data():
    """
    Get historical standings data, using cache if available.

    Returns:
        Dictionary of season -> SeasonStandings
    """
    global _standings_cache

    if _standings_cache is None:
        logger.info("Loading historical standings data for SGP calculation")
        _standings_cache = load_historical_standings(
            seasons=config.SGP_SEASONS,
            data_dir=config.SGP_DATA_DIR
        )
        logger.info(f"Loaded {len(_standings_cache)} seasons of standings data")

    return _standings_cache


def normalize_hitters(df: pd.DataFrame, stat_columns: list) -> pd.DataFrame:
    """
    Calculate SGP values for hitters (drop-in replacement for z-score normalizer).

    This function has the same signature as normalizer.normalize_hitters()
    but uses SGP calculation instead of z-scores.

    Args:
        df: Hitter projections DataFrame (with converted rate stats)
        stat_columns: List of categories (passed for compatibility, but ignored)

    Returns:
        DataFrame with SGP columns and raw_value
    """
    logger.info(f"\n{'='*60}")
    logger.info("Calculating SGP for Hitters")
    logger.info(f"{'='*60}")

    # Get standings data
    standings_data = _get_standings_data()

    # Calculate SGP
    result_df = calculate_sgp_values(
        df,
        player_type='hitters',
        standings_data=standings_data,
        write_diagnostics=config.SGP_WRITE_DIAGNOSTICS
    )

    logger.info(f"\nCompleted SGP calculation for {len(result_df)} hitters")
    logger.info(
        f"raw_value (total SGP) range: "
        f"[{result_df['raw_value'].min():.2f}, {result_df['raw_value'].max():.2f}]"
    )

    return result_df


def normalize_pitchers(df: pd.DataFrame, stat_columns: list) -> pd.DataFrame:
    """
    Calculate SGP values for pitchers (drop-in replacement for z-score normalizer).

    This function has the same signature as normalizer.normalize_pitchers()
    but uses SGP calculation instead of z-scores.

    Args:
        df: Pitcher projections DataFrame (with converted rate stats)
        stat_columns: List of categories (passed for compatibility, but ignored)

    Returns:
        DataFrame with SGP columns and raw_value
    """
    logger.info(f"\n{'='*60}")
    logger.info("Calculating SGP for Pitchers")
    logger.info(f"{'='*60}")

    # Get standings data
    standings_data = _get_standings_data()

    # Calculate SGP
    result_df = calculate_sgp_values(
        df,
        player_type='pitchers',
        standings_data=standings_data,
        write_diagnostics=config.SGP_WRITE_DIAGNOSTICS
    )

    logger.info(f"\nCompleted SGP calculation for {len(result_df)} pitchers")
    logger.info(
        f"raw_value (total SGP) range: "
        f"[{result_df['raw_value'].min():.2f}, {result_df['raw_value'].max():.2f}]"
    )

    return result_df
