"""
Standings Gain Points (SGP) calculation module.

This package implements SGP-based player valuation for fantasy baseball,
replacing z-score normalization with league-calibrated standings impact.
"""

from .league_data_loader import load_historical_standings, SeasonStandings
from .sgp_calculator import calculate_sgp_values

__all__ = [
    'load_historical_standings',
    'SeasonStandings',
    'calculate_sgp_values',
]
