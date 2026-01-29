# MLB ELO System

MLB Statcast 기반 Dual ELO Rating System

## 프로젝트 개요

- **목적**: MLB Statcast 데이터를 활용한 선수 ELO 레이팅
- **기반**: KBO V5.3 Zero-Sum ELO (balltology-elo) 포팅
- **데이터**: Statcast 2025 (투구 단위 → 타석 단위 변환)
- **백엔드**: Supabase (PostgreSQL)
- **설계 문서**: [docs/plans/2026-01-29-mlb-elo-system-design.md](docs/plans/2026-01-29-mlb-elo-system-design.md)

## 빠른 참조

### Supabase 접속
```bash
# .env 파일에 설정
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
```

### 주요 테이블
- `players`: 1,469 선수 메타데이터
- `plate_appearances`: 183,092 타석 (2025 시즌)
- `player_elo`: 선수별 ELO 현황 (1,469)
- `elo_pa_detail`: PA별 ELO 변동 기록 (183,092)
- `daily_ohlc`: 일별 OHLC 캔들스틱 (69,125)

### 원본 데이터
- `/Users/mksong/Documents/mlb-statcast-book/data/raw/statcast_2025.parquet`
- 711,897 투구 / 118 컬럼 / 2,428 경기

## 문서 구조

| 문서 | 용도 |
|------|------|
| [docs/plans/2026-01-29-mlb-elo-system-design.md](docs/plans/2026-01-29-mlb-elo-system-design.md) | 전체 시스템 설계 |

## 개발 규칙

- 테스트 파일: `tests/test_{기능명}_YYMMDDHHMMSS.py`
- 커밋: `feat/fix/refactor(모듈): 내용`
- Python: pandas 활용
- **TDD 필수**: 테스트 먼저 작성 → RED → GREEN → REFACTOR

### 개발일지 (필수)

**모든 작업 세션 종료 시 개발일지 작성 필수.**

- 위치: `docs/journal/YYYY-MM-DD-HHMM_{작업내용}.md`
- 작성 후 반드시 git commit과 함께 커밋

## 아키텍처

```
[Statcast Parquet] → ETL → [Supabase plate_appearances] → ELO Engine → [Supabase player_elo]
```

### ELO 엔진 (V5.3 Zero-Sum)

| 파라미터 | 값 | 설명 |
|---------|-----|------|
| K_FACTOR | 12.0 | K-factor (delta = K × delta_run_exp) |
| INITIAL_ELO | 1500.0 | 리그 평균 기준점 |
| MIN_ELO | 500.0 | ELO 하한선 |

**공식**: `batter_delta = K × delta_run_exp`, `pitcher_delta = -batter_delta` (Zero-Sum)

### 프론트엔드
- **언어**: English
- **대상**: US MLB fans
- **목적**: 2025 시즌 ELO 데이터 데모 페이지

---

*최종 업데이트: 2026-01-29*
