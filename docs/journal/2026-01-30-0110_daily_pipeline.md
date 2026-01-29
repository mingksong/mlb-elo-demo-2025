# Daily ELO Automation Pipeline

**Date**: 2026-01-30
**Phase**: 5 — Daily ELO Automation

## Summary

GitHub Actions + pybaseball 기반 일일 자동 ELO 파이프라인 구현.
CI 워크플로우 구성, 실제 Statcast 데이터(2025-09-04)로 integration test 검증 완료.

## Changes

### New Files (14)
| File | Purpose |
|------|---------|
| `src/etl/fetch_statcast.py` | pybaseball wrapper (Regular Season 필터) |
| `src/etl/player_registry.py` | 신규 선수 감지 + MLB Stats API 등록 |
| `src/pipeline/__init__.py` | Pipeline package init |
| `src/pipeline/daily_pipeline.py` | 일일 파이프라인 오케스트레이터 |
| `scripts/daily_elo.py` | CLI entrypoint (--date, --force, --range) |
| `.github/workflows/daily-elo.yml` | GitHub Actions cron (UTC 09:00) |
| `.github/workflows/test.yml` | CI: unit test (자동) + integration (수동) |
| `requirements.txt` | Python dependencies |
| `pytest.ini` | pytest marker 등록 (integration) |
| `tests/test_fetch_statcast_*.py` | pybaseball wrapper tests (13 tests) |
| `tests/test_player_registry_*.py` | Player registry tests (14 tests) |
| `tests/test_daily_pipeline_*.py` | Incremental ELO + pipeline tests (12 tests) |
| `tests/test_integration_daily_pipeline_*.py` | 실제 데이터 end-to-end 검증 (24 tests) |

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

## CI/CD

| Workflow | Trigger | 내용 |
|----------|---------|------|
| `test.yml` (unit) | push/PR to main | `pytest -m "not integration"` — 111 tests |
| `test.yml` (integration) | workflow_dispatch 수동 | `pytest -m integration` — 24 tests (pybaseball 네트워크) |
| `daily-elo.yml` | cron UTC 09:00 / 수동 | 실제 파이프라인 (Supabase 기록) |

보안: `.env`는 `.gitignore`, CI는 GitHub Secrets (`SUPABASE_URL`, `SUPABASE_KEY`)로 주입.

## Key Design Decisions
- **Incremental ELO**: `initial_states` parameter on EloBatch — backward compatible
- **active_only**: Daily upload targets ~50-80 active players instead of 1,469 전체
- **Idempotency**: upsert for PA/ELO, delete-then-insert for OHLC
- **New players**: MLB Stats API (free, no auth), fallback to minimal record
- **Test 분리**: `@pytest.mark.integration` marker로 네트워크 필요 테스트 격리

## Integration Test 결과 (2025-09-04 실제 데이터)
- Fetch: 1,843 pitches, 6 games, Regular Season only
- ETL: 450 PAs, 125 batters, 53 pitchers
- ELO: 178 players, Zero-sum net = +0.0000
- OHLC: 178 records, high ≥ low invariant 검증
- Upload schema: 4개 테이블 레코드 타입/NaN/invariant 검증
- Mock Supabase end-to-end: pipeline 전체 흐름 성공

## Test Results
- **Unit**: 111 passed (72 existing + 39 new)
- **Integration**: 24 passed (실제 Statcast 데이터)
- **CI**: GitHub Actions 40초 통과
- Incremental vs full season ELO parity verified
- Backward compatibility confirmed

## Commits
1. `43e109e` feat(pipeline): daily ELO automation via GitHub Actions + pybaseball
2. `78fb321` feat(ci): add test workflow + integration test with pytest marker
3. `70b71b4` fix(ci): correct pybaseball version constraint (latest is 2.2.7)
