# Phase 2: V5.3 ELO Engine Porting

**Date**: 2026-01-29
**Phase**: Phase 2 - ELO Engine

## Summary

KBO V5.3 Zero-Sum ELO Engine을 MLB Statcast 데이터에 포팅하여
2025 시즌 전체 ELO를 계산하고 Supabase에 업로드 완료.

## Key Decisions

1. **V5.3 (not V4)**: 사용자 요청으로 V5.3 Zero-Sum 엔진 사용
   - V4: On-base + Power Dual ELO (result_type 가중치)
   - V5.3: 단일 차원 ELO (delta_run_exp 기반, Zero-Sum)
2. **Park Factor 미적용**: MLB 파크 팩터 데이터 없음 (향후 추가 가능)
3. **State Normalization 불필요**: delta_run_exp가 이미 상태(base-out) 정규화 포함
4. **단일 시즌**: Career ELO 없이 Season ELO만 계산

## Formula

```
batter_delta = K × delta_run_exp
pitcher_delta = -batter_delta  (Zero-Sum)
K = 12.0, INITIAL_ELO = 1500.0, MIN_ELO = 500.0
```

## Results

| Metric | Value |
|--------|-------|
| Players | 1,469 |
| Total PAs | 183,092 |
| ELO Mean | 1500.0 |
| ELO Std | 119.6 |
| ELO Min | 993.9 |
| ELO Max | 2403.6 |
| Zero-Sum Net | +0.00 |
| OHLC Records | 69,125 |

### Top 10 Batters (PA >= 100)

| Rank | Player | ELO | PA | Cumulative RV |
|------|--------|-----|-----|---------------|
| 1 | Aaron Judge | 2403.6 | 679 | +75.3 |
| 2 | Shohei Ohtani | 2312.3 | 904 | +67.7 |
| 3 | Juan Soto | 2121.6 | 716 | +51.8 |
| 4 | Kyle Schwarber | 2069.3 | 726 | +47.4 |
| 5 | George Springer | 2057.0 | 586 | +46.4 |
| 6 | Cal Raleigh | 2051.1 | 706 | +45.9 |
| 7 | Nick Kurtz | 1982.3 | 490 | +40.2 |
| 8 | Geraldo Perdomo | 1971.0 | 723 | +39.3 |
| 9 | Pete Alonso | 1934.0 | 709 | +36.2 |
| 10 | Michael Busch | 1923.7 | 586 | +35.3 |

## Supabase Tables

| Table | Rows | Status |
|-------|------|--------|
| players | 1,469 | Phase 1 |
| plate_appearances | 183,092 | Phase 1 |
| player_elo | 1,469 | Phase 2 |
| elo_pa_detail | 183,092 | Phase 2 |
| daily_ohlc | 69,125 | Phase 2 |

## Files Created

- `src/engine/elo_config.py` - Constants
- `src/engine/elo_calculator.py` - Core ELO calculator
- `src/engine/elo_batch.py` - Batch processor + OHLC tracking
- `scripts/run_elo.py` - Full season pipeline
- `tests/test_elo_engine.py` - 13 tests
- `tests/test_elo_batch.py` - 9 tests

## Test Coverage

- 48 total tests (all pass)
- Engine: zero-sum, delta formula, min ELO clamp, null RV handling
- Batch: OHLC single/multi-day, PA detail records, player ELO records

## Next Steps

- Phase 3: Frontend demo page (English, US MLB fans target)
