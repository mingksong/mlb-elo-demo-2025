# Daily ELO Automation Pipeline

**Date**: 2026-01-30 01:10
**Phase**: 5 — Daily ELO Automation

## Summary

GitHub Actions + pybaseball 기반 일일 자동 ELO 파이프라인 구현.

## Changes

### New Files (10)
| File | Purpose |
|------|---------|
| `src/etl/fetch_statcast.py` | pybaseball wrapper (Regular Season 필터) |
| `src/etl/player_registry.py` | 신규 선수 감지 + MLB Stats API 등록 |
| `src/pipeline/__init__.py` | Pipeline package init |
| `src/pipeline/daily_pipeline.py` | 일일 파이프라인 오케스트레이터 |
| `scripts/daily_elo.py` | CLI entrypoint (--date, --force, --range) |
| `.github/workflows/daily-elo.yml` | GitHub Actions cron (UTC 09:00) |
| `requirements.txt` | Python dependencies |
| `tests/test_fetch_statcast_*.py` | pybaseball wrapper tests (13 tests) |
| `tests/test_player_registry_*.py` | Player registry tests (14 tests) |
| `tests/test_daily_pipeline_*.py` | Incremental ELO + pipeline tests (12 tests) |

### Modified Files (1)
| File | Change |
|------|--------|
| `src/engine/elo_batch.py` | `initial_states` param, `_active_player_ids` tracking, `active_only` filter |

## Architecture

```
GitHub Actions cron (UTC 09:00)
  → pybaseball.statcast(yesterday)
  → game_type == 'R' filter (Regular Season only)
  → ETL: pitch → PA (reuse statcast_to_pa)
  → New player detection + MLB Stats API registration
  → Incremental ELO (EloBatch with initial_states)
  → Supabase upload (active_only players)
```

## Key Design Decisions
- **Incremental ELO**: `initial_states` parameter on EloBatch — backward compatible
- **active_only**: Daily upload targets ~50-80 active players instead of 1,469 全体
- **Idempotency**: upsert for PA/ELO, delete-then-insert for OHLC
- **New players**: MLB Stats API (free, no auth), fallback to minimal record

## Test Results
- **111 passed** (72 existing + 39 new), 0 failures
- Incremental vs full season ELO parity verified
- Backward compatibility confirmed
