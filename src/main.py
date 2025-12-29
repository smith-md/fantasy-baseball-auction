"""
Main CLI entry point for the fantasy baseball auction draft valuation model.
"""

import argparse
import logging
import sys
from pathlib import Path

from . import config
from .data_fetcher import FanGraphsFetcher
from .projection_combiner import combine_hitter_projections, combine_pitcher_projections
from .stat_converter import (
    convert_hitter_stats,
    convert_pitcher_stats,
    get_hitter_categories_for_normalization,
    get_pitcher_categories_for_normalization,
)
from .sgp_normalizer import normalize_hitters, normalize_pitchers
from .position_optimizer import optimize_positions
from .replacement_calculator import calculate_replacement_and_var
from .dollar_allocator import allocate_dollars
from .keeper_handler import process_keepers
from .output_writer import write_output


def setup_logging(verbose: bool = False):
    """
    Configure logging for the application.

    Args:
        verbose: Enable verbose (DEBUG) logging
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format=config.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Fantasy Baseball Auction Draft Valuation Model',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate valuations for 2026 season
  python -m src.main --season 2026

  # With keepers
  python -m src.main --season 2026 --keepers keepers.csv

  # Custom output filename
  python -m src.main --season 2026 --output my_valuations.csv

  # Don't use cache (force fresh API calls)
  python -m src.main --season 2026 --no-cache

  # Separate hitter/pitcher files
  python -m src.main --season 2026 --separate-files
        """
    )

    parser.add_argument(
        '--season',
        type=int,
        required=True,
        help='Projection season (e.g., 2026)'
    )

    parser.add_argument(
        '--keepers',
        type=str,
        default=None,
        help='Path to CSV file with keeper information (optional)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output filename (default: valuations_<timestamp>.csv)'
    )

    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable caching and force fresh API calls'
    )

    parser.add_argument(
        '--separate-files',
        action='store_true',
        help='Write separate CSV files for hitters and pitchers'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    # Live draft mode arguments
    parser.add_argument(
        '--live-draft',
        action='store_true',
        help='Run in live draft mode (poll Fantrax API for real-time updates)'
    )

    parser.add_argument(
        '--fantrax-league-id',
        type=str,
        default=None,
        help='Fantrax league ID for live draft mode'
    )

    parser.add_argument(
        '--fantrax-api-key',
        type=str,
        default=None,
        help='Fantrax API key (or set FANTRAX_API_KEY environment variable)'
    )

    parser.add_argument(
        '--poll-interval',
        type=int,
        default=5,
        help='Polling interval in seconds for live draft mode (default: 5)'
    )

    return parser.parse_args()


def run_batch_mode(args):
    """Run in batch mode (original functionality)."""
    logger = logging.getLogger(__name__)

    logger.info("="*60)
    logger.info("Fantasy Baseball Auction Draft Valuation Model")
    logger.info("="*60)

    try:
        # Step 1: Fetch projections
        logger.info("\n" + "="*60)
        logger.info("STEP 1: Fetching Projections from FanGraphs")
        logger.info("="*60)

        fetcher = FanGraphsFetcher(season=args.season, use_cache=not args.no_cache)
        all_projections = fetcher.fetch_all()

        hitter_projections = all_projections['hitters']
        pitcher_projections = all_projections['pitchers']

        if not hitter_projections or not pitcher_projections:
            logger.error("Failed to fetch projections. Exiting.")
            sys.exit(1)

        # Step 2: Combine projection systems
        logger.info("\n" + "="*60)
        logger.info("STEP 2: Combining Projection Systems")
        logger.info("="*60)

        hitters_df = combine_hitter_projections(hitter_projections)
        pitchers_df = combine_pitcher_projections(pitcher_projections)

        # Step 3: Process keepers (if provided)
        logger.info("\n" + "="*60)
        logger.info("STEP 3: Processing Keepers")
        logger.info("="*60)

        if args.keepers:
            hitters_df, pitchers_df, adjusted_budget, adjusted_roster_spots, keeper_handler = \
                process_keepers(args.keepers, hitters_df, pitchers_df)
        else:
            logger.info("No keepers provided, using full player pool")
            adjusted_budget = config.TOTAL_BUDGET
            adjusted_roster_spots = config.TOTAL_PLAYERS
            keeper_handler = None

        # Step 4: Convert rate stats
        logger.info("\n" + "="*60)
        logger.info("STEP 4: Converting Rate Stats to Contributions")
        logger.info("="*60)

        hitters_df = convert_hitter_stats(hitters_df)
        pitchers_df = convert_pitcher_stats(pitchers_df)

        # Step 5: Calculate SGP (Standings Gain Points)
        logger.info("\n" + "="*60)
        logger.info("STEP 5: Calculating Standings Gain Points (SGP)")
        logger.info("="*60)

        hitter_categories = get_hitter_categories_for_normalization()
        pitcher_categories = get_pitcher_categories_for_normalization()

        logger.info(f"Hitter categories: {hitter_categories}")
        logger.info(f"Pitcher categories: {pitcher_categories}")

        hitters_df = normalize_hitters(hitters_df, hitter_categories)
        pitchers_df = normalize_pitchers(pitchers_df, pitcher_categories)

        # Step 6: Optimize position assignments
        logger.info("\n" + "="*60)
        logger.info("STEP 6: Optimizing Position Assignments")
        logger.info("="*60)

        assignments_df = optimize_positions(hitters_df, pitchers_df)

        # Step 7: Calculate replacement levels and VAR
        logger.info("\n" + "="*60)
        logger.info("STEP 7: Calculating Replacement Levels and VAR")
        logger.info("="*60)

        assignments_df = calculate_replacement_and_var(assignments_df)

        # Step 8: Allocate auction dollars
        logger.info("\n" + "="*60)
        logger.info("STEP 8: Allocating Auction Dollars")
        logger.info("="*60)

        assignments_df = allocate_dollars(
            assignments_df,
            total_budget=adjusted_budget,
            total_players=adjusted_roster_spots
        )

        # Step 9: Merge keeper information (if applicable)
        if keeper_handler:
            logger.info("\n" + "="*60)
            logger.info("STEP 9: Merging Keeper Information")
            logger.info("="*60)
            assignments_df = keeper_handler.merge_keepers_with_results(assignments_df)

        # Step 10: Write output
        logger.info("\n" + "="*60)
        logger.info("STEP 10: Writing Output")
        logger.info("="*60)

        output_path = write_output(
            assignments_df,
            hitters_df,
            pitchers_df,
            output_file=args.output,
            separate_files=args.separate_files
        )

        # Summary
        logger.info("\n" + "="*60)
        logger.info("SUCCESS!")
        logger.info("="*60)
        logger.info(f"Season: {args.season}")
        logger.info(f"Total players valued: {len(assignments_df)}")
        logger.info(f"Budget: ${adjusted_budget}")

        if args.separate_files:
            logger.info(f"Hitter valuations: {output_path['hitters']}")
            logger.info(f"Pitcher valuations: {output_path['pitchers']}")
        else:
            logger.info(f"Output file: {output_path}")

        logger.info("="*60)

    except Exception as e:
        logger.exception(f"Error during execution: {e}")
        sys.exit(1)


def run_live_draft_mode(args):
    """Run in live draft mode (event-driven)."""
    import os
    from .draft.live_draft_engine import LiveDraftEngine

    logger = logging.getLogger(__name__)

    logger.info("="*60)
    logger.info("Fantasy Baseball Live Draft Mode")
    logger.info("="*60)

    # Validate required arguments
    if not args.fantrax_league_id:
        logger.error("--fantrax-league-id is required for live draft mode")
        sys.exit(1)

    # Get API key from args or environment variable
    api_key = args.fantrax_api_key or os.getenv('FANTRAX_API_KEY')
    if not api_key:
        logger.warning(
            "No Fantrax API key provided. "
            "Set --fantrax-api-key or FANTRAX_API_KEY environment variable if needed."
        )

    try:
        # Initialize live draft engine
        engine = LiveDraftEngine(
            season=args.season,
            league_id=args.fantrax_league_id,
            api_key=api_key,
            keepers_file=args.keepers,
            poll_interval=args.poll_interval
        )

        # Initialize session (fetch projections, load state, etc.)
        engine.initialize()

        # Run polling loop
        engine.run_live_session()

        # Cleanup
        engine.close()

    except KeyboardInterrupt:
        logger.info("\nLive draft session interrupted by user")
    except Exception as e:
        logger.exception(f"Error during live draft: {e}")
        sys.exit(1)


def main():
    """Main execution function with mode branching."""
    # Parse arguments
    args = parse_arguments()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Branch to appropriate mode
    if args.live_draft:
        run_live_draft_mode(args)
    else:
        run_batch_mode(args)


if __name__ == '__main__':
    main()
