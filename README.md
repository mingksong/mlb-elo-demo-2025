# MLB ELO Rating System

A zero-sum ELO rating system for MLB players, built on Statcast plate appearance data from the 2025 season. Every batter-pitcher matchup produces an ELO exchange based on run expectancy — over 183,000 plate appearances distilled into a single performance number per player.

## Abstract

Traditional baseball statistics evaluate players in isolation. Batting average, ERA, and OPS measure outcomes but ignore context: who was pitching, what was the base-out state, and how does the ballpark affect scoring?

This project applies an **ELO rating system** — originally designed for chess — to MLB plate appearances. Each PA is a head-to-head contest between batter and pitcher. The batter's gain is exactly the pitcher's loss (**zero-sum**). The result is a unified scale where 1,500 is league average, elite batters climb above 2,000, and dominant pitchers approach 1,900.

Three adjustments ensure fairness:
- **Park factor** — Coors Field inflates run values; Petco Park suppresses them. We normalize.
- **State normalization** — A single with bases loaded has higher raw run value than with bases empty. We subtract the expected run value for each base-out state so only *above-average* outcomes raise ELO.
- **Field error handling** — Batters don't earn ELO credit for reaching base on fielding errors.

## Methodology

### ELO Formula (V5.3 Zero-Sum)

Every player starts at **1,500** (league average). After each plate appearance:

```
Step 1: Park factor adjustment
  adjusted_rv = delta_run_exp - (park_factor - 1.0) × 0.1

Step 2: State normalization
  rv_diff = adjusted_rv - mean_rv[base_out_state]

Step 3: Zero-sum ELO update
  batter_delta  = K × rv_diff
  pitcher_delta = -batter_delta
```

| Parameter | Value | Description |
|-----------|-------|-------------|
| `K_FACTOR` | 12.0 | ELO sensitivity per plate appearance |
| `INITIAL_ELO` | 1500.0 | Starting ELO for all players |
| `MIN_ELO` | 500.0 | Floor (ELO cannot drop below) |
| `ADJUSTMENT_SCALE` | 0.1 | Park factor scaling constant |

### Data Source

- **MLB Statcast** via Baseball Savant
- **711,897 pitches** aggregated into **183,092 plate appearances**
- **2,428 games** across the 2025 season
- **1,469 players** (batters and pitchers)

### Key Metric: delta_run_exp

The core input is **delta run expectancy** (`delta_run_exp`) from Statcast — how much a plate appearance outcome changed the expected runs scored in that inning. Examples:

| Outcome | Typical delta_run_exp | ELO Impact (K=12) |
|---------|----------------------|-------------------|
| Home run | +1.4 | ~+17 ELO |
| Walk | +0.3 | ~+4 ELO |
| Strikeout | -0.3 | ~-4 ELO |
| Double play | -0.8 | ~-10 ELO |

### State Normalization

The 24 base-out states (8 base configurations × 3 out counts) each have different average run values. A hit with runners in scoring position carries higher raw `delta_run_exp` than with bases empty — but it's also the *expected* outcome in that situation.

We compute the mean `delta_run_exp` for each state from the full season (183K PAs) and subtract it, so ELO only rewards performance *above* the situational average.

### Park Factor

MLB's 30 stadiums have different scoring environments:

| Stadium | Park Factor | Effect |
|---------|------------|--------|
| Coors Field (COL) | 1.13 | Batter-friendly — positive outcomes adjusted down |
| T-Mobile Park (SEA) | 0.91 | Pitcher-friendly — positive outcomes adjusted up |
| Yankee Stadium (NYY) | 1.00 | Neutral — no adjustment |

Over a season of ~250 home PAs, park factor shifts ELO by ±40 points for extreme parks.

## ELO Tiers

| Tier | ELO Range | Description |
|------|-----------|-------------|
| **Elite** | 1,800+ | MVP-caliber performance |
| **High** | 1,650 – 1,799 | All-Star level |
| **Above Avg** | 1,550 – 1,649 | Above-average starter |
| **Average** | 1,450 – 1,549 | League average |
| **Below Avg** | 1,350 – 1,449 | Below-average performance |
| **Low** | 1,200 – 1,349 | Struggling performance |
| **Cold** | < 1,200 | Significant slump |

## System Architecture

```
[Statcast Parquet] → ETL → [Supabase plate_appearances] → ELO Engine → [player_elo / daily_ohlc]
                                                                ↑
                                                    RE24 Baseline + Park Factors
```

### Pipeline

1. **Raw Data** — Statcast pitch-level parquet (711K rows, 118 columns)
2. **ETL** — Aggregate to plate appearance level, extract `delta_run_exp`, base-out state, venue
3. **ELO Engine (V5.3)** — Process PAs chronologically with park factor + state normalization
4. **Output** — Per-PA ELO detail records + daily OHLC candlestick aggregation
5. **Frontend** — React SPA reading directly from Supabase

### Database (Supabase / PostgreSQL)

| Table | Rows | Description |
|-------|------|-------------|
| `players` | 1,469 | Player metadata (name, team, position) |
| `plate_appearances` | 183,092 | All PAs with delta_run_exp and context |
| `player_elo` | 1,469 | Current ELO + PA count per player |
| `elo_pa_detail` | 183,092 | Per-PA ELO change records |
| `daily_ohlc` | 69,125 | Daily OHLC candlestick data |

### OHLC Candlestick Tracking

Each player's daily ELO is tracked as Open-High-Low-Close, similar to stock charts:
- **Open**: ELO before the first PA of the day
- **High**: Maximum ELO reached during the day
- **Low**: Minimum ELO reached during the day
- **Close**: ELO after the last PA of the day

Green candles (close > open) indicate an ELO gain; red candles indicate a decline.

## Tech Stack

### Engine (Python)
- **pandas** — data processing
- **Supabase Python SDK** — database I/O
- **pytest** — test suite (72 tests)

### Frontend (TypeScript)
- **Vite + React + TypeScript** — build toolchain
- **Tailwind CSS** — utility-first styling
- **@supabase/supabase-js** — direct DB queries (read-only)
- **TanStack React Query** — data fetching and caching
- **Lightweight Charts** — OHLC candlestick visualization
- **React Router** — client-side routing
- **Lucide React** — icons

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase project with credentials

### Engine Setup
```bash
# Install Python dependencies
pip install pandas supabase python-dotenv

# Configure environment
cp .env.example .env
# Edit .env with your Supabase URL and key

# Run ELO calculation
python -m scripts.run_elo
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

The frontend connects directly to Supabase using a read-only anonymous key — no backend server required.

## License

This project is for demonstration and analytical purposes. MLB Statcast data sourced from Baseball Savant.
