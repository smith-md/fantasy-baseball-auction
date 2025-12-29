"""
Allocate auction dollars based on value above replacement (VAR).

Implements dynamic hitter/pitcher split based on total value generated.
"""

import pandas as pd
import numpy as np

from . import config


class DollarAllocator:
    """Allocates auction dollars to players based on VAR."""

    def __init__(self, assignments_df: pd.DataFrame,
                 total_budget: int = None,
                 total_players: int = None):
        """
        Initialize the dollar allocator.

        Args:
            assignments_df: DataFrame with VAR calculated
            total_budget: Total league budget (default from config)
            total_players: Total players to draft (default from config)
        """
        self.assignments_df = assignments_df.copy()
        self.total_budget = total_budget or config.TOTAL_BUDGET
        self.total_players = total_players or config.TOTAL_PLAYERS

        # Calculate dollars available for allocation
        self.minimum_spend = self.total_players * config.MINIMUM_BID
        self.dollars_to_allocate = self.total_budget - self.minimum_spend

    def calculate_split(self) -> tuple:
        """
        Calculate dynamic hitter/pitcher dollar split based on VAR.

        Returns:
            Tuple of (hitter_dollars, pitcher_dollars)
        """
        # Calculate total VAR for hitters and pitchers
        hitter_var = self.assignments_df[
            self.assignments_df['player_type'] == 'hitter'
        ]['VAR'].sum()

        pitcher_var = self.assignments_df[
            self.assignments_df['player_type'] == 'pitcher'
        ]['VAR'].sum()

        total_var = hitter_var + pitcher_var

        if total_var == 0:
            # Edge case: no positive VAR, split evenly
            print("Warning: Total VAR is 0, splitting budget evenly")
            hitter_dollars = self.dollars_to_allocate / 2
            pitcher_dollars = self.dollars_to_allocate / 2
        else:
            # Allocate proportionally to VAR
            hitter_dollars = self.dollars_to_allocate * (hitter_var / total_var)
            pitcher_dollars = self.dollars_to_allocate * (pitcher_var / total_var)

        print(f"\nDynamic budget allocation:")
        print(f"Total budget: ${self.total_budget}")
        print(f"Minimum spend: ${self.minimum_spend} ({self.total_players} players × ${config.MINIMUM_BID})")
        print(f"Dollars to allocate: ${self.dollars_to_allocate}")
        print(f"\nHitter VAR: {hitter_var:.2f} -> ${hitter_dollars:.2f} ({hitter_dollars/self.dollars_to_allocate*100:.1f}%)")
        print(f"Pitcher VAR: {pitcher_var:.2f} -> ${pitcher_dollars:.2f} ({pitcher_dollars/self.dollars_to_allocate*100:.1f}%)")

        return hitter_dollars, pitcher_dollars

    def allocate_dollars(self) -> pd.DataFrame:
        """
        Allocate auction dollars to each player.

        Formula:
        auction_price = $1 + (player_VAR / total_VAR_in_group) × group_dollars

        Returns:
            DataFrame with auction_value column added
        """
        hitter_dollars, pitcher_dollars = self.calculate_split()

        # Calculate auction value for each player
        auction_values = []

        for _, player in self.assignments_df.iterrows():
            player_type = player['player_type']
            var = player['VAR']

            if var == 0:
                # Players with VAR = 0 get minimum bid
                auction_value = config.MINIMUM_BID
            else:
                # Get total VAR and allocated dollars for this player type
                if player_type == 'hitter':
                    total_var = self.assignments_df[
                        self.assignments_df['player_type'] == 'hitter'
                    ]['VAR'].sum()
                    group_dollars = hitter_dollars
                else:  # pitcher
                    total_var = self.assignments_df[
                        self.assignments_df['player_type'] == 'pitcher'
                    ]['VAR'].sum()
                    group_dollars = pitcher_dollars

                if total_var == 0:
                    auction_value = config.MINIMUM_BID
                else:
                    # Proportional share of group dollars, plus minimum bid
                    auction_value = config.MINIMUM_BID + (var / total_var) * group_dollars

            auction_values.append(auction_value)

        self.assignments_df['auction_value'] = auction_values

        # Round to 2 decimal places (or nearest dollar)
        self.assignments_df['auction_value'] = self.assignments_df['auction_value'].round(0)

        # Ensure minimum bid
        self.assignments_df['auction_value'] = self.assignments_df['auction_value'].clip(
            lower=config.MINIMUM_BID
        )

        # Print summary
        total_allocated = self.assignments_df['auction_value'].sum()
        print(f"\nAuction value allocation summary:")
        print(f"Total allocated: ${total_allocated:.0f} (target: ${self.total_budget})")
        print(f"Hitters total: ${self.assignments_df[self.assignments_df['player_type'] == 'hitter']['auction_value'].sum():.0f}")
        print(f"Pitchers total: ${self.assignments_df[self.assignments_df['player_type'] == 'pitcher']['auction_value'].sum():.0f}")
        print(f"Price range: ${self.assignments_df['auction_value'].min():.0f} - ${self.assignments_df['auction_value'].max():.0f}")

        return self.assignments_df

    def add_rankings(self) -> pd.DataFrame:
        """
        Add overall and position rankings.

        Returns:
            DataFrame with overall_rank and position_rank columns added
        """
        # Overall rank (by auction value descending)
        self.assignments_df['overall_rank'] = self.assignments_df['auction_value'].rank(
            ascending=False,
            method='min'
        ).astype(int)

        # Position rank (by auction value within assigned position)
        self.assignments_df['position_rank'] = self.assignments_df.groupby('assigned_position')[
            'auction_value'
        ].rank(
            ascending=False,
            method='min'
        ).astype(int)

        return self.assignments_df


def allocate_dollars(assignments_df: pd.DataFrame,
                    total_budget: int = None,
                    total_players: int = None) -> pd.DataFrame:
    """
    Convenience function to allocate auction dollars.

    Args:
        assignments_df: DataFrame with VAR calculated
        total_budget: Total league budget (optional, uses config default)
        total_players: Total players to draft (optional, uses config default)

    Returns:
        DataFrame with auction_value, overall_rank, and position_rank columns
    """
    allocator = DollarAllocator(assignments_df, total_budget, total_players)
    df = allocator.allocate_dollars()
    df = allocator.add_rankings()
    return df
