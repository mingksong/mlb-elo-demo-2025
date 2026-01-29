# Phase 1: ETL Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Statcast 2025 parquet 데이터를 KBO ELO 스키마 형태의 plate_appearances로 변환하여 Supabase에 업로드

**Architecture:** Parquet → pandas ETL → Supabase PostgreSQL. event_mapper가 Statcast events를 KBO result_type으로 매핑하고, statcast_to_pa가 투구 단위를 타석 단위로 집계한다.

**Tech Stack:** Python, pandas, pyarrow, supabase-py

---

## 원본 데이터 참조

- **파일**: `/Users/mksong/Documents/mlb-statcast-book/data/raw/statcast_2025.parquet`
- **형태**: 711,897 rows × 118 columns (투구 단위)
- **PA 추출**: `events` IS NOT NULL → ~183,092 타석
- **기간**: 2025.03.27 - 2025.09.28
- **커버리지**: 2,428 경기 / 673 타자 / 873 투수 / 30팀

## KBO V4 엔진 참조

- **파일**: `/Users/mksong/Documents/balltology-elo/src/elo_engine_v4.py`
- 엔진이 필요로 하는 최소 데이터: `pa_id`, `game_id`, `batter_id`, `pitcher_id`, `result_type`
- result_type 유효값: Single, Double, Triple, HR, BB, IBB, HBP, StrikeOut, OUT, SAC, FC, E, GIDP

---

### Task 1: Event Mapper 모듈

**Files:**
- Create: `src/etl/event_mapper.py`
- Test: `tests/test_event_mapper.py`

**Step 1: Write the failing test**

```python
# tests/test_event_mapper.py
from src.etl.event_mapper import EVENT_MAP, map_event, VALID_RESULT_TYPES

def test_event_map_covers_all_statcast_events():
    """22개 Statcast events가 모두 매핑되어야 함."""
    statcast_events = [
        'single', 'double', 'triple', 'home_run',
        'walk', 'intentional_walk', 'hit_by_pitch',
        'strikeout', 'strikeout_double_play',
        'field_out', 'force_out', 'triple_play',
        'grounded_into_double_play', 'double_play',
        'sac_fly', 'sac_bunt', 'sac_fly_double_play',
        'fielders_choice', 'fielders_choice_out',
        'field_error', 'catcher_interf', 'other_out',
    ]
    for event in statcast_events:
        assert event in EVENT_MAP, f"Missing mapping for: {event}"

def test_map_event_basic():
    assert map_event('single') == 'Single'
    assert map_event('home_run') == 'HR'
    assert map_event('walk') == 'BB'
    assert map_event('strikeout') == 'StrikeOut'
    assert map_event('field_out') == 'OUT'
    assert map_event('grounded_into_double_play') == 'GIDP'
    assert map_event('sac_fly') == 'SAC'
    assert map_event('fielders_choice') == 'FC'
    assert map_event('field_error') == 'E'
    assert map_event('catcher_interf') == 'HBP'

def test_map_event_unknown_returns_out_and_logs():
    result = map_event('unknown_event_xyz')
    assert result == 'OUT'

def test_all_mapped_values_are_valid():
    for event, result_type in EVENT_MAP.items():
        assert result_type in VALID_RESULT_TYPES, f"{event} -> {result_type} is not valid"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mksong/Documents/mlb-elo && python -m pytest tests/test_event_mapper.py -v`
Expected: FAIL (module not found)

**Step 3: Write minimal implementation**

```python
# src/etl/event_mapper.py
"""Statcast events → KBO ELO result_type 매핑."""

import logging

logger = logging.getLogger(__name__)

VALID_RESULT_TYPES = {
    'Single', 'Double', 'Triple', 'HR',
    'BB', 'IBB', 'HBP',
    'StrikeOut', 'OUT', 'SAC', 'FC', 'E', 'GIDP',
}

EVENT_MAP = {
    'single': 'Single',
    'double': 'Double',
    'triple': 'Triple',
    'home_run': 'HR',
    'walk': 'BB',
    'intentional_walk': 'IBB',
    'hit_by_pitch': 'HBP',
    'strikeout': 'StrikeOut',
    'strikeout_double_play': 'StrikeOut',
    'field_out': 'OUT',
    'force_out': 'OUT',
    'triple_play': 'OUT',
    'grounded_into_double_play': 'GIDP',
    'double_play': 'GIDP',
    'sac_fly': 'SAC',
    'sac_bunt': 'SAC',
    'sac_fly_double_play': 'SAC',
    'fielders_choice': 'FC',
    'fielders_choice_out': 'FC',
    'field_error': 'E',
    'catcher_interf': 'HBP',
    'other_out': 'OUT',
}

def map_event(event: str) -> str:
    result = EVENT_MAP.get(event)
    if result is None:
        logger.warning(f"Unknown Statcast event: '{event}' → defaulting to 'OUT'")
        return 'OUT'
    return result
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mksong/Documents/mlb-elo && python -m pytest tests/test_event_mapper.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/etl/event_mapper.py tests/test_event_mapper.py
git commit -m "feat(etl): Statcast events → result_type 매핑 모듈"
```

---

### Task 2: Statcast → Plate Appearance 변환 모듈

**Files:**
- Create: `src/etl/statcast_to_pa.py`
- Test: `tests/test_statcast_to_pa.py`

**Step 1: Write the failing test**

```python
# tests/test_statcast_to_pa.py
import pandas as pd
from src.etl.statcast_to_pa import convert_statcast_to_pa

def _make_statcast_row(**overrides):
    """테스트용 Statcast 행 생성."""
    defaults = {
        'game_pk': 717001,
        'game_date': pd.Timestamp('2025-04-01'),
        'game_year': 2025,
        'batter': 660271,
        'pitcher': 543037,
        'events': 'single',
        'at_bat_number': 1,
        'pitch_number': 3,
        'inning': 1,
        'inning_topbot': 'Top',
        'outs_when_up': 0,
        'on_1b': None,
        'on_2b': None,
        'on_3b': None,
        'home_team': 'NYY',
        'away_team': 'BOS',
        'bat_score': 0,
        'fld_score': 0,
        'launch_speed': 95.2,
        'launch_angle': 12.0,
        'estimated_woba_using_speedangle': 0.380,
        'delta_run_exp': 0.45,
    }
    defaults.update(overrides)
    return defaults

def test_filters_to_pa_only():
    """events가 NOT NULL인 행만 추출."""
    rows = [
        _make_statcast_row(events='single', pitch_number=3),
        _make_statcast_row(events=None, pitch_number=1),
        _make_statcast_row(events=None, pitch_number=2),
    ]
    df = pd.DataFrame(rows)
    result = convert_statcast_to_pa(df)
    assert len(result) == 1

def test_result_type_mapping():
    """events → result_type 변환."""
    rows = [
        _make_statcast_row(events='home_run', at_bat_number=1),
        _make_statcast_row(events='strikeout', at_bat_number=2),
        _make_statcast_row(events='walk', at_bat_number=3),
    ]
    df = pd.DataFrame(rows)
    result = convert_statcast_to_pa(df)
    assert list(result['result_type']) == ['HR', 'StrikeOut', 'BB']

def test_pa_id_generation():
    """pa_id = game_pk * 1000 + at_bat_number."""
    rows = [_make_statcast_row(game_pk=717001, at_bat_number=5)]
    df = pd.DataFrame(rows)
    result = convert_statcast_to_pa(df)
    assert result.iloc[0]['pa_id'] == 717001 * 1000 + 5

def test_sort_order():
    """game_date, game_pk, at_bat_number 순 정렬."""
    rows = [
        _make_statcast_row(game_date=pd.Timestamp('2025-04-02'), game_pk=717002, at_bat_number=1, events='single'),
        _make_statcast_row(game_date=pd.Timestamp('2025-04-01'), game_pk=717001, at_bat_number=2, events='double'),
        _make_statcast_row(game_date=pd.Timestamp('2025-04-01'), game_pk=717001, at_bat_number=1, events='triple'),
    ]
    df = pd.DataFrame(rows)
    result = convert_statcast_to_pa(df)
    assert list(result['at_bat_number']) == [1, 2, 1]
    assert list(result['game_pk']) == [717001, 717001, 717002]

def test_base_runner_boolean_conversion():
    """주자 유무를 boolean으로 변환."""
    rows = [_make_statcast_row(on_1b=660271.0, on_2b=None, on_3b=543037.0)]
    df = pd.DataFrame(rows)
    result = convert_statcast_to_pa(df)
    assert result.iloc[0]['on_1b'] == True
    assert result.iloc[0]['on_2b'] == False
    assert result.iloc[0]['on_3b'] == True

def test_output_columns():
    """출력 DataFrame에 필요한 컬럼이 모두 존재."""
    rows = [_make_statcast_row()]
    df = pd.DataFrame(rows)
    result = convert_statcast_to_pa(df)
    required = [
        'pa_id', 'game_pk', 'game_date', 'season_year',
        'batter_id', 'pitcher_id', 'result_type',
        'inning', 'inning_half', 'at_bat_number', 'outs_when_up',
        'on_1b', 'on_2b', 'on_3b',
        'home_team', 'away_team', 'bat_score', 'fld_score',
        'launch_speed', 'launch_angle', 'xwoba', 'delta_run_exp',
    ]
    for col in required:
        assert col in result.columns, f"Missing column: {col}"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/mksong/Documents/mlb-elo && python -m pytest tests/test_statcast_to_pa.py -v`
Expected: FAIL (module not found)

**Step 3: Write minimal implementation**

```python
# src/etl/statcast_to_pa.py
"""Statcast 투구 데이터 → 타석(PA) 단위 변환."""

import pandas as pd
from src.etl.event_mapper import map_event

def convert_statcast_to_pa(statcast_df: pd.DataFrame) -> pd.DataFrame:
    # 1. PA만 추출 (events가 NOT NULL)
    pa_df = statcast_df[statcast_df['events'].notna()].copy()

    # 2. result_type 매핑
    pa_df['result_type'] = pa_df['events'].apply(map_event)

    # 3. 컬럼 변환
    pa_df['season_year'] = pa_df['game_year'] if 'game_year' in pa_df.columns else pd.to_datetime(pa_df['game_date']).dt.year
    pa_df['batter_id'] = pa_df['batter'].astype(int)
    pa_df['pitcher_id'] = pa_df['pitcher'].astype(int)
    pa_df['inning_half'] = pa_df['inning_topbot']
    pa_df['on_1b'] = pa_df['on_1b'].notna()
    pa_df['on_2b'] = pa_df['on_2b'].notna()
    pa_df['on_3b'] = pa_df['on_3b'].notna()
    pa_df['xwoba'] = pa_df.get('estimated_woba_using_speedangle')

    # 4. PA ID 생성
    pa_df['pa_id'] = pa_df['game_pk'].astype(int) * 1000 + pa_df['at_bat_number'].astype(int)

    # 5. 정렬
    pa_df = pa_df.sort_values(['game_date', 'game_pk', 'at_bat_number']).reset_index(drop=True)

    # 6. 출력 컬럼 선택
    output_columns = [
        'pa_id', 'game_pk', 'game_date', 'season_year',
        'batter_id', 'pitcher_id', 'result_type',
        'inning', 'inning_half', 'at_bat_number', 'outs_when_up',
        'on_1b', 'on_2b', 'on_3b',
        'home_team', 'away_team', 'bat_score', 'fld_score',
        'launch_speed', 'launch_angle', 'xwoba', 'delta_run_exp',
    ]
    return pa_df[output_columns]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/mksong/Documents/mlb-elo && python -m pytest tests/test_statcast_to_pa.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add src/etl/statcast_to_pa.py tests/test_statcast_to_pa.py
git commit -m "feat(etl): Statcast → plate_appearances 변환 모듈"
```

---

### Task 3: 실제 데이터 변환 검증 스크립트

**Files:**
- Create: `scripts/validate_etl.py`

**Step 1: Write validation script**

```python
# scripts/validate_etl.py
"""실제 Statcast 2025 데이터로 ETL 결과 검증."""

import pandas as pd
from src.etl.statcast_to_pa import convert_statcast_to_pa

STATCAST_PATH = '/Users/mksong/Documents/mlb-statcast-book/data/raw/statcast_2025.parquet'

def main():
    print("Loading Statcast 2025...")
    raw = pd.read_parquet(STATCAST_PATH)
    print(f"  Raw rows: {len(raw):,}")

    print("\nConverting to PA...")
    pa = convert_statcast_to_pa(raw)
    print(f"  PA rows: {len(pa):,}")

    print("\n--- result_type 분포 ---")
    print(pa['result_type'].value_counts().to_string())

    print(f"\n--- 기본 통계 ---")
    print(f"  Unique games: {pa['game_pk'].nunique():,}")
    print(f"  Unique batters: {pa['batter_id'].nunique():,}")
    print(f"  Unique pitchers: {pa['pitcher_id'].nunique():,}")
    print(f"  Date range: {pa['game_date'].min()} ~ {pa['game_date'].max()}")

    print(f"\n--- PA ID 유일성 ---")
    duplicates = pa['pa_id'].duplicated().sum()
    print(f"  Duplicate pa_id: {duplicates}")
    if duplicates > 0:
        print("  ⚠️ PA ID 충돌 발견! game_pk * 1000 + at_bat_number 공식 재검토 필요")

    print(f"\n--- NULL 체크 ---")
    for col in ['pa_id', 'game_pk', 'batter_id', 'pitcher_id', 'result_type']:
        null_count = pa[col].isna().sum()
        print(f"  {col}: {null_count} nulls")

    # 로컬 저장 (검증용)
    output_path = 'data/plate_appearances_2025.parquet'
    pa.to_parquet(output_path, index=False)
    print(f"\n✅ Saved to {output_path}")

if __name__ == '__main__':
    main()
```

**Step 2: Run validation**

Run: `cd /Users/mksong/Documents/mlb-elo && python scripts/validate_etl.py`
Expected: ~183K PA, result_type 분포 출력, PA ID 유일성 확인

**Step 3: Commit**

```bash
git add scripts/validate_etl.py
git commit -m "feat(etl): 실제 데이터 ETL 검증 스크립트"
```

---

### Task 4: Supabase 업로드 모듈

**Files:**
- Create: `src/etl/upload_to_supabase.py`
- Create: `.env.example`
- Test: `tests/test_upload_to_supabase.py`

**의존성:** Supabase 프로젝트 생성 및 API 키 설정 필요 (수동 작업)

**Step 1: .env.example 생성**

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
```

**Step 2: Write upload module**

```python
# src/etl/upload_to_supabase.py
"""Plate appearances DataFrame → Supabase 업로드."""

import os
import pandas as pd
from supabase import create_client

def get_supabase_client():
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_KEY']
    return create_client(url, key)

def upload_plate_appearances(pa_df: pd.DataFrame, batch_size: int = 1000):
    client = get_supabase_client()
    records = pa_df.to_dict('records')

    # game_date를 문자열로 변환 (JSON 직렬화)
    for r in records:
        if hasattr(r['game_date'], 'isoformat'):
            r['game_date'] = r['game_date'].isoformat()[:10]
        # NaN → None
        for k, v in r.items():
            if pd.isna(v):
                r[k] = None

    uploaded = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        client.table('plate_appearances').upsert(batch).execute()
        uploaded += len(batch)
        print(f"  Uploaded {uploaded:,} / {len(records):,}")

    print(f"✅ Total uploaded: {uploaded:,}")
    return uploaded
```

**Step 3: Commit**

```bash
git add src/etl/upload_to_supabase.py .env.example
git commit -m "feat(etl): Supabase 업로드 모듈"
```

---

## 실행 순서 요약

1. **Task 1**: event_mapper.py (테스트 → 구현 → 커밋)
2. **Task 2**: statcast_to_pa.py (테스트 → 구현 → 커밋)
3. **Task 3**: validate_etl.py (실제 데이터 검증 → 커밋)
4. **Task 4**: upload_to_supabase.py (Supabase 업로드 → 커밋)

Phase 1 완료 기준:
- [ ] 183K PA 변환 성공
- [ ] result_type 분포가 합리적 (OUT > Single > StrikeOut > BB > Double > HR ...)
- [ ] PA ID 유일성 보장
- [ ] Supabase에 데이터 업로드 완료
