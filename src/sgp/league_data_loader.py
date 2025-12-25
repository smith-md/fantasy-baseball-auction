"""
Load and validate historical league standings data for SGP calculation.
"""

import os
import logging
from dataclasses import dataclass
from typing import Dict, List
import pandas as pd

from .. import config

logger = logging.getLogger(__name__)


@dataclass
class SeasonStandings:
    """Historical standings data for a single season."""
    season: int
    teams: pd.DataFrame
    categories: List[str]


def load_historical_standings(
    seasons: List[int] = None,
    data_dir: str = None
) -> Dict[int, SeasonStandings]:
    """
    Load historical league standings from CSV files.

    Args:
        seasons: List of seasons to load (default: from config.SGP_SEASONS)
        data_dir: Directory containing standings CSVs (default: from config.SGP_DATA_DIR)

    Returns:
        Dictionary mapping season -> SeasonStandings

    Raises:
        ValueError: If insufficient seasons available or data validation fails
    """
    if seasons is None:
        seasons = config.SGP_SEASONS
    if data_dir is None:
        data_dir = config.SGP_DATA_DIR

    logger.info(f"Loading historical standings for seasons: {seasons}")

    standings_by_season = {}

    for season in seasons:
        file_path = os.path.join(data_dir, f'league_{season}_combined.csv')

        if not os.path.exists(file_path):
            logger.warning(f"Missing data for season {season}: {file_path}")
            continue

        logger.info(f"Loading {file_path}")
        df = pd.read_csv(file_path)

        # Validate data
        if not validate_standings_data(df, season):
            logger.warning(f"Validation failed for season {season}, skipping")
            continue

        # Detect categories available for this season
        categories = detect_categories(df, season)

        standings_by_season[season] = SeasonStandings(
            season=season,
            teams=df,
            categories=categories
        )

        logger.info(f"Loaded {len(df)} teams with categories: {categories}")

    # Validate we have enough seasons
    if len(standings_by_season) < 1:
        raise ValueError(
            f"Need at least 1 season of data for SGP calculation. "
            f"Found {len(standings_by_season)} seasons."
        )

    logger.info(f"Successfully loaded {len(standings_by_season)} seasons")
    return standings_by_season


def validate_standings_data(df: pd.DataFrame, season: int) -> bool:
    """
    Validate standings data integrity.

    Args:
        df: Standings DataFrame
        season: Season year

    Returns:
        True if validation passes, False otherwise
    """
    # Check team count
    if len(df) != config.NUM_TEAMS:
        logger.error(
            f"Season {season}: Expected {config.NUM_TEAMS} teams, found {len(df)}"
        )
        return False

    # Check for required columns
    required_base = ['Team']  # Manager is optional
    missing_cols = [col for col in required_base if col not in df.columns]
    if missing_cols:
        logger.error(f"Season {season}: Missing required columns: {missing_cols}")
        return False

    # Check for duplicate teams
    if df['Team'].duplicated().any():
        logger.error(f"Season {season}: Duplicate team names found")
        return False

    return True


def detect_categories(df: pd.DataFrame, season: int) -> List[str]:
    """
    Detect which scoring categories are available in this season's data.

    Handles category versioning (SV vs SV_HLD).

    Args:
        df: Standings DataFrame
        season: Season year

    Returns:
        List of category names available
    """
    categories = []

    # Hitter counting categories
    for cat in ['R', 'RBI', 'SB']:
        if cat in df.columns:
            categories.append(cat)

    # Hitter rate categories
    for cat in ['OBP', 'SLG']:
        if cat in df.columns:
            categories.append(cat)

    # Pitcher counting categories
    if 'K' in df.columns:
        categories.append('K')
    elif 'SO' in df.columns:
        # FanGraphs uses 'SO', map to 'K'
        df['K'] = df['SO']
        categories.append('K')

    # W+QS category
    if 'W_QS' in df.columns:
        categories.append('W_QS')
    elif 'W' in df.columns and 'QS' in df.columns:
        # Calculate W+QS if not provided
        df['W_QS'] = df['W'] + df['QS']
        categories.append('W_QS')

    # SV+HLD category (version-dependent)
    if season >= 2025:
        # 2025+: Use combined SV+HLD
        if 'SV_HLD' in df.columns:
            categories.append('SV_HLD')
        elif 'SVH' in df.columns:
            # Alternative column name
            df['SV_HLD'] = df['SVH']
            categories.append('SV_HLD')
        elif 'SV' in df.columns and 'HLD' in df.columns:
            # Calculate if separate
            df['SV_HLD'] = df['SV'] + df['HLD']
            categories.append('SV_HLD')
    else:
        # Pre-2025: Try to create SV_HLD if both components exist
        # This allows using historical data if holds are available
        if 'SV' in df.columns and 'HLD' in df.columns:
            df['SV_HLD'] = df['SV'] + df['HLD']
            categories.append('SV_HLD')
        elif 'SV' in df.columns:
            # If only SV available, we can't use it for SV_HLD denominator
            # Log this but don't include in categories for SV_HLD
            logger.info(f"Season {season}: Only SV available (no HLD), cannot use for SV_HLD")

    # Pitcher rate categories
    for cat in ['ERA', 'WHIP']:
        if cat in df.columns:
            categories.append(cat)

    logger.info(f"Season {season}: Detected categories {categories}")
    return categories


def rank_teams_by_category(
    standings: SeasonStandings,
    category: str,
    ascending: bool = False
) -> pd.DataFrame:
    """
    Rank teams by a specific category.

    Args:
        standings: SeasonStandings object
        category: Category name to rank by
        ascending: True for ERA/WHIP (lower is better), False otherwise

    Returns:
        DataFrame sorted by category with rank column
    """
    if category not in standings.categories:
        raise ValueError(
            f"Category {category} not available in season {standings.season}"
        )

    # For ERA and WHIP, lower is better
    if category in ['ERA', 'WHIP']:
        ascending = True
    else:
        ascending = False

    # Sort teams by category
    ranked = standings.teams.sort_values(
        by=category,
        ascending=ascending
    ).copy()

    # Add rank column (1-12)
    ranked['rank'] = range(1, len(ranked) + 1)

    return ranked


def get_categories_for_player_type(player_type: str) -> List[str]:
    """
    Get list of categories for a player type.

    Args:
        player_type: 'hitters' or 'pitchers'

    Returns:
        List of category names
    """
    if player_type == 'hitters':
        return config.HITTER_CATEGORIES
    elif player_type == 'pitchers':
        return config.PITCHER_CATEGORIES
    else:
        raise ValueError(f"Invalid player_type: {player_type}")
