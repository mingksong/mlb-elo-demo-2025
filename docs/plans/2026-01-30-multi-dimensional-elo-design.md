# Multi-Dimensional ELO System Design

> Hybrid A1+C2: xwOBA-Enhanced K-Modulation Architecture

**날짜**: 2026-01-30
**기반**: [Expert Panel Discussion](2026-01-30-multi-elo-expert-panel-discussion.md)
**현재 시스템**: V5.3 Zero-Sum ELO (batting_elo + pitching_elo)

---

## 1. 설계 목표

### 1.1 핵심 질문

> 현재 `delta_run_exp` 단일 신호에 의존하는 V5.3 ELO를,
> MLB Statcast 물리 데이터(EV, LA, xwOBA)를 활용하여 어떻게 강화할 것인가?

### 1.2 설계 원칙

1. **Statcast 가치 극대화**: KBO에서 불가능했던 물리 측정 데이터를 적극 활용
2. **Zero-Sum 불변**: `pitcher_delta = -batter_delta` 유지
3. **100% 커버리지**: 모든 PA가 ELO 업데이트에 기여
4. **점진적 검증**: 단계별 구현, 각 단계에서 A/B 검증
5. **하위 호환**: 기존 V5.3 인터페이스/테스트 유지

### 1.3 KBO 시스템 대비 개선점

| 항목 | KBO (balltology-elo) | MLB (이 설계) |
|------|---------------------|--------------|
| 물리 데이터 | 없음 | EV, LA, xwOBA |
| BIP 품질 측정 | BABIP 기반 (K=4.0, 노이즈) | EV+LA 직접 측정 |
| 커버리지 | 100% (이벤트 기반) | 100% (이벤트 기반 + BIP 물리 보강) |
| K-factor | 차원별 고정 K | 이벤트 유형 × 물리 품질 가변 K |
| 차원 수 | 9D (5 batter + 4 pitcher) | Phase 1-3: 2D → 향후 확장 |

---

## 2. 아키텍처

### 2.1 Hybrid A1+C2: K-Modulation

전문가 패널의 합의 결과, 두 레이어의 결합 방식으로 **K-modulation**을 채택:

```
                    ┌─────────────────────┐
                    │    Plate Appearance  │
                    │   (delta_run_exp,    │
                    │    result_type,      │
                    │    launch_speed,     │
                    │    launch_angle,     │
                    │    xwoba)            │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Layer 1: C2 Event  │
                    │  K_base = f(type)   │
                    │  HR→15, K→6, BB→6   │
                    │  OUT→10, Hit→12     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Layer 2: A1 Physics │
                    │  (BIP only)         │
                    │  modifier = g(xwOBA) │
                    │  or g(EV, LA)       │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  K_effective =       │
                    │  K_base × modifier  │
                    │                     │
                    │  batter_delta =     │
                    │    K_eff × rv_diff  │
                    │  pitcher_delta =    │
                    │    -batter_delta    │
                    └─────────────────────┘
```

### 2.2 왜 K-Modulation인가

| 방식 | 설명 | 문제점 |
|------|------|--------|
| Additive | `delta = C2_delta + A1_delta` | BIP에서 이중 카운팅, zero-sum 추가 관리 |
| Multiplicative | `delta = K × rv_diff × (1 + β × quality)` | rv_diff가 클 때 노이즈 증폭 |
| **K-Modulation** | `delta = K_eff(event, physics) × rv_diff` | **Zero-sum 자동 유지, 기존 엔진 자연 확장** |

K-Modulation은 기존 `EloCalculator.process_plate_appearance()`의 `self.k_factor * rv_diff` 라인을
`k_effective * rv_diff`로 교체하는 것만으로 구현 가능.

---

## 3. Layer 1: C2 Event K-Factor Table

### 3.1 이벤트별 K-Factor

모든 PA에 적용 (100% 커버리지). 이벤트 유형의 신호 신뢰도에 비례하여 K를 조절.

| result_type | K_base | 근거 |
|-------------|--------|------|
| `HR` | 15.0 | 방어/운 무관, 최고 신뢰도 |
| `Triple` | 14.0 | 강한 타구 + 주루, 높은 신뢰도 |
| `Double` | 12.0 | 실력 신호 높음 |
| `Single` | 10.0 | BABIP 노이즈 포함 |
| `OUT` | 10.0 | BIP out, BABIP 노이즈 |
| `GIDP` | 10.0 | 약한 타구 신호 |
| `FC` | 10.0 | 혼합 상황 |
| `StrikeOut` | 6.0 | 높은 확실성이지만 낮은 delta 이벤트 |
| `BB` | 6.0 | 높은 확실성이지만 낮은 delta 이벤트 |
| `IBB` | 3.0 | 전략적 선택, 실력 신호 미약 |
| `HBP` | 3.0 | 우연적 요소 큼 |
| `SAC` | 3.0 | 전략적 선택 |
| `E` | 0.0 | 수비 에러, 실력 무관 (기존 로직 유지) |

### 3.2 유효 K 분석

2025 시즌 이벤트 분포 기준 가중 평균 K:

```
K_effective_avg ≈ Σ(K_event × P(event)) ≈ 9.5~10.5
```

현재 V5.3의 K=12 대비 약간 낮으나, Layer 2 physics modifier가 BIP에서 K를 증폭하므로 실질 K는 유사.

---

## 4. Layer 2: A1 Physics Modifier

### 4.1 Phase 1: xwOBA 기반 (권장 시작점)

`plate_appearances` 테이블에 이미 `xwoba` 필드가 99% 커버리지로 존재.
xwOBA는 MLB가 EV+LA+sprint_speed를 모델링한 결과물 → 물리 신호를 간접 활용.

```python
def calculate_physics_modifier(
    result_type: str,
    xwoba: Optional[float],
    league_avg_xwoba: float = 0.315,  # 2025 시즌 평균
) -> float:
    """
    BIP 이벤트의 물리 품질에 따라 K-factor modifier 반환.

    - Non-BIP (K, BB, HBP 등): modifier = 1.0 (C2 Layer만 적용)
    - BIP (hit, out, etc.): xwOBA 기반 modifier (0.7 ~ 1.3)
    """
    NON_BIP_TYPES = {'StrikeOut', 'BB', 'IBB', 'HBP', 'SAC', 'E'}

    if result_type in NON_BIP_TYPES:
        return 1.0

    if xwoba is None:
        return 1.0  # fallback: xwoba 없으면 modifier 미적용

    # xwOBA 편차를 modifier로 변환
    # xwOBA 범위: ~0.0 ~ ~2.0, 리그 평균 ~0.315
    deviation = xwoba - league_avg_xwoba
    # modifier 범위: 0.7 ~ 1.3 (alpha=0.3 보수적 시작)
    alpha = 0.3
    modifier = 1.0 + alpha * (deviation / league_avg_xwoba)
    return max(0.7, min(1.3, modifier))
```

**설계 결정**:
- `alpha = 0.3`: 보수적 시작 (물리 30%, 이벤트 70% 비중)
- modifier 범위 `[0.7, 1.3]`: K_base를 ±30%까지 조절
- Non-BIP 이벤트는 modifier = 1.0 (C2만 적용)
- xwoba=None 시 graceful degradation (modifier=1.0)

### 4.2 Phase 3 (향후): Raw EV+LA 기반

Phase 1 검증 완료 후, xwOBA 대신 raw 물리 데이터 직접 활용:

```python
def calculate_physics_modifier_v2(
    result_type: str,
    launch_speed: Optional[float],
    launch_angle: Optional[float],
) -> float:
    """
    EV+LA 직접 사용한 물리 modifier (Phase 3).

    Barrel Zone 정의 (MLB 공식):
    - Barrel: EV >= 98 mph, LA 26-30° (optimal)
    - Sweet Spot: EV >= 95 mph, LA 10-30°
    - Hard Hit: EV >= 95 mph (any angle)
    """
    NON_BIP_TYPES = {'StrikeOut', 'BB', 'IBB', 'HBP', 'SAC', 'E'}

    if result_type in NON_BIP_TYPES:
        return 1.0

    if launch_speed is None or launch_angle is None:
        return 1.0  # ~2% of BIP have null EV/LA

    # Continuous quality scoring
    ev = launch_speed
    la = launch_angle

    # Base modifier from exit velocity
    if ev >= 98:
        ev_score = 0.3   # barrel-range EV
    elif ev >= 95:
        ev_score = 0.15  # hard hit
    elif ev >= 85:
        ev_score = 0.0   # average
    else:
        ev_score = -0.15  # weak contact

    # Angle modifier (optimal: 10-30 degrees)
    if 10 <= la <= 30:
        la_score = 0.1   # optimal launch angle
    elif 0 <= la <= 10 or 30 < la <= 45:
        la_score = 0.0   # acceptable
    else:
        la_score = -0.1  # poor angle (popup or grounder)

    modifier = 1.0 + ev_score + la_score
    return max(0.7, min(1.4, modifier))
```

### 4.3 K-Effective 예시

Phase 1 (xwOBA 기반) 시나리오:

| PA 상황 | result_type | K_base | xwOBA | modifier | K_effective |
|---------|-------------|--------|-------|----------|-------------|
| 배럴 홈런 | HR | 15.0 | 1.95 | 1.30 | 19.5 |
| 일반 홈런 | HR | 15.0 | 1.40 | 1.23 | 18.5 |
| 라인드라이브 2루타 | Double | 12.0 | 1.20 | 1.18 | 14.2 |
| 텍사스 안타 | Single | 10.0 | 0.15 | 0.84 | 8.4 |
| 105mph 라인아웃 | OUT | 10.0 | 1.80 | 1.30 | 13.0 |
| 약한 플라이아웃 | OUT | 10.0 | 0.05 | 0.70 | 7.0 |
| 삼진 | StrikeOut | 6.0 | - | 1.0 | 6.0 |
| 볼넷 | BB | 6.0 | - | 1.0 | 6.0 |
| 몸에 맞는 공 | HBP | 3.0 | - | 1.0 | 3.0 |

**핵심 효과**: 105mph 라인아웃(K=13.0)은 약한 플라이아웃(K=7.0)보다 ELO 변동이 크다.
→ Statcast 물리 품질이 결과와 무관하게 신호 강도를 조절.

---

## 5. 코드 변경 사항

### 5.1 `elo_config.py` — 이벤트 K-Factor 테이블 추가

```python
# Event K-factor table (Layer 1: C2)
EVENT_K_FACTORS: dict[str, float] = {
    'HR': 15.0,
    'Triple': 14.0,
    'Double': 12.0,
    'Single': 10.0,
    'OUT': 10.0,
    'GIDP': 10.0,
    'FC': 10.0,
    'StrikeOut': 6.0,
    'BB': 6.0,
    'IBB': 3.0,
    'HBP': 3.0,
    'SAC': 3.0,
    'E': 0.0,
}

# Physics modifier config (Layer 2: A1)
PHYSICS_ALPHA = 0.3             # physics layer weight (conservative start)
PHYSICS_MOD_MIN = 0.7           # minimum K modifier
PHYSICS_MOD_MAX = 1.3           # maximum K modifier
LEAGUE_AVG_XWOBA = 0.315       # 2025 season average
```

### 5.2 `elo_calculator.py` — K-Modulation 통합

변경 범위: `process_plate_appearance()` 메서드에 `xwoba` 파라미터 추가, K 계산 로직 교체.

```python
def process_plate_appearance(
    self,
    batter: PlayerEloState,
    pitcher: PlayerEloState,
    delta_run_exp: Optional[float],
    state: int = 0,
    home_team: Optional[str] = None,
    result_type: Optional[str] = None,
    xwoba: Optional[float] = None,          # NEW: Phase 1
    launch_speed: Optional[float] = None,   # FUTURE: Phase 3
    launch_angle: Optional[float] = None,   # FUTURE: Phase 3
) -> EloUpdateResult:
```

K 계산 변경:

```python
# 기존 V5.3:
# batter_delta = self.k_factor * rv_diff

# 신규 K-Modulation:
k_base = EVENT_K_FACTORS.get(result_type, self.k_factor)
physics_mod = calculate_physics_modifier(result_type, xwoba)
k_effective = k_base * physics_mod
batter_delta = k_effective * rv_diff
pitcher_delta = -batter_delta  # zero-sum 유지
```

### 5.3 `elo_batch.py` — xwoba 컬럼 전달

```python
# process() 내부 변경:
xwoba_val = row.get('xwoba')
if pd.isna(xwoba_val):
    xwoba_val = None

result = self.calc.process_plate_appearance(
    batter, pitcher, rv,
    state=state,
    home_team=home_team,
    result_type=result_type,
    xwoba=xwoba_val,  # NEW
)
```

### 5.4 PA Detail 확장

`pa_details`에 K-modulation 정보 추가:

```python
self.pa_details.append({
    # 기존 필드...
    'k_base': k_base,          # NEW
    'physics_mod': physics_mod, # NEW
    'k_effective': k_effective, # NEW
})
```

---

## 6. DB 스키마 변경

### 6.1 `elo_pa_detail` 테이블 확장

```sql
-- scripts/migrations/003_k_modulation.sql
ALTER TABLE elo_pa_detail ADD COLUMN IF NOT EXISTS k_base REAL;
ALTER TABLE elo_pa_detail ADD COLUMN IF NOT EXISTS physics_mod REAL;
ALTER TABLE elo_pa_detail ADD COLUMN IF NOT EXISTS k_effective REAL;
```

### 6.2 기존 테이블 변경 없음

- `player_elo`: 변경 없음 (batting_elo, pitching_elo 유지)
- `daily_ohlc`: 변경 없음 (role별 OHLC 유지)
- `plate_appearances`: 변경 없음 (xwoba 이미 존재)

---

## 7. 단계별 구현 계획

### Phase 1: xwOBA 기반 K-Modulation

**목표**: Statcast xwOBA(99% 커버리지)를 활용한 physics modifier 도입.

| 항목 | 내용 |
|------|------|
| 파일 | `elo_config.py`, `elo_calculator.py`, `elo_batch.py` |
| 테스트 | `test_k_modulation.py` |
| 마이그레이션 | `003_k_modulation.sql` |
| 검증 | pytest + 전체 시즌 재계산 비교 |

**구현 태스크**:

1. `elo_config.py`에 `EVENT_K_FACTORS`, physics modifier 상수 추가
2. `elo_calculator.py`에 `calculate_physics_modifier()` 함수 추가
3. `EloCalculator.process_plate_appearance()`에 `xwoba` 파라미터 + K-modulation 로직
4. `EloBatch.process()`에서 xwoba 컬럼 전달
5. PA detail에 k_base/physics_mod/k_effective 추가
6. 단위 테스트 (TDD)
7. 전체 시즌 재계산 + V5.3 대비 비교

### Phase 2: 이벤트별 가변 K-Factor (C2 Layer 정교화)

**목표**: K_base 테이블 미세 조정 + 리그 분포 검증.

| 항목 | 내용 |
|------|------|
| 검증 지표 | 이벤트별 ELO 분산, K_effective 리그 분포 |
| 조정 대상 | alpha 값, K_base 개별 값, modifier 범위 |

**태스크**:

1. 2025 시즌 재계산 후 이벤트별 K_effective 분포 분석
2. ELO 분산 vs V5.3 비교 (너무 크면 alpha 축소)
3. 결과 기반 K_base 값 미세 조정
4. year-over-year 예측력 검증 (가능한 경우)

### Phase 3: Raw EV+LA Physics Layer (향후)

**목표**: xwOBA 대신 raw 물리 데이터로 physics modifier 직접 계산.

| 항목 | 내용 |
|------|------|
| 전제조건 | Phase 1 검증 완료, xwOBA 기반 ELO가 V5.3 대비 개선 확인 |
| 추가 데이터 | launch_speed, launch_angle (68% BIP), bat_speed (2024+ 시즌) |

**태스크**:

1. `calculate_physics_modifier_v2()` 구현 (EV+LA 연속 함수)
2. Phase 1 (xwOBA) vs Phase 3 (raw EV+LA) A/B 비교
3. 68% 커버리지 영향 분석
4. bat_speed 등 추가 피처 통합 검토

---

## 8. 테스트 전략

### 8.1 단위 테스트 (Phase 1)

```python
# test_k_modulation.py

class TestEventKFactor:
    def test_hr_gets_highest_k(self):
        """HR은 K=15.0"""
    def test_strikeout_gets_low_k(self):
        """StrikeOut은 K=6.0"""
    def test_error_gets_zero_k(self):
        """E는 K=0.0 (기존 로직 호환)"""
    def test_unknown_event_falls_back(self):
        """미등록 이벤트는 기본 K=12.0"""

class TestPhysicsModifier:
    def test_non_bip_returns_1(self):
        """StrikeOut, BB 등은 modifier=1.0"""
    def test_high_xwoba_increases_modifier(self):
        """xwoba=1.5 → modifier > 1.0"""
    def test_low_xwoba_decreases_modifier(self):
        """xwoba=0.05 → modifier < 1.0"""
    def test_none_xwoba_returns_1(self):
        """xwoba=None → modifier=1.0"""
    def test_modifier_clamped(self):
        """modifier는 [0.7, 1.3] 범위"""

class TestKModulationIntegration:
    def test_barrel_hr_gets_max_k(self):
        """배럴 HR: K=15 × 1.3 = 19.5"""
    def test_weak_out_gets_min_k(self):
        """약한 아웃: K=10 × 0.7 = 7.0"""
    def test_zero_sum_preserved(self):
        """K-modulation 후에도 batter_delta = -pitcher_delta"""
    def test_backward_compat_no_xwoba(self):
        """xwoba=None → V5.3과 동일 동작 (K=K_base)"""

class TestIncrementalConsistency:
    def test_full_vs_incremental_with_k_mod(self):
        """K-modulation 적용해도 전체/증분 처리 결과 동일"""
```

### 8.2 통합 검증

| 지표 | 목표 | 방법 |
|------|------|------|
| Zero-sum 보존 | 모든 PA에서 `batter_delta = -pitcher_delta` | 전체 시즌 재계산 후 검증 |
| ELO 분포 | 평균 ~1500, 합계 변동 < 0.01 | `player_elo` 통계 |
| K_effective 분포 | 평균 ~10, 범위 3~20 | PA detail 분석 |
| 기존 테스트 통과 | 100% | `pytest` 전체 실행 |

### 8.3 A/B 비교 (V5.3 vs K-Modulation)

```
# 전체 시즌 재계산 두 번
python scripts/run_elo.py --version v53       # 기존
python scripts/run_elo.py --version k_mod     # 신규

# 비교 항목
1. Top-50 타자 ELO: 두 버전 간 순위 상관 (Spearman r)
2. Top-50 투수 ELO: 두 버전 간 순위 상관
3. ELO 분산: V5.3 vs K-mod (과대/과소 평가 확인)
4. 물리 품질 반영: 105mph 라인아웃 vs 약한 안타 ELO 변동 차이
```

---

## 9. 프론트엔드 영향

### 9.1 변경 없음 (Phase 1)

Phase 1은 **백엔드 엔진 변경만**. 프론트엔드에 노출되는 데이터 구조는 동일:

- `player_elo`: 동일 (batting_elo, pitching_elo, composite_elo)
- `daily_ohlc`: 동일 (open, high, low, close, delta, role)
- `elo_pa_detail`: k_base, physics_mod, k_effective 컬럼 추가 (프론트엔드 미사용)

### 9.2 향후 가능한 확장

- PA Detail 페이지에 K-modulation 시각화 (K_effective 히트맵)
- 플레이어 프로필에 "Contact Quality" 지표 표시
- Barrel Rate / Hard Hit Rate 통계 카드

---

## 10. 리스크 & 완화

| 리스크 | 영향 | 완화 |
|--------|------|------|
| K_effective 과대 → ELO 변동성 증가 | 리더보드 불안정 | alpha=0.3 보수적 시작, 모니터링 후 조절 |
| xwOBA null (1%) | modifier 미적용 | fallback=1.0 (graceful degradation) |
| 이벤트 K-table 불균형 | 특정 선수 유형 편향 | 리그 평균 K_effective 모니터링 |
| 기존 테스트 호환 깨짐 | 리그레션 | xwoba=None 시 V5.3 동일 동작 보장 |
| 물리 modifier와 delta_run_exp 상관 | 이중 카운팅 | alpha 낮게 시작, 독립성 검증 |

---

## 11. 향후 로드맵

```
Phase 1 (현재)           Phase 2              Phase 3              Phase 4+
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ xwOBA K-mod  │   │ K-table 미세 │   │ Raw EV+LA    │   │ 다차원 탤런트│
│ EVENT_K_TABLE│──▶│ 조정 + 검증  │──▶│ Physics Mod  │──▶│ ELO + 매치업 │
│ alpha=0.3    │   │ alpha 최적화 │   │ bat_speed 등 │   │ 엔진 (9D)   │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
      ▲                                                          │
      │                                                          │
      └──── balltology-elo 아키텍처 참고 ────────────────────────┘
```

Phase 4+ 에서 balltology-elo의 9차원 탤런트 ELO와 3단계 매치업 엔진을
MLB Statcast 데이터에 최적화하여 구현. Phase 1-3에서 축적된 K-modulation 인프라 위에 구축.

---

## 부록 A: 수식 정리

### 현재 V5.3

```
adjusted_rv  = delta_run_exp - park_adjustment
rv_diff      = adjusted_rv - mean_rv[state]
batter_delta = K × rv_diff                    (K = 12.0 고정)
pitcher_delta = -batter_delta
```

### K-Modulation (Phase 1)

```
adjusted_rv  = delta_run_exp - park_adjustment
rv_diff      = adjusted_rv - mean_rv[state]

K_base       = EVENT_K_FACTORS[result_type]    (이벤트 유형별)
modifier     = physics_modifier(result_type, xwoba)
K_effective  = K_base × modifier

batter_delta = K_effective × rv_diff
pitcher_delta = -batter_delta
```

### Physics Modifier (Phase 1)

```
if result_type ∈ {StrikeOut, BB, IBB, HBP, SAC, E}:
    modifier = 1.0

else:  # BIP events
    if xwoba is None:
        modifier = 1.0
    else:
        deviation = xwoba - LEAGUE_AVG_XWOBA
        modifier = 1.0 + α × (deviation / LEAGUE_AVG_XWOBA)
        modifier = clamp(modifier, 0.7, 1.3)

where α = 0.3 (PHYSICS_ALPHA)
```

---

## 부록 B: balltology-elo 참고 문서

| 문서 | 핵심 내용 | 적용 |
|------|----------|------|
| `multi-dimensional-elo-design.md` | 9차원 설계, 이벤트-차원 가중치 | Phase 4+ 참고 |
| `matchup-engine-v2-expert-panel.md` | 3단계 매치업 엔진, DIPS 비대칭 | Phase 4+ 참고 |
| `talent-elo-schema-design.md` | talent_pa_detail 스키마 | Phase 4+ 참고 |
| `multi_elo_config.yaml` | 이벤트-차원 가중치 매트릭스 | Phase 4+ 참고 |

---

*이 설계의 토의 과정: [2026-01-30-multi-elo-expert-panel-discussion.md](2026-01-30-multi-elo-expert-panel-discussion.md)*
*기존 시스템 설계: [2026-01-29-mlb-elo-system-design.md](2026-01-29-mlb-elo-system-design.md)*
