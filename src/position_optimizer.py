"""
Optimize player-to-position assignments to maximize total value.

Uses a greedy algorithm to assign players to roster positions based on
positional scarcity and raw value.
"""

import pandas as pd
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

    def _assign_players(self, df: pd.DataFrame, player_type: str, extra_slots: int = 0):
        """
        Assign players to positions using tier-based greedy algorithm.

        Players are processed in descending raw_value order. Each player is
        assigned to the best available position using a priority system:
          Tier 1: Specific positions (C, 1B, 2B, 3B, SS, OF) -- prefer most scarce
          Tier 2: UTIL slot
          Tier 3: Bench (BN_H / BN_P)

        For pitchers: P -> BN_P (two tiers).

        After filling real roster slots, continues assigning fringe players up to
        extra_slots, using a bench position without decrementing slot counts.

        Args:
            df: DataFrame with player projections and raw_value
            player_type: 'hitter' or 'pitcher'
            extra_slots: Additional fringe players to include beyond real roster slots
        """
        df_sorted = df.sort_values('raw_value', ascending=False).reset_index(drop=True)

        print(f"\nAssigning {len(df_sorted)} {player_type}s to positions...")

        # Determine which positions are relevant for this player type
        if player_type == 'hitter':
            relevant_positions = {pos for pos in config.ROSTER_SLOTS
                                  if self._is_hitter_position(pos)}
            default_fringe_position = 'BN_H'
        else:
            relevant_positions = {pos for pos in config.ROSTER_SLOTS
                                  if self._is_pitcher_position(pos)}
            default_fringe_position = 'BN_P'

        total_slots = sum(self.remaining_slots[pos] for pos in relevant_positions)
        assignments_made = 0
        fringe_assigned = 0

        for _, player in df_sorted.iterrows():
            if assignments_made >= total_slots and fringe_assigned >= extra_slots:
                break

            positions = player['positions'] if isinstance(player['positions'], list) else []
            eligible = self._expand_position_eligibility(positions, player_type)
            player_id = player.get('player_id')

            if assignments_made < total_slots:
                # Normal assignment -- fill real roster slots
                available = [pos for pos in eligible
                             if pos in relevant_positions
                             and self.remaining_slots.get(pos, 0) > 0]

                if not available:
                    continue

                specific = [p for p in available if p not in ('UTIL', 'BN_H', 'BN_P')]
                util = [p for p in available if p == 'UTIL']
                bench = [p for p in available if p in ('BN_H', 'BN_P')]

                if specific:
                    best_position = min(specific, key=lambda p: self.remaining_slots[p])
                elif util:
                    best_position = 'UTIL'
                elif bench:
                    best_position = bench[0]
                else:
                    continue

                self.remaining_slots[best_position] -= 1
                assignments_made += 1
                is_rostered = True
            else:
                # Fringe assignment -- beyond real roster slots, no slot tracking
                if player_id in self.assigned_player_ids:
                    continue
                best_position = default_fringe_position
                fringe_assigned += 1
                is_rostered = False

            self.assignments.append({
                'player_id': player_id,
                'player_name': player.get('player_name', 'Unknown'),
                'player_type': player_type,
                'positions': positions,
                'assigned_position': best_position,
                'raw_value': player['raw_value'],
                'is_rostered': is_rostered,
            })
            self.assigned_player_ids.add(player_id)

        print(f"Assigned {assignments_made} rostered + {fringe_assigned} fringe {player_type}s")

        # Print remaining slots
        print("\nRemaining slots after assignment:")
        for pos in sorted(relevant_positions):
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

        # Calculate extra fringe slots, split proportionally between hitters and pitchers
        extra = max(0, config.PLAYER_POOL_SIZE - config.TOTAL_PLAYERS)
        hitter_extra = round(extra * config.TOTAL_HITTERS / config.TOTAL_PLAYERS)
        pitcher_extra = extra - hitter_extra

        # Assign hitters first
        self._assign_players(self.hitters_df, 'hitter', extra_slots=hitter_extra)

        # Then assign pitchers
        self._assign_players(self.pitchers_df, 'pitcher', extra_slots=pitcher_extra)

        # Convert assignments to DataFrame
        assignments_df = pd.DataFrame(self.assignments)

        print(f"\nTotal players in pool: {len(assignments_df)} ({config.TOTAL_PLAYERS} rostered + {extra} fringe)")

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
