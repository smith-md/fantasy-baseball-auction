# Fantasy Baseball Auction Draft Valuation Model

A Python-based auction draft valuation system for fantasy baseball that converts player projections into auction dollar values using **Standings Gain Points (SGP)** methodology, positional scarcity analysis, and dynamic budget allocation. Includes **live draft mode** for real-time valuation updates during your auction.

## Overview

This tool generates auction dollar values for fantasy baseball players based on:
- **Player Projections**: Fetches and combines Steamer and FanGraphs DC projections from FanGraphs
- **SGP Valuation**: Uses historical league standings to calculate Standings Gain Points instead of z-scores
- **League Settings**: Configured for 12-team roto leagues with standard roster construction
- **Positional Scarcity**: Accounts for multi-position eligibility and replacement levels
- **Dynamic Split**: Allocates budget between hitters/pitchers based on total value generated
- **Keeper Support**: Adjusts valuations when players are retained from previous seasons
- **Live Draft Mode**: Real-time valuation updates during auction via Fantrax API integration

## Features

### Batch Mode (Pre-Draft Valuations)
- Fetches projections from FanGraphs unofficial API endpoints
- Combines multiple projection systems using simple mean
- Converts rate stats (OBP, SLG, ERA, WHIP) to playing-time-weighted contributions
- **Uses Standings Gain Points (SGP) methodology** based on historical league standings
- Optimizes position assignments using greedy scarcity-based algorithm
- Calculates replacement levels and value above replacement (VAR)
- Dynamically allocates $6,000 budget between hitters and pitchers
- Supports keeper leagues
- Outputs detailed CSV with player valuations, rankings, and projections

### Live Draft Mode (Real-Time Updates)
- **Polls Fantrax API** for draft transactions during your auction
- **Automatic valuation updates** within 2 seconds of each pick
- **Event-driven architecture** - only runs when picks occur
- **Crash recovery** via append-only event log
- **JSON cache output** for local consumption or web UI integration
- Reuses existing SGP valuation engine for consistency
- Team budget and roster tracking across all teams

## Installation

1. Clone or download this repository

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Generate valuations for a specific season:

```bash
python -m src.main --season 2026
```

### With Keepers

If your league has keepers, create a CSV file with keeper information:

**keepers.csv:**
```csv
player_name,keeper_salary
Juan Soto,45
Shohei Ohtani,52
Elly De La Cruz,28
```

Then run:
```bash
python -m src.main --season 2026 --keepers keepers.csv
```

### Live Draft Mode

Run real-time valuations during your Fantrax auction draft:

```bash
# Set your Fantrax API key (optional)
export FANTRAX_API_KEY="your_api_key"

# Start live draft mode
python -m src.main \
    --season 2026 \
    --live-draft \
    --fantrax-league-id YOUR_LEAGUE_ID \
    --keepers keepers.csv \
    --poll-interval 10
```

**Output**: `data/draft_cache/latest_valuations.json` (updated on each pick)

See [LIVE_DRAFT.md](LIVE_DRAFT.md) for complete live draft documentation.

### Advanced Options

```bash
# Custom output filename
python -m src.main --season 2026 --output my_valuations.csv

# Disable caching (force fresh API calls)
python -m src.main --season 2026 --no-cache

# Separate hitter/pitcher files
python -m src.main --season 2026 --separate-files

# Verbose logging
python -m src.main --season 2026 --verbose
```

### Full Command Reference

```
python -m src.main [OPTIONS]

Required Arguments:
  --season YEAR              Projection season (e.g., 2026)

Batch Mode Arguments:
  --keepers PATH             Path to CSV file with keeper information
  --output FILENAME          Output filename (default: valuations_<timestamp>.csv)
  --no-cache                 Disable caching and force fresh API calls
  --separate-files           Write separate CSV files for hitters and pitchers
  --verbose                  Enable verbose logging

Live Draft Mode Arguments:
  --live-draft               Enable live draft mode
  --fantrax-league-id ID     Fantrax league ID (required for live mode)
  --fantrax-api-key KEY      Fantrax API key (or set FANTRAX_API_KEY env var)
  --poll-interval SECONDS    Polling interval (default: 5)

Other:
  --help                     Show help message
```

## League Configuration

The model is pre-configured for a 12-team roto league with the following settings:

**Roster Construction:**
- Hitters: C, 1B, 2B, 3B, SS, 3×OF, 3×UTIL, 2×BN (13 total)
- Pitchers: 8×P, 3×BN (11 total)

**Scoring Categories:**
- Hitters: R, RBI, SB, OBP, SLG
- Pitchers: W+QS, SV+HLD, K, ERA, WHIP

**Budget:**
- $500 per team
- $6,000 total league budget
- $1 minimum bid per player

To modify these settings, edit `src/config.py`.

## Output Format

The model generates a CSV file with the following columns:

| Column | Description |
|--------|-------------|
| player_name | Player name |
| team | MLB team |
| positions | Eligible positions (list) |
| assigned_position | Position assigned by optimizer |
| PA/IP | Playing time projection |
| R, RBI, SB, etc. | Projected stats |
| raw_value | Sum of SGP values across categories |
| replacement_level | Replacement level for assigned position |
| VAR | Value above replacement |
| auction_value | Auction dollar value |
| overall_rank | Overall rank by auction value |
| position_rank | Rank within assigned position |
| keeper_cost | Keeper salary (if applicable) |
| keeper_surplus | Auction value - keeper cost (if applicable) |

## How It Works

### Pipeline Overview

**Batch Mode:**
1. **Fetch Projections**: Downloads projections from FanGraphs (Steamer and FanGraphs DC)
2. **Combine Systems**: Calculates simple mean across projection systems for each stat
3. **Process Keepers**: Removes kept players and adjusts budget/roster (if applicable)
4. **Convert Rate Stats**: Transforms OBP/SLG/ERA/WHIP into playing-time-weighted contributions
5. **Calculate SGP**: Uses historical league standings to compute Standings Gain Points for each category
6. **Optimize Positions**: Assigns players to roster slots using greedy scarcity algorithm
7. **Calculate Replacement**: Determines replacement level for each position
8. **Allocate Dollars**: Converts VAR to auction dollars with dynamic hitter/pitcher split
9. **Output**: Generates CSV with complete valuations

**Live Draft Mode:**
1. **Initialize**: Fetch projections once at startup (steps 1-2 above)
2. **Poll Fantrax**: Check for new draft picks every N seconds
3. **Update State**: Apply draft events to league state (budgets, rosters, drafted players)
4. **Recompute**: Re-run valuation pipeline (steps 3-8) for remaining players
5. **Cache Results**: Update JSON cache with latest valuations
6. **Repeat**: Continue polling until draft ends or user stops

### Key Algorithms

#### Rate Stat Conversion

**Hitters:**
```
OBP_contrib = (OBP_player - OBP_avg) × PA
SLG_contrib = (SLG_player - SLG_avg) × AB
```

**Pitchers:**
```
ERA_contrib = (ERA_avg - ERA_player) × IP
WHIP_contrib = (WHIP_avg - WHIP_player) × IP
```

#### Standings Gain Points (SGP) Calculation

**SGP** measures how much each statistical unit improves your team's standing in a category.

```
# Calculate SGP denominator from historical standings
SGP_denominator = median(rank-to-rank gaps in historical standings)

# Convert player stats to SGP
SGP = player_stat_value / SGP_denominator

# Sum across all categories
raw_value = sum of SGP across all categories
```

**Example**: If the median gap between 1st and 2nd place in Runs is 20 runs, then:
- A player projected for 100 runs = 100 / 20 = 5.0 SGP in Runs
- This represents contributing 5 standings points in that category

SGP is more league-calibrated than z-scores because it's based on actual historical performance gaps in your specific league format.

#### Position Assignment (Greedy Algorithm)

1. Sort players by raw_value (descending)
2. For each player:
   - Calculate scarcity for each eligible position
   - Scarcity = remaining_slots / remaining_eligible_players
   - Assign to most scarce position
3. Continue until all 288 roster slots filled

#### Dollar Allocation

```
total_hitter_VAR = sum(VAR for all hitters)
total_pitcher_VAR = sum(VAR for all pitchers)

hitter_dollars = 5712 × (total_hitter_VAR / total_VAR)
pitcher_dollars = 5712 × (total_pitcher_VAR / total_VAR)

auction_value = 1 + (player_VAR / total_group_VAR) × group_dollars
```

## Project Structure

```
fantasy-baseball-auction/
├── src/
│   ├── config.py                    # League configuration
│   ├── main.py                      # CLI entry point
│   ├── data_fetcher.py              # FanGraphs API integration
│   ├── projection_combiner.py       # Combine projection systems
│   ├── stat_converter.py            # Convert rate stats
│   ├── sgp_normalizer.py            # SGP calculation wrapper
│   ├── position_optimizer.py        # Position assignment
│   ├── replacement_calculator.py    # Replacement levels & VAR
│   ├── dollar_allocator.py          # Auction dollar allocation
│   ├── keeper_handler.py            # Keeper support
│   ├── output_writer.py             # CSV generation
│   ├── sgp/                         # SGP calculation subsystem
│   │   ├── league_data_loader.py    # Load historical standings
│   │   ├── category_analyzer.py     # Analyze standings gaps
│   │   ├── sgp_calculator.py        # Compute SGP values
│   │   ├── replacement_baseline.py  # Calculate replacement baselines
│   │   └── diagnostic_writer.py     # SGP diagnostics
│   └── draft/                       # Live draft subsystem
│       ├── draft_event.py           # Data structures
│       ├── draft_state_manager.py   # State management
│       ├── event_store.py           # Event persistence
│       ├── fantrax_client.py        # Fantrax API client
│       ├── live_draft_engine.py     # Main orchestrator
│       └── result_cache.py          # JSON output cache
├── data/
│   ├── cache/                       # Cached API responses
│   ├── output/                      # Generated CSV files
│   ├── standings/                   # Historical league standings (for SGP)
│   ├── diagnostics/                 # SGP diagnostics
│   ├── draft_events/                # Live draft event logs (JSONL)
│   ├── draft_cache/                 # Live draft JSON cache
│   ├── draft_checkpoints/           # State snapshots
│   └── mappings/                    # Fantrax player/team mappings
├── tests/                           # Unit tests
├── requirements.txt
├── README.md
├── LIVE_DRAFT.md                    # Live draft documentation
└── .gitignore
```

## Keeper Format

Create a CSV file with the following columns:

**Required:**
- `player_name` or `player_id`: Player identifier
- `keeper_salary`: Dollar amount the player is being kept for

**Example:**
```csv
player_name,keeper_salary
Juan Soto,45
Shohei Ohtani,52
Elly De La Cruz,28
```

The model will:
1. Remove kept players from the draftable pool
2. Subtract keeper salaries from the total budget ($6,000 - keeper costs)
3. Reduce available roster slots (288 - number of keepers)
4. Recalculate replacement levels and values based on adjusted pool

## Customization

### Modify League Settings

Edit `src/config.py` to change:
- Number of teams
- Budget per team
- Roster construction
- Scoring categories
- Minimum PA/IP thresholds

### Adjust Position Eligibility

Modify `UTIL_ELIGIBLE_POSITIONS` and `BN_H_ELIGIBLE_POSITIONS` in `src/config.py` to change which positions qualify for UTIL and bench slots.

### Change Projection Systems

Edit `PROJECTION_SYSTEMS` in `src/config.py` to include/exclude projection systems:
```python
PROJECTION_SYSTEMS = ['steamer', 'zips', 'atc']  # Remove or add systems
```

## Troubleshooting

### FanGraphs API Issues

The model uses unofficial FanGraphs endpoints that may change. If you encounter errors:

1. Check the endpoint structure in `src/config.py`
2. Enable verbose logging: `--verbose`
3. Try disabling cache: `--no-cache`

### Missing Stats

If projections are missing required stats:

1. Check `src/config.py` for required stat column names
2. Verify FanGraphs has published projections for the selected season
3. Review cached data in `data/cache/` and delete if stale

### Position Assignment Warnings

If you see warnings like "Could not assign X players":

1. Check that positions in projections match `config.py` definitions
2. Verify roster slot configuration matches league settings
3. Enable verbose logging to see detailed assignment process

## Known Limitations

1. **Unofficial API**: FanGraphs endpoints are unofficial and may change without notice
2. **Projection Availability**: Projections may not be available for future seasons until published
3. **Greedy Algorithm**: Position assignment uses greedy algorithm (~95% optimal) rather than true optimization
4. **No Injury Adjustments**: Does not account for injuries or playing time uncertainty
5. **Fixed Categories**: Categories are hardcoded (not configurable without editing code)

## Future Enhancements

- **Web UI for live draft** - Real-time visualization dashboard
- **Draft recommendations** - Suggest best picks based on team needs
- **Multi-league support** - Track multiple drafts simultaneously
- Linear programming optimization for position assignment
- Fixed hitter/pitcher split option (e.g., 67/33)
- Support for points leagues
- Risk/volatility adjustments
- Auction simulator

## Testing

Run unit tests:
```bash
pytest tests/
```

## License

This project is provided as-is for personal use in fantasy baseball leagues.

## Credits

Projection data sourced from FanGraphs. This tool is not affiliated with or endorsed by FanGraphs.

## Support

For issues or questions, refer to the PRD documentation or check the implementation in the source code.
