# Live Draft Mode - User Guide

## Overview

The Live Draft mode enables real-time valuation updates during your fantasy baseball auction draft. The system polls Fantrax for draft transactions and automatically recalculates player values as the draft progresses.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Your Fantrax API Key (Optional)

```bash
export FANTRAX_API_KEY="your_api_key_here"
```

Or pass it directly via command line argument.

### 3. Run Pre-Draft Valuations (Batch Mode)

Before the draft starts, generate initial valuations:

```bash
python -m src.main --season 2026 --keepers keepers.csv
```

### 4. Start Live Draft Mode

On draft day, start the live polling:

```bash
python -m src.main \
    --season 2026 \
    --live-draft \
    --fantrax-league-id YOUR_LEAGUE_ID \
    --keepers keepers.csv \
    --poll-interval 10
```

The system will:
- Fetch projections and mappings
- Poll Fantrax every 10 seconds
- Detect new draft picks automatically
- Recompute valuations for remaining players
- Update JSON cache for consumption

Press Ctrl+C to stop.

## Command Line Arguments

### Required for Live Draft
- `--season YEAR` - Projection season (e.g., 2026)
- `--live-draft` - Enable live draft mode
- `--fantrax-league-id ID` - Your Fantrax league ID

### Optional
- `--fantrax-api-key KEY` - API authentication (or use FANTRAX_API_KEY env var)
- `--keepers FILE` - Path to keeper CSV file
- `--poll-interval SECONDS` - Polling frequency (default: 5)
- `--verbose` - Enable debug logging

## Output Files

### Live Valuation Cache (JSON)
**Location**: `data/draft_cache/latest_valuations.json`

Updated automatically on each pick. Contains:
```json
{
  "timestamp": "2025-03-15T14:23:45Z",
  "last_pick": 42,
  "available_budget": 4200,
  "available_roster_spots": 246,
  "team_summary": [...],
  "players": [
    {
      "player_name": "Juan Soto",
      "team": "NYY",
      "positions": ["OF"],
      "auction_value": 52,
      "overall_rank": 1,
      ...
    }
  ]
}
```

You can read this file from a web UI, Excel, or any other tool.

### Draft Event Log (JSONL)
**Location**: `data/draft_events/draft_{league_id}_{timestamp}.jsonl`

Append-only log of all draft picks. One JSON object per line:
```json
{"pick_number": 1, "player_id": "sa01227", "player_name": "Juan Soto", "team_id": "team_05", "price": 52, "timestamp": "2025-03-15T14:23:45Z"}
```

This enables crash recovery and draft replay.

### Historical Snapshots
**Location**: `data/draft_cache/history/valuations_pick{N}.json`

Saved every 10 picks for historical analysis.

## Crash Recovery

If the system crashes during the draft:

1. Restart with the same command
2. The system will detect the existing event log
3. It will replay all previous picks to restore state
4. Continue polling from where it left off

No data is lost because events are append-only.

## How It Works

### Architecture
```
Fantrax API (polling)
    ↓
Draft Events
    ↓
League State (teams, budgets, rosters)
    ↓
Keeper Format Conversion
    ↓
Existing Valuation Pipeline (SGP, positions, dollars)
    ↓
JSON Cache
```

### Key Design Principles

1. **Event-driven**: Only runs when picks occur
2. **Transactional**: Fantrax API is source of truth
3. **Reuses existing code**: Drafted players treated as "keepers"
4. **Fast recompute**: Target <1 second per update

## Troubleshooting

### "No Fantrax API key provided"
Set the API key via `--fantrax-api-key` or `FANTRAX_API_KEY` environment variable.

### "Failed to match player to FanGraphs"
The system uses fuzzy name matching to map Fantrax players to FanGraphs projections. If a player can't be matched:
- Check the log for the player name
- The player will be skipped (won't affect other picks)
- You can manually add a mapping later if needed

### "Valuation taking >1 second"
This is usually fine, but if it's consistently slow:
- Check if diagnostics output is enabled (can disable in config.py)
- Ensure you're not running other heavy processes
- The first valuation is slower (loading SGP data), subsequent ones are faster

### "State validation failed"
This indicates a bug in state management. The system will log the error and stop. Please report this with the event log file.

## Advanced Usage

### Custom Poll Interval
Faster polling for quick drafts:
```bash
--poll-interval 3
```

Slower polling to reduce API load:
```bash
--poll-interval 15
```

### Export Cache to CSV
After the draft, convert JSON cache to CSV:
```python
from src.draft.result_cache import ResultCache
from pathlib import Path

cache = ResultCache(Path('data/draft_cache'))
cache.export_to_csv(Path('data/output/final_valuations.csv'))
```

### Replay Historical Draft
Test the system with a past draft:
```python
from src.draft.event_store import DraftEventStore
from pathlib import Path

store = DraftEventStore(Path('data/draft_events/draft_xyz_20250315.jsonl'))
final_state = store.replay_events()
print(f"Final state: {final_state.total_picks()} picks")
```

## Performance Targets

- **Projection loading**: ~5 seconds (one-time at startup)
- **Valuation recompute**: <1 second per pick
- **Polling overhead**: <100ms
- **Total latency**: Pick detected → cache updated in <2 seconds

## File Structure

```
fantasy-baseball-auction/
├── src/
│   ├── draft/                    # Live draft subsystem
│   │   ├── draft_event.py        # Data structures
│   │   ├── draft_state_manager.py # State management
│   │   ├── event_store.py        # Event persistence
│   │   ├── fantrax_client.py     # API integration
│   │   ├── live_draft_engine.py  # Main orchestrator
│   │   └── result_cache.py       # JSON output
│   ├── main.py                   # Entry point
│   └── ...                       # Existing valuation code
└── data/
    ├── draft_events/             # Event logs (JSONL)
    ├── draft_cache/              # JSON cache + history
    ├── draft_checkpoints/        # State snapshots
    └── mappings/                 # Fantrax player/team mappings
```

## Support

For issues or questions:
1. Check the logs (use `--verbose` for detailed output)
2. Review the event log file in `data/draft_events/`
3. Check the cached mappings in `data/mappings/`

## Next Steps

After implementing and testing:
- Add web UI for visualizing live valuations
- Implement draft recommendations based on team needs
- Add mobile notifications for high-value picks
- Support multiple leagues simultaneously
