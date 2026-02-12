# Valuation Investigation: Trea Turner & Position Assignment

## Problem

Trea Turner's auction valuation ($9, ranked 208th overall) is significantly lower than expected. FanGraphs has him ranked ~23rd with an ADP of 29, yet the SGP engine assigns him minimal value.

## Raw Projections (2026 Steamer)

| Stat | Value |
|------|-------|
| PA   | 609   |
| R    | 85    |
| RBI  | 65    |
| SB   | 26    |
| OBP  | .332  |
| SLG  | .441  |
| ADP  | 29    |

These projections are pulled directly from the FanGraphs API and look reasonable. The data source is not the problem.

## SGP Valuation Output

| Field             | Value |
|-------------------|-------|
| raw_value         | 20.48 SGP |
| assigned_position | BN_H (bench hitter) |
| replacement_level | 19.56 SGP |
| VAR               | 0.92 SGP |
| auction_value     | $9 |
| overall_rank      | 208 |

## Root Cause Analysis

### 1. Position Assignment (Primary Suspect)

The position optimizer uses a greedy scarcity-based algorithm and assigned Turner to **BN_H** instead of **SS**. This is the biggest driver of his deflated value:

- BN_H replacement level is 19.56 SGP — very high, since many capable hitters compete for bench slots
- SS replacement level would be much lower due to positional scarcity
- A player assigned to SS with the same 20.48 raw_value would have significantly higher VAR and therefore more auction dollars

The greedy algorithm may be placing a less-deserving player at SS ahead of Turner, which cascades into Turner getting stuck at BN_H.

### 2. Rate Stat Marginal Impact

The SGP system calculates marginal contributions for OBP and SLG relative to league average:
- `OBP_contrib = (player_OBP - league_avg_OBP) x PA`
- `SLG_contrib = (player_SLG - league_avg_SLG) x AB`

Turner's .332 OBP and .441 SLG are decent but not far above league average, which compresses his SGP value in those categories. This may systematically undervalue players whose value comes from balanced production across categories rather than elite performance in one.

### 3. Projection System Coverage

Only two projection systems are active in `src/config.py`:
- Steamer
- FanGraphs Depth Charts

ZiPS and ATC are mapped but not fetched. With only two systems, a pessimistic projection from one system has outsized impact on the combined average.

## Proposed Next Steps

1. **Investigate position assignment logic** (`src/position_optimizer.py`) — Trace why the greedy algorithm places Turner at BN_H instead of SS. Identify which players got assigned to SS ahead of him and whether that's defensible.

2. **Compare SS-assigned players vs Turner** — Pull the players who did get assigned SS slots and compare their raw_value to Turner's. If weaker players got SS, the optimizer has a bug.

3. **Test with forced position assignment** — Manually assign Turner to SS and re-run the valuation to see what his dollar value would be. This isolates position assignment as the cause.

4. **Review the greedy algorithm's ordering** — The algorithm assigns positions based on scarcity. Check whether the ordering of position fills is causing suboptimal assignments (e.g., filling BN_H before SS is fully allocated).

5. **Audit rate stat baselines** — Check what league average OBP/SLG values are being used for marginal impact. If these are inflated, it would compress value for average-OBP players like Turner.

6. **Consider adding projection systems** — Enable ZiPS and/or ATC in config to smooth out projection variance and reduce sensitivity to a single system's pessimism.

7. **Spot-check other suspect players** — Run the same analysis for 5-10 players with large gaps between ADP and auction value to see if the position assignment issue is systemic.
