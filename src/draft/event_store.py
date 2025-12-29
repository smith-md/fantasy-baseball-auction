"""
Append-only event storage for draft history.

Uses JSONL (JSON Lines) format where each line is a complete JSON object
representing a single draft event. This format enables:
- Streaming writes without loading entire file
- Human-readable event log
- Simple replay from any point
- Crash recovery
"""

import json
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .draft_event import DraftEvent, LeagueState, create_initial_league_state

logger = logging.getLogger(__name__)


class DraftEventStore:
    """Append-only event log for draft history."""

    def __init__(self, filepath: Path):
        """
        Initialize event store.

        Args:
            filepath: Path to JSONL file for event storage
        """
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: DraftEvent) -> None:
        """
        Append a single event to the log.

        Args:
            event: DraftEvent to append

        The event is written as a single line of JSON (JSONL format).
        """
        with open(self.filepath, 'a', encoding='utf-8') as f:
            f.write(event.to_json() + '\n')
        logger.debug(f"Appended event: Pick {event.pick_number} - {event.player_name}")

    def append_events(self, events: List[DraftEvent]) -> None:
        """
        Append multiple events to the log.

        Args:
            events: List of DraftEvents to append
        """
        if not events:
            return

        with open(self.filepath, 'a', encoding='utf-8') as f:
            for event in events:
                f.write(event.to_json() + '\n')

        logger.info(f"Appended {len(events)} events to {self.filepath}")

    def load_all_events(self) -> List[DraftEvent]:
        """
        Load complete event history from file.

        Returns:
            List of DraftEvents in chronological order

        Returns empty list if file doesn't exist.
        """
        if not self.filepath.exists():
            logger.debug(f"Event store file does not exist: {self.filepath}")
            return []

        events = []
        with open(self.filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue  # Skip empty lines

                try:
                    event = DraftEvent.from_json(line)
                    events.append(event)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(
                        f"Failed to parse event at line {line_num}: {e}\n"
                        f"Line content: {line}"
                    )
                    # Continue processing remaining events

        logger.info(f"Loaded {len(events)} events from {self.filepath}")
        return events

    def replay_events(
        self,
        initial_state: Optional[LeagueState] = None,
        num_teams: int = 12
    ) -> LeagueState:
        """
        Replay all events to reconstruct league state.

        Args:
            initial_state: Starting league state (if None, creates fresh state)
            num_teams: Number of teams (used if creating fresh state)

        Returns:
            LeagueState after replaying all events

        This enables crash recovery and testing with historical drafts.
        """
        from .draft_state_manager import DraftStateManager

        events = self.load_all_events()

        if initial_state is None:
            initial_state = create_initial_league_state(num_teams=num_teams)
            logger.info(f"Created initial league state with {num_teams} teams")

        manager = DraftStateManager(initial_state)
        manager.apply_events(events)

        logger.info(
            f"Replayed {len(events)} events - "
            f"{manager.state.total_picks()} total picks, "
            f"${manager.state.available_budget} remaining"
        )

        return manager.state

    def get_event_count(self) -> int:
        """
        Get the number of events in the store without loading them all.

        Returns:
            Number of events (lines) in the file
        """
        if not self.filepath.exists():
            return 0

        with open(self.filepath, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())

    def get_last_event(self) -> Optional[DraftEvent]:
        """
        Get the most recent event without loading all events.

        Returns:
            Last DraftEvent or None if empty
        """
        if not self.filepath.exists():
            return None

        # Read file backwards to get last non-empty line
        with open(self.filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    return DraftEvent.from_json(line)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(f"Failed to parse last event: {e}")
                    continue

        return None

    def export_to_csv(self, output_path: Path) -> None:
        """
        Export event log to CSV format for analysis.

        Args:
            output_path: Path for CSV output file
        """
        import csv

        events = self.load_all_events()
        if not events:
            logger.warning("No events to export")
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'pick_number', 'player_id', 'player_name',
                'team_id', 'price', 'timestamp'
            ])

            for event in events:
                writer.writerow([
                    event.pick_number,
                    event.player_id,
                    event.player_name,
                    event.team_id,
                    event.price,
                    event.timestamp.isoformat()
                ])

        logger.info(f"Exported {len(events)} events to {output_path}")

    def clear(self) -> None:
        """
        Clear all events from the store.

        WARNING: This deletes the event log file. Use with caution.
        """
        if self.filepath.exists():
            self.filepath.unlink()
            logger.warning(f"Cleared event store: {self.filepath}")


def create_session_filepath(
    base_dir: Path,
    league_id: str,
    session_id: Optional[str] = None
) -> Path:
    """
    Generate a filepath for a draft session event store.

    Args:
        base_dir: Base directory for event stores
        league_id: Fantrax league identifier
        session_id: Optional session identifier (uses timestamp if None)

    Returns:
        Path for event store file
    """
    if session_id is None:
        session_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    filename = f"draft_{league_id}_{session_id}.jsonl"
    return base_dir / filename
