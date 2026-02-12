"""
Entry point for running the Draft Session API server.

Usage:
    python -m src.draft.run_api_server --host 0.0.0.0 --port 8000
    python -m src.draft.run_api_server --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src import config


def main():
    """Main entry point for API server."""
    parser = argparse.ArgumentParser(
        description='Fantasy Baseball Draft Session API Server',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host address to bind server'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port to bind server'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--reload',
        action='store_true',
        help='Enable auto-reload on code changes (development only)'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format=config.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger(__name__)

    # Ensure required directories exist
    logger.info("Initializing directories...")
    Path(config.DRAFT_SESSIONS_DIR).mkdir(parents=True, exist_ok=True)
    Path(config.DRAFT_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    Path(config.DRAFT_EVENTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(config.DRAFT_CHECKPOINTS_DIR).mkdir(parents=True, exist_ok=True)

    # Print startup banner
    logger.info("=" * 60)
    logger.info("Fantasy Baseball Draft Session API Server")
    logger.info("=" * 60)
    logger.info(f"Listening on: http://{args.host}:{args.port}")
    logger.info(f"API Docs: http://{args.host}:{args.port}/docs")
    logger.info(f"Session directory: {config.DRAFT_SESSIONS_DIR}")
    logger.info(f"Cache directory: {config.DRAFT_CACHE_DIR}")
    logger.info(f"Log level: {logging.getLevelName(log_level)}")
    logger.info("=" * 60)

    # Import uvicorn here to avoid startup overhead if args are invalid
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn is not installed. Install with: pip install uvicorn[standard]")
        sys.exit(1)

    # Run FastAPI server
    try:
        uvicorn.run(
            "src.draft.api_server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info" if not args.verbose else "debug",
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
