# MLB ELO System Design

## 개요

KBO Dual ELO (V4) 엔진을 MLB Statcast 데이터에 적용하는 시스템 설계.
MVP 우선 구현 후 Statcast 고유 데이터를 활용한 확장을 목표로 한다.

- **데이터 소스**: MLB Statcast 2025 (711,897 투구 / ~183,092 타석)
- **백엔드**: Supabase (PostgreSQL)
- **엔진**: KBO V4 Dual ELO 복사 → MLB용 리팩터링
- **프로젝트**: 별도 레포 (`mlb-elo`)

---

## 1. 프로젝트 구조

```
mlb-elo/
├── src/
│   ├── etl/
│   │   ├── statcast_to_pa.py      # Statcast 투구 → 타석 변환
│   │   ├── event_mapper.py         # events → result_type 매핑
│   │   └── upload_to_supabase.py   # Supabase에 업로드
│   ├── engine/
│   │   ├── elo_engine_v4.py        # KBO V4 복사 → MLB용 리팩터링
│   │   └── elo_config.py           # 파라미터 설정 (확장 가능)
│   └── api/                        # (향후) Supabase Edge Functions
├── tests/
├── config/
│   └── mlb_elo_config.yaml
├── scripts/
│   └── run_elo.py                  # 전체 파이프라인 실행
├── docs/
│   └── plans/
└── data/                           # 로컬 캐시 (gitignore)
```

---

## 2. 데이터 파이프라인

### 흐름

```
[Statcast Parquet]          [Supabase]              [ELO Engine]
711K 투구 rows    →  ETL  → plate_appearances 테이블 → ELO 계산
  (pitch-level)      ↓       (PA-level, ~183K rows)    ↓
                event_mapper                      elo_results 테이블
                     ↓                            player_elo 테이블
              result_type 정규화
```

### ETL 핵심 로직

```python
# 1. PA 추출: events가 NOT NULL인 행만 필터
pa_df = statcast_df[statcast_df['events'].notna()].copy()

# 2. result_type 매핑
EVENT_MAP = {
    'single': 'Single', 'double': 'Double', 'triple': 'Triple',
    'home_run': 'HR', 'walk': 'BB', 'intentional_walk': 'IBB',
    'hit_by_pitch': 'HBP', 'strikeout': 'StrikeOut',
    'strikeout_double_play': 'StrikeOut',
    'field_out': 'OUT', 'force_out': 'OUT', 'triple_play': 'OUT',
    'grounded_into_double_play': 'GIDP', 'double_play': 'GIDP',
    'sac_fly': 'SAC', 'sac_bunt': 'SAC', 'sac_fly_double_play': 'SAC',
    'fielders_choice': 'FC', 'fielders_choice_out': 'FC',
    'field_error': 'E', 'catcher_interf': 'HBP', 'other_out': 'OUT',
}
pa_df['result_type'] = pa_df['events'].map(EVENT_MAP)

# 3. PA 정렬: 시간순 + 이닝순 + 타석순
pa_df = pa_df.sort_values(['game_date', 'game_pk', 'at_bat_number'])

# 4. PA ID 생성
pa_df['pa_id'] = pa_df['game_pk'] * 1000 + pa_df['at_bat_number']
```

---

## 3. Supabase 스키마

### plate_appearances (ETL 결과)

```sql
CREATE TABLE plate_appearances (
  pa_id          BIGINT PRIMARY KEY,  -- game_pk * 1000 + at_bat_number
  game_pk        INTEGER NOT NULL,
  game_date      DATE NOT NULL,
  season_year    INTEGER NOT NULL,
  batter_id      INTEGER NOT NULL,
  pitcher_id     INTEGER NOT NULL,
  result_type    VARCHAR(20) NOT NULL,
  inning         SMALLINT NOT NULL,
  inning_half    VARCHAR(3) NOT NULL,  -- Top/Bot
  at_bat_number  SMALLINT NOT NULL,
  outs_when_up   SMALLINT NOT NULL,
  on_1b          BOOLEAN DEFAULT FALSE,
  on_2b          BOOLEAN DEFAULT FALSE,
  on_3b          BOOLEAN DEFAULT FALSE,
  home_team      VARCHAR(3),
  away_team      VARCHAR(3),
  bat_score      SMALLINT,
  fld_score      SMALLINT,
  -- Statcast 확장 필드 (향후 활용)
  launch_speed   REAL,
  launch_angle   REAL,
  xwoba          REAL,
  delta_run_exp  REAL
);

CREATE INDEX idx_pa_game ON plate_appearances(game_pk);
CREATE INDEX idx_pa_batter ON plate_appearances(batter_id);
CREATE INDEX idx_pa_pitcher ON plate_appearances(pitcher_id);
CREATE INDEX idx_pa_date ON plate_appearances(game_date);
```

### player_elo (ELO 결과)

```sql
CREATE TABLE player_elo (
  player_id      INTEGER PRIMARY KEY,
  player_name    VARCHAR(100),
  player_type    VARCHAR(10),  -- 'batter' or 'pitcher'
  on_base_elo    REAL DEFAULT 1500.0,
  power_elo      REAL DEFAULT 1500.0,
  composite_elo  REAL DEFAULT 1500.0,
  pa_count       INTEGER DEFAULT 0,
  last_game_date DATE
);
```

### elo_pa_detail (PA별 ELO 변동)

```sql
CREATE TABLE elo_pa_detail (
  pa_id              BIGINT PRIMARY KEY,
  batter_id          INTEGER,
  pitcher_id         INTEGER,
  result_type        VARCHAR(20),
  batter_elo_before  REAL,
  batter_elo_after   REAL,
  pitcher_elo_before REAL,
  pitcher_elo_after  REAL,
  on_base_delta      REAL,
  power_delta        REAL
);

CREATE INDEX idx_elo_detail_batter ON elo_pa_detail(batter_id);
CREATE INDEX idx_elo_detail_pitcher ON elo_pa_detail(pitcher_id);
```

---

## 4. Statcast events → result_type 매핑

| Statcast `events` | `result_type` | ELO 처리 |
|---|---|---|
| single | Single | On-base 0.43 / Power 0.0 |
| double | Double | On-base 0.55 / Power 0.25 |
| triple | Triple | On-base 0.65 / Power 0.50 |
| home_run | HR | On-base 0.75 / Power 0.75 |
| walk | BB | On-base 0.32 / Power 0.0 |
| intentional_walk | IBB | On-base 0.32 / Power 0.0 |
| hit_by_pitch | HBP | On-base 0.34 / Power 0.0 |
| strikeout | StrikeOut | On-base -0.27 / Power 0.0 |
| strikeout_double_play | StrikeOut | On-base -0.27 / Power 0.0 |
| field_out | OUT | On-base -0.25 / Power -0.10 |
| force_out | OUT | On-base -0.25 / Power -0.10 |
| triple_play | OUT | On-base -0.25 / Power -0.10 |
| grounded_into_double_play | GIDP | On-base -0.25 / Power -0.10 |
| double_play | GIDP | On-base -0.25 / Power -0.10 |
| sac_fly | SAC | On-base 0.0 / Power 0.0 |
| sac_bunt | SAC | On-base 0.0 / Power 0.0 |
| sac_fly_double_play | SAC | On-base 0.0 / Power 0.0 |
| fielders_choice | FC | On-base -0.25 / Power -0.10 |
| fielders_choice_out | FC | On-base -0.25 / Power -0.10 |
| field_error | E | On-base 0.43 / Power 0.0 |
| catcher_interf | HBP | On-base 0.34 / Power 0.0 |
| other_out | OUT | On-base -0.25 / Power -0.10 |

---

## 5. ELO 엔진 리팩터링

### 변경 사항

| 항목 | KBO | MLB |
|---|---|---|
| 데이터 소스 | PostgreSQL 직접 조회 | Supabase Python Client |
| 선수 식별자 | batter_pcode (문자열) | batter_id (정수) |
| 이닝 표기 | B/T | Bot/Top |
| FULL_RELIABILITY_PA | 400 | 502 (MLB 시즌 평균 PA) |

### 보존 사항 (변경 없음)

- Dual ELO 공식 (On-base + Power)
- Zero-Sum 보장 로직
- K-factor 체계 (K_BASE=12.0, Rookie 1.4x, Veteran 0.7x, Adaptive max 2x)
- ALPHA=0.45, SCALE_ON_BASE=5.0, SCALE_POWER=10.0
- Reliability 조정, 시즌 회귀/정규화

### 확장 포인트

```python
class EloEngine:
    def calculate_weight(self, result_type: str, context: dict) -> tuple:
        """확장 포인트: context에 launch_speed, xwoba 등 추가 가능"""
        on_base_w = self.ON_BASE_WEIGHTS.get(result_type, 0)
        power_w = self.POWER_WEIGHTS.get(result_type, 0)
        return on_base_w, power_w
```

---

## 6. 구현 로드맵

### Phase 1: ETL 파이프라인
- statcast_to_pa.py: Parquet → PA 변환 + result_type 매핑
- upload_to_supabase.py: Supabase 테이블 생성 + 데이터 업로드
- 검증: 183K PA 변환 완료, result_type 분포 크로스체크

### Phase 2: ELO 엔진 포팅
- KBO V4 엔진 복사 → 데이터 소스 Supabase로 교체
- FULL_RELIABILITY_PA = 502로 조정
- 확장 hook 추가
- 검증: 단일 경기 수동 계산 vs 엔진 출력 대조

### Phase 3: 전체 시즌 실행 + 검증
- 2025 시즌 전체 ELO 계산 실행
- Supabase에 결과 저장
- 검증 기준:
  - ELO 분포: 평균 1500, std ~145
  - Zero-Sum: 전체 ELO 합 = 초기값
  - Composite ELO vs wOBA 상관관계 (r > 0.7 목표)
  - Power ELO vs ISO 상관관계
  - 상위 10명 = 실제 MLB 스타 일치 여부

### Phase 4 (향후): Statcast Enhanced
- launch_speed/angle 기반 Power ELO 보강
- xwOBA 기반 가중치 동적 조정
- 멀티시즌 확장 (2015-2025)

---

## 7. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| Statcast events에 누락/미지 이벤트 | ETL에서 미매핑 이벤트 로깅, OUT으로 안전 처리 |
| 단일 시즌이라 ELO 수렴 부족 | 초기값 1500 시작, 충분한 PA 후 검증 |
| KBO 파라미터가 MLB에 부적합 | Phase 3 검증에서 상관관계 낮으면 파라미터 튜닝 |
| Supabase 무료 플랜 용량 | ~183K PA + ~1.5K 선수 = 충분 |

---

## 8. 원본 데이터 참조

- **파일**: `/Users/mksong/Documents/mlb-statcast-book/data/raw/statcast_2025.parquet`
- **형태**: 711,897 rows × 118 columns (투구 단위)
- **기간**: 2025.03.27 - 2025.09.28
- **커버리지**: 2,428 경기 / 673 타자 / 873 투수 / 30팀

---

*설계일: 2026-01-29*
*기반: KBO Dual ELO V4 (balltology-elo)*
