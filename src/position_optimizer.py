"""
Optimize player-to-position assignments to maximize total value.

Uses a greedy algorithm to assign players to roster positions based on
positional scarcity and raw value.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Set

from . import config


class PositionOptimizer:
    """Assigns players to positions using a greedy scarcity-based algorithm."""

    def __init__(self, hitters_df: pd.DataFrame, pitchers_df: pd.DataFrame):
        """
        Initialize the position optimizer.

        Args:
            hitters_df: DataFrame with hitter projections and raw_value
            pitchers_df: DataFrame with pitcher projections and raw_value
        """
        self.hitters_df = hitters_df.copy()
        self.pitchers_df = pitchers_df.copy()

        # Initialize remaining slots (will be modified during assignment)
        self.remaining_slots = config.ROSTER_SLOTS.copy()

        # Track assignments
        self.assignments = []
        self.assigned_player_ids = set()

    def _is_hitter_position(self, position: str) -> bool:
        """Check if a position is a hitter position."""
        return position in config.HITTER_POSITIONS

    def _is_pitcher_position(self, position: str) -> bool:
        """Check if a position is a pitcher position."""
        return position in config.PITCHER_POSITIONS

    def _expand_position_eligibility(self, positions: List[str], player_type: str) -> Set[str]:
        """
        Expand position eligibility to include UTIL and bench slots.

        Args:
            positions: List of player's eligible positions
            player_type: 'hitter' or 'pitcher'

        Returns:
            Set of all eligible roster slots
        """
        eligible = set(positions)

        if player_type == 'hitter':
            # Hitters are eligible for UTIL and BN_H
            eligible.add('UTIL')
            eligible.add('BN_H')

            # Handle OF eligibility (player might have specific OF like LF, CF, RF)
            # Map them all to OF
            of_positions = ['LF', 'CF', 'RF', 'OF']
            if any(pos in positions for pos in of_positions):
                eligible.add('OF')

        elif player_type == 'pitcher':
            # All pitchers are eligible for P and BN_P
            eligible.add('P')
            eligible.add('BN_P')

            # Handle SP/RP positions
            if 'SP' in positions or 'RP' in positions or 'P' in positions:
                eligible.add('P')

        return eligible

    def _calculate_scarcity(self, position: str, remaining_players: pd.DataFrame,
                           player_type: str) -> float:
        """
        Calculate scarcity score for a position.

        Scarcity = remaining_slots / remaining_eligible_players
        Higher scarcity = fewer slots relative to eligible players = more scarce

        Args:
            position: Position to calculate scarcity for
            remaining_players: DataFrame of players not yet assigned
            player_type: 'hitter' or 'pitcher'

        Returns:
            Scarcity score (higher = more scarce)
        """
        if self.remaining_slots[position] <= 0:
            return 0.0

        # Count remaining players eligible for this position
        eligible_count = 0
        for _, player in remaining_players.iterrows():
            eligible_positions = self._expand_position_eligibility(
                player['positions'],
                player_type
            )
            if position in eligible_positions:
                eligible_count += 1

        if eligible_count == 0:
            return 0.0

        # Scarcity = remaining slots / eligible players
        # Lower ratio = more scarce (fewer slots per player)
        # We want to fill scarce positions first, so invert
        scarcity = self.remaining_slots[position] / eligible_count

        return scarcity

    def _assign_players(self, df: pd.DataFrame, player_type: str):
        """
        Assign players to positions using greedy algorithm.

        Args:
            df: DataFrame with player projections and raw_value
            player_type: 'hitter' or 'pitcher'
        """
        # Sort by raw_value descending
        df_sorted = df.sort_values('raw_value', ascending=False).reset_index(drop=True)

        # Track player index for efficient filtering
        remaining_indices = set(df_sorted.index)

        print(f"\nAssigning {len(df_sorted)} {player_type}s to positions...")

        # Determine which positions are relevant for this player type
        if player_type == 'hitter':
            relevant_positions = [pos for pos in config.ROSTER_SLOTS.keys()
                                if self._is_hitter_position(pos)]
        else:
            relevant_positions = [pos for pos in config.ROSTER_SLOTS.keys()
                                if self._is_pitcher_position(pos)]

        # Calculate total slots to fill for this player type
        total_slots = sum(self.remaining_slots[pos] for pos in relevant_positions)

        assignments_made = 0

        # Continue until all slots filled or no more players
        while assignments_made < total_slots and remaining_indices:
            # Get remaining players DataFrame
            remaining_df = df_sorted.loc[list(remaining_indices)]

            if remaining_df.empty:
                break

            # Process players in order of raw_value
            assigned_this_round = False

            for idx in sorted(remaining_indices,
                            key=lambda i: df_sorted.loc[i, 'raw_value'],
                            reverse=True):

                player = df_sorted.loc[idx]

                # Get eligible positions
                positions = player['positions'] if isinstance(player['positions'], list) else []
                eligible_positions = self._expand_position_eligibility(positions, player_type)

                # Filter to positions with remaining slots
                available_positions = [pos for pos in eligible_positions
                                     if pos in relevant_positions
                                     and self.remaining_slots.get(pos, 0) > 0]

                if not available_positions:
                    continue

                # Calculate scarcity for each available position
                scarcity_scores = {}
                for pos in available_positions:
                    scarcity = self._calculate_scarcity(pos, remaining_df, player_type)
                    scarcity_scores[pos] = scarcity

                # Assign to most scarce position (lowest scarcity score)
                best_position = min(scarcity_scores, key=scarcity_scores.get)

                # Record assignment
                self.assignments.append({
                    'player_id': player.get('player_id', idx),
                    'player_name': player.get('player_name', 'Unknown'),
                    'player_type': player_type,
                    'positions': positions,
                    'assigned_position': best_position,
                    'raw_value': player['raw_value'],
                })

                # Update remaining slots
                self.remaining_slots[best_position] -= 1
                remaining_indices.remove(idx)
                assignments_made += 1
                assigned_this_round = True

                # Check if all slots filled
                if assignments_made >= total_slots:
                    break

            # If no assignments made this round, break to avoid infinite loop
            if not assigned_this_round:
                print(f"Warning: Could not assign {len(remaining_indices)} {player_type}s")
                break

        print(f"Assigned {assignments_made} {player_type}s to positions")

        # Print remaining slots
        print("\nRemaining slots after assignment:")
        for pos in relevant_positions:
            remaining = self.remaining_slots.get(pos, 0)
            if remaining > 0:
                print(f"  {pos}: {remaining}")

    def optimize(self) -> pd.DataFrame:
        """
        Run the optimization to assign all players to positions.

        Returns:
            DataFrame with assignment results
        """
        print("Starting position assignment optimization...")

        # Assign hitters first
        self._assign_players(self.hitters_df, 'hitter')

        # Then assign pitchers
        self._assign_players(self.pitchers_df, 'pitcher')

        # Convert assignments to DataFrame
        assignments_df = pd.DataFrame(self.assignments)

        print(f"\nTotal players assigned: {len(assignments_df)}")

        return assignments_df


def optimize_positions(hitters_df: pd.DataFrame,
                      pitchers_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convenience function to optimize position assignments.

    Args:
        hitters_df: Hitter projections with raw_value
        pitchers_df: Pitcher projections with raw_value

    Returns:
        DataFrame with position assignments
    """
    optimizer = PositionOptimizer(hitters_df, pitchers_df)
    return optimizer.optimize()
