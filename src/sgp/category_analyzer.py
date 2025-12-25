"""
Analyze historical category distributions and calculate SGP denominators.
"""

import logging
from dataclasses import dataclass
from typing import List, Dict
import numpy as np
import pandas as pd

from .league_data_loader import SeasonStandings, rank_teams_by_category

logger = logging.getLogger(__name__)


@dataclass
class CategoryGaps:
    """Gap analysis for a category in a single season."""
    category: str
    season: int
    gaps: List[float]  # All rank-to-rank gaps
    median_gap: float  # Median gap (SGP denominator)
    mean_gap: float    # Mean gap (for comparison)
    std_gap: float     # Standard deviation


def analyze_category_gaps(
    standings: SeasonStandings,
    category: str
) -> CategoryGaps:
    """
    Analyze rank-to-rank gaps for a category.

    For ratio categories (OBP, SLG, ERA, WHIP), converts to marginal impact units
    before calculating gaps.

    Args:
        standings: SeasonStandings for a single season
        category: Category name

    Returns:
        CategoryGaps object with gap analysis
    """
    # Rank teams by category
    ranked = rank_teams_by_category(standings, category)

    # For ratio categories, convert to marginal impact units
    if category in ['OBP', 'SLG', 'ERA', 'WHIP']:
        ranked = _convert_ratio_to_marginal(ranked, category, standings)

    # Calculate gaps between consecutive ranks
    gaps = []
    for i in range(len(ranked) - 1):
        team1_value = ranked.iloc[i][f'{category}_marginal'] if category in ['OBP', 'SLG', 'ERA', 'WHIP'] else ranked.iloc[i][category]
        team2_value = ranked.iloc[i + 1][f'{category}_marginal'] if category in ['OBP', 'SLG', 'ERA', 'WHIP'] else ranked.iloc[i + 1][category]

        # Gap is always positive (absolute difference)
        gap = abs(team1_value - team2_value)
        gaps.append(gap)

    # Calculate statistics
    median_gap = np.median(gaps)
    mean_gap = np.mean(gaps)
    std_gap = np.std(gaps)

    logger.debug(
        f"Season {standings.season}, {category}: "
        f"median={median_gap:.3f}, mean={mean_gap:.3f}, std={std_gap:.3f}"
    )

    return CategoryGaps(
        category=category,
        season=standings.season,
        gaps=gaps,
        median_gap=median_gap,
        mean_gap=mean_gap,
        std_gap=std_gap
    )


def calculate_sgp_denominator_per_season(
    standings_data: Dict[int, SeasonStandings],
    category: str
) -> Dict[int, float]:
    """
    Calculate SGP denominator for each season.

    Uses median gap method: median of rank-to-rank gaps.

    Args:
        standings_data: Dictionary of season -> SeasonStandings
        category: Category name

    Returns:
        Dictionary of season -> denominator
    """
    denominators = {}

    for season, standings in standings_data.items():
        # Skip if category not available in this season
        if category not in standings.categories:
            logger.debug(
                f"Category {category} not available in season {season}, skipping"
            )
            continue

        # Analyze gaps
        gap_analysis = analyze_category_gaps(standings, category)

        # Use median gap as denominator
        denominator = gap_analysis.median_gap

        # Sanity check
        if denominator <= 0:
            logger.warning(
                f"Season {season}, {category}: "
                f"Invalid denominator {denominator:.3f}, using mean gap"
            )
            denominator = gap_analysis.mean_gap

        if denominator <= 0:
            logger.error(
                f"Season {season}, {category}: "
                f"Cannot calculate valid denominator"
            )
            continue

        denominators[season] = denominator
        logger.info(
            f"Season {season}, {category}: denominator = {denominator:.3f}"
        )

    return denominators


def detect_outliers(gaps: List[float], method: str = 'iqr') -> List[int]:
    """
    Detect outlier gaps using IQR method.

    Args:
        gaps: List of rank-to-rank gaps
        method: 'iqr' (only method supported)

    Returns:
        List of indices of outlier gaps
    """
    if method != 'iqr':
        raise ValueError(f"Unsupported outlier detection method: {method}")

    q1 = np.percentile(gaps, 25)
    q3 = np.percentile(gaps, 75)
    iqr = q3 - q1

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    outliers = [
        i for i, gap in enumerate(gaps)
        if gap < lower_bound or gap > upper_bound
    ]

    return outliers


def get_gap_distribution_stats(gaps: List[float]) -> Dict[str, float]:
    """
    Calculate distribution statistics for gaps.

    Args:
        gaps: List of rank-to-rank gaps

    Returns:
        Dictionary of statistic name -> value
    """
    return {
        'min': np.min(gaps),
        'p25': np.percentile(gaps, 25),
        'median': np.median(gaps),
        'p75': np.percentile(gaps, 75),
        'max': np.max(gaps),
        'mean': np.mean(gaps),
        'std': np.std(gaps),
    }


def _convert_ratio_to_marginal(ranked: pd.DataFrame, category: str, standings: SeasonStandings) -> pd.DataFrame:
    """
    Convert ratio category values to marginal impact units.

    For ratio categories, we need to convert from ratios (e.g., 0.336 OBP) to
    marginal impacts (e.g., OBP × PA) so denominators match player calculations.

    Args:
        ranked: Ranked teams DataFrame
        category: Category name (OBP, SLG, ERA, WHIP)
        standings: SeasonStandings object

    Returns:
        DataFrame with marginal impact column added
    """
    df = ranked.copy()

    # Calculate league average for this category (baseline)
    league_avg = df[category].median()

    if category == 'OBP':
        # OBP marginal = (team_OBP - league_avg_OBP) × team_AB
        if 'AB' in df.columns:
            df[f'{category}_marginal'] = (df[category] - league_avg) * df['AB']
        else:
            # Fallback: use raw values
            logger.warning(f"Missing AB column for {category}, using raw values")
            df[f'{category}_marginal'] = df[category]

    elif category == 'SLG':
        # SLG marginal = (team_SLG - league_avg_SLG) × team_AB
        if 'AB' in df.columns:
            df[f'{category}_marginal'] = (df[category] - league_avg) * df['AB']
        else:
            logger.warning(f"Missing AB column for {category}, using raw values")
            df[f'{category}_marginal'] = df[category]

    elif category == 'ERA':
        # ERA marginal = (league_avg_ERA - team_ERA) × team_IP (inverted: lower is better)
        if 'IP' in df.columns:
            df[f'{category}_marginal'] = (league_avg - df[category]) * df['IP']
        else:
            logger.warning(f"Missing IP column for {category}, using raw values")
            df[f'{category}_marginal'] = -df[category]  # Invert for lower-is-better

    elif category == 'WHIP':
        # WHIP marginal = (league_avg_WHIP - team_WHIP) × team_IP (inverted: lower is better)
        if 'IP' in df.columns:
            df[f'{category}_marginal'] = (league_avg - df[category]) * df['IP']
        else:
            logger.warning(f"Missing IP column for {category}, using raw values")
            df[f'{category}_marginal'] = -df[category]  # Invert for lower-is-better

    return df
