"""
Greedy position assignment for live draft events.

Provides fast, incremental position assignment during live draft.
Different from PositionOptimizer which performs batch optimization.

Strategy:
- Assign players to positions one at a time in draft order
- Prioritize specific positions over utility/bench
- Among specific positions, choose the most scarce
- Fast enough for real-time processing (~50-100ms per assignment)
"""

from typing import Dict, List, Set, Optional
import logging

from .league_schema import PlayerState
from .. import config

logger = logging.getLogger(__name__)


class PositionAssigner:
    """Greedy position assignment for live draft."""

    def __init__(self, open_slots: Dict[str, int]):
        """
        Initialize position assigner with current slot availability.

        Args:
            open_slots: Mapping of position to number of open slots
        """
        self.open_slots = open_slots.copy()
        logger.debug(f"Initialized PositionAssigner with slots: {self.open_slots}")

    def assign_position(
        self,
        player: PlayerState,
        player_type: str
    ) -> str:
        """
        Assign a player to a position using greedy algorithm.

        Strategy:
        1. Expand position eligibility (e.g., LF/CF/RF → OF)
        2. Filter to positions with open slots
        3. Prioritize: specific positions > UTIL > BN
        4. Among specific positions, choose least available (most scarce)

        Args:
            player: Player to assign
            player_type: 'hitter' or 'pitcher'

        Returns:
            Assigned position

        Raises:
            ValueError: If no positions available
        """
        # Expand eligibility
        eligible = self._expand_eligibility(player.eligible_positions, player_type)

        # Filter to positions with open slots
        available = [pos for pos in eligible if self.open_slots.get(pos, 0) > 0]

        if not available:
            raise ValueError(
                f"No available roster slots for {player.player_name} "
                f"(eligible: {player.eligible_positions}, type: {player_type})"
            )

        # Categorize positions
        specific = [p for p in available if p not in ['UTIL', 'BN_H', 'BN_P']]
        util = [p for p in available if p == 'UTIL']
        bench = [p for p in available if p in ['BN_H', 'BN_P']]

        # Priority 1: Specific positions (choose most scarce)
        if specific:
            # Choose position with fewest open slots (most scarce)
            assigned = min(specific, key=lambda p: self.open_slots[p])

        # Priority 2: UTIL slot
        elif util:
            assigned = 'UTIL'

        # Priority 3: Bench slot
        elif bench:
            assigned = bench[0]  # BN_H or BN_P

        else:
            # Should never reach here due to available check above
            raise ValueError(f"No assignment found for {player.player_name}")

        # Update open slots
        self.open_slots[assigned] -= 1

        logger.debug(
            f"Assigned {player.player_name} to {assigned} "
            f"({self.open_slots[assigned]} slots remaining)"
        )

        return assigned

    def _expand_eligibility(
        self,
        positions: List[str],
        player_type: str
    ) -> Set[str]:
        """
        Expand position eligibility to include UTIL and bench slots.

        Args:
            positions: Player's eligible positions
            player_type: 'hitter' or 'pitcher'

        Returns:
            Set of all eligible roster slots
        """
        eligible = set(positions)

        if player_type == 'hitter':
            # All hitters eligible for UTIL and BN_H
            eligible.add('UTIL')
            eligible.add('BN_H')

            # Handle OF sub-positions (LF, CF, RF → OF)
            of_positions = {'LF', 'CF', 'RF', 'OF'}
            if any(pos in positions for pos in of_positions):
                eligible.add('OF')

            # Handle DH (also eligible for UTIL)
            if 'DH' in positions:
                eligible.add('UTIL')

        elif player_type == 'pitcher':
            # All pitchers eligible for P and BN_P
            eligible.add('P')
            eligible.add('BN_P')

            # Handle SP/RP positions
            if any(pos in positions for pos in ['SP', 'RP', 'P']):
                eligible.add('P')

        else:
            raise ValueError(f"Unknown player_type: {player_type}")

        return eligible

    def get_remaining_slots(self) -> Dict[str, int]:
        """
        Get current open slot counts.

        Returns:
            Copy of open_slots dict
        """
        return self.open_slots.copy()

    def validate_slots(self) -> None:
        """
        Validate slot counts are consistent.

        Raises:
            ValueError: If any position has negative slots
        """
        for position, count in self.open_slots.items():
            if count < 0:
                raise ValueError(
                    f"Position {position} has negative open slots: {count}"
                )

        logger.debug("Position slot validation passed")

    def total_remaining(self) -> int:
        """
        Calculate total remaining roster spots across all positions.

        Returns:
            Sum of all open slots
        """
        return sum(self.open_slots.values())


def determine_player_type(player: PlayerState) -> str:
    """
    Determine if a player is a hitter or pitcher based on positions.

    Args:
        player: Player to classify

    Returns:
        'hitter' or 'pitcher'

    Raises:
        ValueError: If player type cannot be determined
    """
    positions_set = set(player.eligible_positions)

    # Check for hitter positions
    hitter_positions = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH', 'UTIL'}
    is_hitter = bool(positions_set & hitter_positions)

    # Check for pitcher positions
    pitcher_positions = {'P', 'SP', 'RP'}
    is_pitcher = bool(positions_set & pitcher_positions)

    # Resolve conflicts (shouldn't happen, but handle gracefully)
    if is_hitter and is_pitcher:
        # Two-way player - treat as hitter by default (e.g., Ohtani)
        logger.warning(
            f"Player {player.player_name} has both hitter and pitcher positions. "
            f"Treating as hitter."
        )
        return 'hitter'
    elif is_hitter:
        return 'hitter'
    elif is_pitcher:
        return 'pitcher'
    else:
        raise ValueError(
            f"Cannot determine player type for {player.player_name}: "
            f"positions={player.eligible_positions}"
        )


def create_position_assigner_from_teams(teams: Dict[str, 'TeamState']) -> PositionAssigner:
    """
    Create a PositionAssigner from current team states.

    Aggregates open_slots across all teams to get league-wide availability.

    Args:
        teams: Dictionary of TeamState objects

    Returns:
        PositionAssigner initialized with aggregated open slots
    """
    total_open_slots = {}

    for team in teams.values():
        for position, count in team.open_slots.items():
            total_open_slots[position] = total_open_slots.get(position, 0) + count

    return PositionAssigner(total_open_slots)
