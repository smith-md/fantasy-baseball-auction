"""
Generate CSV output with player valuations.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime

from . import config


class OutputWriter:
    """Writes valuation results to CSV file."""

    def __init__(self, output_dir: str = None):
        """
        Initialize the output writer.

        Args:
            output_dir: Directory to write output files (default from config)
        """
        self.output_dir = Path(output_dir or config.OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def prepare_output(self,
                      assignments_df: pd.DataFrame,
                      hitters_df: pd.DataFrame,
                      pitchers_df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare final output DataFrame by merging assignments with projections.

        Args:
            assignments_df: DataFrame with position assignments and valuations
            hitters_df: Hitter projections with all stats
            pitchers_df: Pitcher projections with all stats

        Returns:
            Combined DataFrame ready for output
        """
        # Combine hitters and pitchers
        # Reset index to avoid duplicate index issues
        hitters_clean = hitters_df.reset_index(drop=True)
        pitchers_clean = pitchers_df.reset_index(drop=True)
        all_players = pd.concat([hitters_clean, pitchers_clean], ignore_index=True)

        # Determine merge key
        if 'player_id' in assignments_df.columns and 'player_id' in all_players.columns:
            merge_key = 'player_id'
        elif 'player_name' in assignments_df.columns and 'player_name' in all_players.columns:
            merge_key = 'player_name'
        else:
            raise ValueError("Cannot find common key to merge assignments with projections")

        # Merge assignments with projections
        output_df = assignments_df.merge(
            all_players,
            on=merge_key,
            how='left',
            suffixes=('', '_proj')
        )

        # Clean up duplicate columns
        for col in output_df.columns:
            if col.endswith('_proj'):
                base_col = col.replace('_proj', '')
                if base_col in output_df.columns:
                    # Keep the non-_proj version
                    output_df = output_df.drop(columns=[col])

        return output_df

    def select_output_columns(self, df: pd.DataFrame, player_type: str = None) -> pd.DataFrame:
        """
        Select and order columns for final output.

        Args:
            df: DataFrame with all data
            player_type: Optional filter for 'hitter' or 'pitcher'

        Returns:
            DataFrame with selected columns in proper order
        """
        if player_type:
            df = df[df['player_type'] == player_type].copy()

        # Define column order
        base_columns = [
            'player_name',
            'team',
            'positions',
            'assigned_position',
        ]

        # Add hitter stats
        hitter_stat_columns = ['PA', 'AB', 'R', 'RBI', 'SB', 'OBP', 'SLG']

        # Add pitcher stats (Note: FanGraphs uses 'SO' not 'K')
        pitcher_stat_columns = ['IP', 'W', 'QS', 'SV', 'HLD', 'W_QS', 'SV_HLD', 'SO', 'ERA', 'WHIP']

        # SGP columns (category-level SGP values)
        hitter_sgp_columns = ['R_sgp', 'RBI_sgp', 'SB_sgp', 'OBP_sgp', 'SLG_sgp']
        pitcher_sgp_columns = ['K_sgp', 'W_QS_sgp', 'SV_HLD_sgp', 'ERA_sgp', 'WHIP_sgp']

        # Valuation columns
        valuation_columns = [
            'raw_value',
            'replacement_level',
            'VAR',
            'auction_value',
            'overall_rank',
            'position_rank',
        ]

        # Keeper columns (if they exist)
        keeper_columns = ['keeper_cost', 'keeper_surplus']

        # Build final column list
        final_columns = []

        for col in base_columns:
            if col in df.columns:
                final_columns.append(col)

        # Add relevant stat columns based on player type
        if player_type == 'hitter':
            stat_cols = hitter_stat_columns
        elif player_type == 'pitcher':
            stat_cols = pitcher_stat_columns
        else:
            # Include both if not filtered
            stat_cols = hitter_stat_columns + pitcher_stat_columns

        for col in stat_cols:
            if col in df.columns:
                final_columns.append(col)

        # Add SGP columns (between stats and valuation)
        if player_type == 'hitter':
            sgp_cols = hitter_sgp_columns
        elif player_type == 'pitcher':
            sgp_cols = pitcher_sgp_columns
        else:
            # Include both if not filtered by player type
            sgp_cols = hitter_sgp_columns + pitcher_sgp_columns

        for col in sgp_cols:
            if col in df.columns:
                final_columns.append(col)

        for col in valuation_columns:
            if col in df.columns:
                final_columns.append(col)

        for col in keeper_columns:
            if col in df.columns:
                final_columns.append(col)

        # Add player_id if it exists (useful for reference)
        if 'player_id' in df.columns and 'player_id' not in final_columns:
            final_columns.insert(0, 'player_id')

        # Select only existing columns
        final_columns = [col for col in final_columns if col in df.columns]

        return df[final_columns]

    def write_csv(self,
                  df: pd.DataFrame,
                  filename: str = None,
                  include_timestamp: bool = True) -> Path:
        """
        Write DataFrame to CSV file.

        Args:
            df: DataFrame to write
            filename: Output filename (default: valuations_<timestamp>.csv)
            include_timestamp: Whether to include timestamp in filename

        Returns:
            Path to output file
        """
        if filename is None:
            if include_timestamp:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"valuations_{timestamp}.csv"
            else:
                filename = "valuations.csv"

        output_path = self.output_dir / filename

        # Write to CSV
        df.to_csv(output_path, index=False, float_format='%.2f')

        print(f"\nOutput written to: {output_path}")
        print(f"Total players: {len(df)}")

        return output_path

    def write_separate_files(self,
                            df: pd.DataFrame,
                            base_filename: str = None) -> dict:
        """
        Write separate CSV files for hitters and pitchers.

        Args:
            df: DataFrame with all players
            base_filename: Base filename (default: valuations)

        Returns:
            Dictionary with paths to output files
        """
        if base_filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_filename = f"valuations_{timestamp}"

        # Filter and write hitters
        hitters_df = self.select_output_columns(df, 'hitter')
        hitters_path = self.write_csv(
            hitters_df,
            f"{base_filename}_hitters.csv",
            include_timestamp=False
        )

        # Filter and write pitchers
        pitchers_df = self.select_output_columns(df, 'pitcher')
        pitchers_path = self.write_csv(
            pitchers_df,
            f"{base_filename}_pitchers.csv",
            include_timestamp=False
        )

        return {
            'hitters': hitters_path,
            'pitchers': pitchers_path,
        }


def write_output(assignments_df: pd.DataFrame,
                hitters_df: pd.DataFrame,
                pitchers_df: pd.DataFrame,
                output_file: str = None,
                separate_files: bool = False) -> Path:
    """
    Convenience function to write valuation output.

    Args:
        assignments_df: DataFrame with position assignments and valuations
        hitters_df: Hitter projections with all stats
        pitchers_df: Pitcher projections with all stats
        output_file: Output filename (optional)
        separate_files: Whether to write separate hitter/pitcher files

    Returns:
        Path to output file (or dictionary of paths if separate_files=True)
    """
    writer = OutputWriter()

    # Prepare output
    output_df = writer.prepare_output(assignments_df, hitters_df, pitchers_df)

    # Sort by auction value descending
    output_df = output_df.sort_values('auction_value', ascending=False)

    # Select final columns
    output_df = writer.select_output_columns(output_df)

    if separate_files:
        return writer.write_separate_files(output_df, output_file)
    else:
        return writer.write_csv(output_df, output_file)
