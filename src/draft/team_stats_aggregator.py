"""
Team statistics aggregation.

Aggregates individual player projections into team-level statistics
compatible with the TeamStats schema.
"""

import pandas as pd
from typing import Dict, List
import logging

from .league_schema import TeamStats, PlayerState
from .. import config

logger = logging.getLogger(__name__)


class TeamStatsAggregator:
    """Aggregates player projections into team statistics."""

    def __init__(self, hitters_df: pd.DataFrame, pitchers_df: pd.DataFrame):
        """
        Initialize aggregator with projection data.

        Args:
            hitters_df: DataFrame with hitter projections
            pitchers_df: DataFrame with pitcher projections
        """
        # Create lookup dict for fast player stat access
        self.player_stats = {}

        # Index hitters by player_id
        for _, player in hitters_df.iterrows():
            player_id = str(player['player_id'])
            self.player_stats[player_id] = player.to_dict()

        # Index pitchers by player_id
        for _, player in pitchers_df.iterrows():
            player_id = str(player['player_id'])
            self.player_stats[player_id] = player.to_dict()

        logger.debug(f"Initialized stats aggregator with {len(self.player_stats)} players")

    def aggregate_team_stats(
        self,
        roster: Dict[str, List[str]],
        player_pool: Dict[str, PlayerState]
    ) -> TeamStats:
        """
        Aggregate stats for all players on a team's roster.

        Args:
            roster: Position-based roster (position -> [player_ids])
            player_pool: Complete player pool for validation

        Returns:
            TeamStats with aggregated counting and rate stat components

        Raises:
            ValueError: If player not found in stats lookup
        """
        # Initialize accumulators
        counting_stats = {
            'R': 0.0,
            'RBI': 0.0,
            'SB': 0.0,
            'W_QS': 0.0,  # W + QS
            'SV_HLD': 0.0,  # SV + HLD
            'K': 0.0,
        }

        rate_numerators = {
            'OBP_num': 0.0,  # H + BB + HBP
            'SLG_num': 0.0,  # TB
            'ERA_num': 0.0,  # ER
            'WHIP_num': 0.0,  # H + BB
        }

        rate_denominators = {
            'PA': 0.0,  # For OBP
            'AB': 0.0,  # For SLG
            'IP': 0.0,  # For ERA and WHIP
        }

        # Iterate through all roster positions
        for position, player_ids in roster.items():
            for player_id in player_ids:
                # Validate player exists in pool
                if player_id not in player_pool:
                    raise ValueError(f"Player {player_id} in roster but not in player pool")

                # Get player stats
                if player_id not in self.player_stats:
                    raise ValueError(
                        f"Player {player_id} ({player_pool[player_id].player_name}) "
                        f"not found in projection data"
                    )

                stats = self.player_stats[player_id]

                # Determine player type based on available stats
                is_hitter = 'PA' in stats and pd.notna(stats.get('PA'))
                is_pitcher = 'IP' in stats and pd.notna(stats.get('IP'))

                if is_hitter:
                    self._aggregate_hitter(stats, counting_stats, rate_numerators, rate_denominators)

                if is_pitcher:
                    self._aggregate_pitcher(stats, counting_stats, rate_numerators, rate_denominators)

        return TeamStats(
            counting=counting_stats,
            rate_numerators=rate_numerators,
            rate_denominators=rate_denominators
        )

    def aggregate_for_player_ids(
        self,
        player_ids: set,
        player_pool: Dict[str, PlayerState]
    ) -> TeamStats:
        """
        Aggregate stats for a specific set of player_ids.

        Used for optimal lineup selection in standings projection — avoids
        relying on roster slot assignment order.

        Args:
            player_ids: Set of player IDs to aggregate
            player_pool: Complete player pool for validation

        Returns:
            TeamStats with aggregated counting and rate stat components
        """
        # Initialize accumulators (identical to aggregate_team_stats)
        counting_stats = {
            'R': 0.0,
            'RBI': 0.0,
            'SB': 0.0,
            'W_QS': 0.0,
            'SV_HLD': 0.0,
            'K': 0.0,
        }

        rate_numerators = {
            'OBP_num': 0.0,
            'SLG_num': 0.0,
            'ERA_num': 0.0,
            'WHIP_num': 0.0,
        }

        rate_denominators = {
            'PA': 0.0,
            'AB': 0.0,
            'IP': 0.0,
        }

        for player_id in player_ids:
            if player_id not in player_pool:
                logger.warning(f"Player {player_id} in lineup set but not in player pool — skipping")
                continue

            if player_id not in self.player_stats:
                logger.warning(
                    f"Player {player_id} ({player_pool[player_id].player_name}) "
                    f"not found in projection data — skipping"
                )
                continue

            stats = self.player_stats[player_id]

            is_hitter = 'PA' in stats and pd.notna(stats.get('PA'))
            is_pitcher = 'IP' in stats and pd.notna(stats.get('IP'))

            if is_hitter:
                self._aggregate_hitter(stats, counting_stats, rate_numerators, rate_denominators)

            if is_pitcher:
                self._aggregate_pitcher(stats, counting_stats, rate_numerators, rate_denominators)

        return TeamStats(
            counting=counting_stats,
            rate_numerators=rate_numerators,
            rate_denominators=rate_denominators
        )

    def _aggregate_hitter(
        self,
        stats: dict,
        counting_stats: dict,
        rate_numerators: dict,
        rate_denominators: dict
    ) -> None:
        """
        Aggregate a hitter's stats.

        Args:
            stats: Player stats dict
            counting_stats: Accumulator for counting stats (modified in place)
            rate_numerators: Accumulator for rate numerators (modified in place)
            rate_denominators: Accumulator for rate denominators (modified in place)
        """
        # Counting stats
        counting_stats['R'] += self._get_stat(stats, 'R')
        counting_stats['RBI'] += self._get_stat(stats, 'RBI')
        counting_stats['SB'] += self._get_stat(stats, 'SB')

        # Rate stat components
        pa = self._get_stat(stats, 'PA')
        ab = self._get_stat(stats, 'AB')
        h = self._get_stat(stats, 'H')
        bb = self._get_stat(stats, 'BB')
        hbp = self._get_stat(stats, 'HBP')

        # FanGraphs does not provide TB directly — compute from SLG * AB
        slg = self._get_stat(stats, 'SLG')
        tb = slg * ab

        # OBP components
        rate_numerators['OBP_num'] += (h + bb + hbp)
        rate_denominators['PA'] += pa

        # SLG components
        rate_numerators['SLG_num'] += tb
        rate_denominators['AB'] += ab

    def _aggregate_pitcher(
        self,
        stats: dict,
        counting_stats: dict,
        rate_numerators: dict,
        rate_denominators: dict
    ) -> None:
        """
        Aggregate a pitcher's stats.

        Args:
            stats: Player stats dict
            counting_stats: Accumulator for counting stats (modified in place)
            rate_numerators: Accumulator for rate numerators (modified in place)
            rate_denominators: Accumulator for rate denominators (modified in place)
        """
        # Counting stats
        # W_QS = Wins + Quality Starts
        w = self._get_stat(stats, 'W')
        qs = self._get_stat(stats, 'QS')
        counting_stats['W_QS'] += (w + qs)

        # SV_HLD = Saves + Holds
        sv = self._get_stat(stats, 'SV')
        hld = self._get_stat(stats, 'HLD')
        counting_stats['SV_HLD'] += (sv + hld)

        # K = Strikeouts (FanGraphs uses 'SO')
        so = self._get_stat(stats, 'SO', alternative='K')
        counting_stats['K'] += so

        # Rate stat components
        ip = self._get_stat(stats, 'IP')
        er = self._get_stat(stats, 'ER')
        h = self._get_stat(stats, 'H')
        bb = self._get_stat(stats, 'BB')

        # ERA components (stored as raw ER, will multiply by 9 when calculating rate)
        rate_numerators['ERA_num'] += er

        # WHIP components (H + BB)
        rate_numerators['WHIP_num'] += (h + bb)

        # Shared denominator (IP)
        rate_denominators['IP'] += ip

    def _get_stat(self, stats: dict, stat_name: str, alternative: str = None) -> float:
        """
        Safely get a stat value from dict.

        Args:
            stats: Player stats dict
            stat_name: Primary stat name to look up
            alternative: Alternative stat name if primary not found

        Returns:
            Stat value (0.0 if missing or NaN)
        """
        value = stats.get(stat_name)

        # Try alternative if primary is None or NaN
        if (value is None or pd.isna(value)) and alternative:
            value = stats.get(alternative)

        # Return 0.0 if still None or NaN
        if value is None or pd.isna(value):
            return 0.0

        return float(value)

    def get_player_stats(self, player_id: str) -> dict:
        """
        Get raw stats for a specific player.

        Args:
            player_id: Player ID to look up

        Returns:
            Player stats dict

        Raises:
            ValueError: If player not found
        """
        if player_id not in self.player_stats:
            raise ValueError(f"Player {player_id} not found in stats")

        return self.player_stats[player_id]

    def calculate_team_rate_stats(self, team_stats: TeamStats) -> Dict[str, float]:
        """
        Calculate rate stats from aggregated components.

        Args:
            team_stats: TeamStats with aggregated numerators/denominators

        Returns:
            Dict with calculated rate stats (OBP, SLG, ERA, WHIP)
        """
        return team_stats.calculate_rate_stats()
