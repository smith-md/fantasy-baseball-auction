# Fantasy Baseball Auction Draft Valuation Model

A Python-based auction draft valuation system for fantasy baseball that converts player projections into auction dollar values using z-score normalization, positional scarcity analysis, and dynamic budget allocation.

## Overview

This tool generates auction dollar values for fantasy baseball players based on:
- **Player Projections**: Fetches and combines Steamer, ZiPS, and ATC projections from FanGraphs
- **League Settings**: Configured for 12-team roto leagues with standard roster construction
- **Positional Scarcity**: Accounts for multi-position eligibility and replacement levels
- **Dynamic Split**: Allocates budget between hitters/pitchers based on total value generated
- **Keeper Support**: Adjusts valuations when players are retained from previous seasons

## Features

- Fetches projections from FanGraphs unofficial API endpoints
- Combines multiple projection systems using simple mean
- Converts rate stats (OBP, SLG, ERA, WHIP) to playing-time-weighted contributions
- Normalizes categories using z-scores
- Optimizes position assignments using greedy scarcity-based algorithm
- Calculates replacement levels and value above replacement (VAR)
- Dynamically allocates $6,000 budget between hitters and pitchers
- Supports keeper leagues
- Outputs detailed CSV with player valuations, rankings, and projections

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
  --season YEAR         Projection season (e.g., 2026)

Optional Arguments:
  --keepers PATH        Path to CSV file with keeper information
  --output FILENAME     Output filename (default: valuations_<timestamp>.csv)
  --no-cache           Disable caching and force fresh API calls
  --separate-files     Write separate CSV files for hitters and pitchers
  --verbose            Enable verbose logging
  --help               Show help message
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
| raw_value | Sum of z-scores across categories |
| replacement_level | Replacement level for assigned position |
| VAR | Value above replacement |
| auction_value | Auction dollar value |
| overall_rank | Overall rank by auction value |
| position_rank | Rank within assigned position |
| keeper_cost | Keeper salary (if applicable) |
| keeper_surplus | Auction value - keeper cost (if applicable) |

## How It Works

### Pipeline Overview

1. **Fetch Projections**: Downloads projections from FanGraphs for Steamer, ZiPS, and ATC systems
2. **Combine Systems**: Calculates simple mean across projection systems for each stat
3. **Convert Rate Stats**: Transforms OBP/SLG/ERA/WHIP into playing-time-weighted contributions
4. **Normalize**: Calculates z-scores for each category (hitters and pitchers separately)
5. **Optimize Positions**: Assigns players to roster slots using greedy scarcity algorithm
6. **Calculate Replacement**: Determines replacement level for each position
7. **Allocate Dollars**: Converts VAR to auction dollars with dynamic hitter/pitcher split
8. **Output**: Generates CSV with complete valuations

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

#### Z-Score Normalization

```
z = (player_value - category_mean) / category_std_dev
raw_value = sum of z-scores across all categories
```

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
│   ├── data_fetcher.py              # FanGraphs API integration
│   ├── projection_combiner.py       # Combine projection systems
│   ├── stat_converter.py            # Convert rate stats
│   ├── normalizer.py                # Z-score normalization
│   ├── position_optimizer.py        # Position assignment
│   ├── replacement_calculator.py    # Replacement levels & VAR
│   ├── dollar_allocator.py          # Auction dollar allocation
│   ├── keeper_handler.py            # Keeper support
│   ├── output_writer.py             # CSV generation
│   └── main.py                      # CLI entry point
├── data/
│   ├── cache/                       # Cached API responses
│   └── output/                      # Generated CSV files
├── tests/                           # Unit tests
├── requirements.txt
├── README.md
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

- Standings Gain Points (SGP) methodology as alternative to z-scores
- Linear programming optimization for position assignment
- Fixed hitter/pitcher split option (e.g., 67/33)
- Support for points leagues
- Web UI for draft room integration
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
