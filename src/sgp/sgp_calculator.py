"""
Core SGP calculation engine.

Orchestrates the complete SGP calculation process:
1. Calculate replacement baselines
2. Calculate SGP denominators with multi-year smoothing
3. Convert player stats to SGP values
4. Sum to raw_value
"""

import logging
from typing import Dict
from dataclasses import dataclass
import pandas as pd
import numpy as np

from .. import config
from .league_data_loader import SeasonStandings, get_categories_for_player_type
from .category_analyzer import calculate_sgp_denominator_per_season
from .replacement_baseline import (
    calculate_replacement_baseline,
    calculate_ratio_marginal_impact,
    ReplacementBaseline
)

logger = logging.getLogger(__name__)


@dataclass
class SGPDenominators:
    """SGP denominators for a category."""
    category: str
    per_season: Dict[int, float]  # season -> denominator
    smoothed: float                # Multi-year weighted average
    seasons_used: list             # Which seasons contributed


def calculate_sgp_values(
    player_df: pd.DataFrame,
    player_type: str,
    standings_data: Dict[int, SeasonStandings],
    write_diagnostics: bool = True
) -> pd.DataFrame:
    """
    Main entry point for SGP calculation.

    This function:
    1. Calculates replacement baseline
    2. Calculates SGP denominators (with multi-year smoothing)
    3. Converts player stats to SGP per category
    4. Sums category SGP to raw_value

    Args:
        player_df: Player projections DataFrame
        player_type: 'hitters' or 'pitchers'
        standings_data: Historical standings data
        write_diagnostics: Whether to write diagnostic files

    Returns:
        DataFrame with SGP columns and raw_value
    """
    logger.info(f"\nCalculating SGP for {len(player_df)} {player_type}")

    df = player_df.copy()

    # Step 1: Calculate replacement baseline
    logger.info("Step 1: Calculating replacement baseline")
    baseline = calculate_replacement_baseline(df, player_type)

    # Step 2: Calculate marginal impacts for ratio categories
    logger.info("Step 2: Calculating ratio marginal impacts")
    df = calculate_ratio_marginal_impact(df, baseline, player_type)

    # Step 3: Calculate SGP denominators
    logger.info("Step 3: Calculating SGP denominators")
    categories = get_categories_for_player_type(player_type)
    denominators = {}

    for category in categories:
        denominators[category] = calculate_category_sgp_denominator(
            standings_data,
            category
        )

    # Step 4: Calculate SGP per category
    logger.info("Step 4: Converting stats to SGP values")
    sgp_columns = []

    for category in categories:
        sgp_col = f'{category}_sgp'

        if category in config.HITTER_RATE_STATS or category in config.PITCHER_RATE_STATS:
            # Ratio categories: use marginal impact
            marginal_col = f'{category}_marginal'

            if marginal_col in df.columns:
                df[sgp_col] = df[marginal_col] / denominators[category].smoothed
            else:
                logger.warning(
                    f"Missing {marginal_col} column, setting {sgp_col} to 0"
                )
                df[sgp_col] = 0

        else:
            # Counting categories: direct division
            # Map K to SO if needed (FanGraphs naming)
            stat_col = 'SO' if category == 'K' and 'SO' in df.columns else category

            if stat_col in df.columns:
                df[sgp_col] = df[stat_col] / denominators[category].smoothed
            else:
                logger.warning(
                    f"Missing {stat_col} column, setting {sgp_col} to 0"
                )
                df[sgp_col] = 0

        sgp_columns.append(sgp_col)

        # Log stats
        logger.info(
            f"{category}: denominator={denominators[category].smoothed:.3f}, "
            f"SGP range=[{df[sgp_col].min():.2f}, {df[sgp_col].max():.2f}]"
        )

    # Step 5: Sum to raw_value
    logger.info("Step 5: Summing category SGP to raw_value")
    df['raw_value'] = df[sgp_columns].sum(axis=1)

    logger.info(
        f"raw_value range: [{df['raw_value'].min():.2f}, "
        f"{df['raw_value'].max():.2f}]"
    )

    # Step 6: Write diagnostics (if enabled)
    if write_diagnostics:
        logger.info("Step 6: Writing diagnostic files")
        from .diagnostic_writer import write_all_diagnostics
        write_all_diagnostics(
            standings_data,
            denominators,
            baseline,
            df,
            player_type
        )

    return df


def calculate_category_sgp_denominator(
    standings_data: Dict[int, SeasonStandings],
    category: str
) -> SGPDenominators:
    """
    Calculate SGP denominator for a category with multi-year smoothing.

    Args:
        standings_data: Historical standings data
        category: Category name

    Returns:
        SGPDenominators object
    """
    # Calculate per-season denominators
    per_season = calculate_sgp_denominator_per_season(standings_data, category)

    if not per_season:
        raise ValueError(
            f"No valid seasons found for category {category}. "
            f"Check that category exists in historical data."
        )

    # Apply multi-year smoothing
    smoothed = apply_multi_year_smoothing(
        per_season,
        config.SGP_SEASON_WEIGHTS
    )

    seasons_used = list(per_season.keys())

    logger.info(
        f"{category}: smoothed denominator = {smoothed:.3f} "
        f"(from seasons {seasons_used})"
    )

    return SGPDenominators(
        category=category,
        per_season=per_season,
        smoothed=smoothed,
        seasons_used=seasons_used
    )


def apply_multi_year_smoothing(
    per_season_denominators: Dict[int, float],
    season_weights: Dict[int, float]
) -> float:
    """
    Calculate weighted average of denominators across seasons.

    More recent seasons are weighted higher to reflect current meta.

    Args:
        per_season_denominators: season -> denominator
        season_weights: season -> weight

    Returns:
        Smoothed denominator (weighted average)
    """
    weighted_sum = 0.0
    weight_total = 0.0

    for season, denominator in per_season_denominators.items():
        # Use weight from config, default to 1.0 if not specified
        weight = season_weights.get(season, 1.0)

        weighted_sum += denominator * weight
        weight_total += weight

    if weight_total == 0:
        raise ValueError("Total weight is zero, cannot calculate smoothed denominator")

    smoothed = weighted_sum / weight_total

    logger.debug(
        f"Smoothing: weighted_sum={weighted_sum:.3f}, "
        f"weight_total={weight_total:.1f}, "
        f"smoothed={smoothed:.3f}"
    )

    return smoothed
