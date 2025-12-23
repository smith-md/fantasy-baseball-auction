"""
Handle keeper players and adjust the draft pool accordingly.

Keepers are players retained from previous seasons at a predetermined cost.
They are removed from the draftable pool, and their salaries are subtracted
from the available budget.
"""

import pandas as pd
from typing import Optional, Tuple
from pathlib import Path

from . import config


class KeeperHandler:
    """Handles keeper players and adjusts draft parameters."""

    def __init__(self, keeper_file: Optional[str] = None):
        """
        Initialize the keeper handler.

        Args:
            keeper_file: Path to CSV file with keeper information
                        Expected columns: player_id or player_name, keeper_salary
        """
        self.keeper_file = keeper_file
        self.keepers_df = None

        if keeper_file:
            self.load_keepers()

    def load_keepers(self) -> pd.DataFrame:
        """
        Load keeper data from CSV file.

        Returns:
            DataFrame with keeper information
        """
        if not self.keeper_file:
            return pd.DataFrame()

        keeper_path = Path(self.keeper_file)

        if not keeper_path.exists():
            raise FileNotFoundError(f"Keeper file not found: {self.keeper_file}")

        # Load keeper CSV
        self.keepers_df = pd.read_csv(keeper_path)

        # Validate required columns
        required_cols = ['keeper_salary']
        has_id = 'player_id' in self.keepers_df.columns
        has_name = 'player_name' in self.keepers_df.columns

        if not (has_id or has_name):
            raise ValueError("Keeper file must have 'player_id' or 'player_name' column")

        if 'keeper_salary' not in self.keepers_df.columns:
            raise ValueError("Keeper file must have 'keeper_salary' column")

        print(f"\nLoaded {len(self.keepers_df)} keepers from {self.keeper_file}")
        print(f"Total keeper salaries: ${self.keepers_df['keeper_salary'].sum()}")

        return self.keepers_df

    def remove_keepers_from_pool(self,
                                 hitters_df: pd.DataFrame,
                                 pitchers_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Remove keeper players from the draftable pool.

        Args:
            hitters_df: Hitter projections DataFrame
            pitchers_df: Pitcher projections DataFrame

        Returns:
            Tuple of (filtered_hitters_df, filtered_pitchers_df)
        """
        if self.keepers_df is None or len(self.keepers_df) == 0:
            return hitters_df, pitchers_df

        # Determine which column to use for matching
        if 'player_id' in self.keepers_df.columns:
            keeper_ids = set(self.keepers_df['player_id'].dropna())
            match_col = 'player_id'
        else:
            keeper_names = set(self.keepers_df['player_name'].dropna())
            match_col = 'player_name'

        # Filter out keepers from hitters
        initial_hitters = len(hitters_df)
        if match_col in hitters_df.columns:
            if match_col == 'player_id':
                hitters_df = hitters_df[~hitters_df[match_col].isin(keeper_ids)]
            else:
                hitters_df = hitters_df[~hitters_df[match_col].isin(keeper_names)]

        removed_hitters = initial_hitters - len(hitters_df)

        # Filter out keepers from pitchers
        initial_pitchers = len(pitchers_df)
        if match_col in pitchers_df.columns:
            if match_col == 'player_id':
                pitchers_df = pitchers_df[~pitchers_df[match_col].isin(keeper_ids)]
            else:
                pitchers_df = pitchers_df[~pitchers_df[match_col].isin(keeper_names)]

        removed_pitchers = initial_pitchers - len(pitchers_df)

        print(f"Removed {removed_hitters} hitter keepers from pool")
        print(f"Removed {removed_pitchers} pitcher keepers from pool")

        return hitters_df, pitchers_df

    def adjust_budget(self) -> Tuple[int, int]:
        """
        Calculate adjusted budget and roster spots for the draft.

        Returns:
            Tuple of (adjusted_budget, adjusted_roster_spots)
        """
        if self.keepers_df is None or len(self.keepers_df) == 0:
            return config.TOTAL_BUDGET, config.TOTAL_PLAYERS

        total_keeper_cost = self.keepers_df['keeper_salary'].sum()
        num_keepers = len(self.keepers_df)

        adjusted_budget = config.TOTAL_BUDGET - total_keeper_cost
        adjusted_roster_spots = config.TOTAL_PLAYERS - num_keepers

        print(f"\nAdjusted draft parameters:")
        print(f"Original budget: ${config.TOTAL_BUDGET}")
        print(f"Keeper costs: ${total_keeper_cost}")
        print(f"Adjusted budget: ${adjusted_budget}")
        print(f"Original roster spots: {config.TOTAL_PLAYERS}")
        print(f"Keepers: {num_keepers}")
        print(f"Adjusted roster spots: {adjusted_roster_spots}")

        return adjusted_budget, adjusted_roster_spots

    def merge_keepers_with_results(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """
        Merge keeper information back into final results for reference.

        Args:
            results_df: Final valuation results DataFrame

        Returns:
            DataFrame with keeper information merged
        """
        if self.keepers_df is None or len(self.keepers_df) == 0:
            # Add empty keeper columns for consistency
            results_df['keeper_cost'] = None
            results_df['keeper_surplus'] = None
            return results_df

        # Determine match column
        if 'player_id' in self.keepers_df.columns and 'player_id' in results_df.columns:
            match_col = 'player_id'
        elif 'player_name' in self.keepers_df.columns and 'player_name' in results_df.columns:
            match_col = 'player_name'
        else:
            print("Warning: Cannot match keepers to results, skipping keeper merge")
            results_df['keeper_cost'] = None
            results_df['keeper_surplus'] = None
            return results_df

        # Merge keeper info
        results_df = results_df.merge(
            self.keepers_df[[match_col, 'keeper_salary']],
            on=match_col,
            how='left'
        )

        # Rename and calculate surplus
        results_df = results_df.rename(columns={'keeper_salary': 'keeper_cost'})

        # Calculate keeper surplus (auction value - keeper cost)
        # Only for players who are keepers
        results_df['keeper_surplus'] = None
        has_keeper_cost = results_df['keeper_cost'].notna()
        results_df.loc[has_keeper_cost, 'keeper_surplus'] = (
            results_df.loc[has_keeper_cost, 'auction_value'] -
            results_df.loc[has_keeper_cost, 'keeper_cost']
        )

        print(f"Merged keeper information for {has_keeper_cost.sum()} players")

        return results_df


def process_keepers(keeper_file: Optional[str],
                   hitters_df: pd.DataFrame,
                   pitchers_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, int, int, Optional[KeeperHandler]]:
    """
    Convenience function to process keepers and adjust draft pool.

    Args:
        keeper_file: Path to keeper CSV file (or None)
        hitters_df: Hitter projections DataFrame
        pitchers_df: Pitcher projections DataFrame

    Returns:
        Tuple of (filtered_hitters, filtered_pitchers, adjusted_budget,
                 adjusted_roster_spots, keeper_handler)
    """
    handler = KeeperHandler(keeper_file)

    if keeper_file:
        hitters_df, pitchers_df = handler.remove_keepers_from_pool(hitters_df, pitchers_df)
        adjusted_budget, adjusted_roster_spots = handler.adjust_budget()
    else:
        adjusted_budget = config.TOTAL_BUDGET
        adjusted_roster_spots = config.TOTAL_PLAYERS

    return hitters_df, pitchers_df, adjusted_budget, adjusted_roster_spots, handler
