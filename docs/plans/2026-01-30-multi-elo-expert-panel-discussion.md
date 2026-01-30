# Multi-Dimensional ELO: Expert Panel Discussion

> 5인 전문가 패널을 통한 BIP Quality 차원 설계 토의 기록

**날짜**: 2026-01-30
**목적**: MLB Statcast 데이터를 활용한 다차원 ELO 시스템의 BIP(Batted Ball In Play) 품질 차원 설계 방향 결정
**방법**: 5인 전문가 패널 → 각 2개 제안 (총 10개) → 교차 평가 → Statcast 특화 재평가

---

## 1. 배경

### 1.1 현재 시스템 (V5.3)

- 2차원 ELO: `batting_elo` + `pitching_elo` (Phase 6 완료)
- K=12, zero-sum: `pitcher_delta = -batter_delta`
- 입력: `delta_run_exp` (100% coverage)
- 183,092 PA / 2025 시즌

### 1.2 KBO 시스템 (balltology-elo) 참고

- 9차원 탤런트 ELO (Batter 5D + Pitcher 4D)
- 3단계 매치업 엔진 (BB/K/BIP softmax → Hit|BIP logistic → hit type distribution)
- DIPS 기반 비대칭 가중치
- **핵심 한계**: 물리 측정 데이터 없음 → BIP Suppression K=4.0으로 축소

### 1.3 MLB Statcast 데이터 우위

| 필드 | 커버리지 | 설명 |
|------|---------|------|
| `launch_speed` | 68% (BIP only) | 타구 속도 (mph) |
| `launch_angle` | 68% (BIP only) | 타구 각도 (degrees) |
| `xwoba` | 99% | MLB 모델 기반 기대 wOBA |
| `release_speed` | 99.6% | 투구 속도 |
| `release_spin_rate` | 99.4% | 투구 회전수 |
| `delta_run_exp` | 100% | 득점 기대치 변화 |

KBO에서 불가능했던 **타구 물리 데이터(EV+LA)** 직접 활용이 핵심 차별점.

---

## 2. 전문가 패널 구성

| ID | 전문가 | 전문 분야 |
|----|--------|----------|
| A | 세이버메트릭스 전문가 | Run expectancy, wOBA, 타격 지표 |
| B | 게임이론 전문가 | 경쟁 레이팅 시스템, 정보 비대칭 |
| C | ELO 전문가 | Elo/Glicko-2, K-factor 최적화, 수렴 |
| D | 구단 데이터 분석가 | Statcast 실무 10년, 선수 평가 |
| E | 알고리즘 엔지니어 | ML 시스템, 수치 안정성, 구현 |

---

## 3. 1차 제안 (10개)

### Expert A: 세이버메트릭스

**A1: BBQ (Batted Ball Quality)**
- EV+LA 자체 채점, BIP only
- 연속 함수: `quality = f(EV, LA)` → xwOBA 스케일 매핑
- K=10, 대칭 zero-sum

**A2: xCV (Expected Contact Value)**
- xwOBA 블렌딩 (65% xwOBA + 35% outcome)
- 모든 PA 포함
- K=11

### Expert B: 게임이론

**B1: BIP Quality**
- EV+LA 기반, 비대칭 zero-sum (65/35)
- BIP only
- K=10

**B2: xwOBA Skill**
- 직교 잔차 (orthogonalized residual) 기반
- 대칭 zero-sum
- K=6

### Expert C: ELO 전문가

**C1: BIP Quality + Glicko-2 RD**
- EV+LA + 불확실성(RD) 추적
- BIP only with uncertainty decay
- K=8

**C2: Contact Impact**
- 모든 PA 유형 포함
- 이벤트별 가변 K: K_strikeout=6, K_walk=6, K_single=8, K_homer=15
- EV/LA 직접 미사용 → 이벤트 결과 기반

### Expert D: 구단 분석가

**D1: BBT (Batted Ball Threat)**
- EV+LA zone 기반: Barrel Zone (EV≥98, LA 26-30°) = +1.0, Sweet Spot = +0.5
- BIP only (68%)
- K~10, 투수는 역방향 (BIP suppression quality)

**D2: xDMG (Expected Damage)**
- xwOBA 기반
- K~10

### Expert E: 알고리즘 엔지니어

**E1: contact_quality**
- xwOBA 직접 사용
- K=12-15

**E2: contact_power**
- EV+LA + K imputation (삼진에 대해 EV 추정)
- K~10

---

## 4. 1차 교차 평가

### 4.1 평가 기준

| 기준 | 설명 |
|------|------|
| 통계 타당성 | 세이버메트릭스 이론 부합 |
| 시스템 안정성 | ELO 수렴, K-factor 안정성 |
| 구현 가능성 | 코드 복잡도, 테스트 용이성 |
| 예측 정확도 | 미래 성과 예측력 |
| 확장성 | 매치업 엔진 확장 가능성 |

### 4.2 종합 점수 (5인 × 5기준 × 10점 = 250점 만점)

| 순위 | 제안 | 총점 | 특징 |
|------|------|------|------|
| 1 | **D1: BBT** | **177** | 구단 분석가 1위 선정 |
| 2 | **A1: BBQ** | **175** | 세이버메트릭스 1위 |
| 3 | **C2: Contact Impact** | **170** | ELO/엔지니어 1위 |
| 4 | B1: BIP Quality | 163 | |
| 5 | E2: contact_power | 160 | |
| 6 | A2: xCV | 157 | |
| 7 | C1: BIP+Glicko-2 | 153 | |
| 8 | D2: xDMG | 148 | |
| 9 | E1: contact_quality | 145 | |
| 10 | B2: xwOBA Skill | 140 | |

### 4.3 두 진영 발견

**물리 측정 진영** (A1, B1, D1, E2):
- EV+LA 직접 활용, BIP only (68% coverage)
- 야구 도메인 전문가들 선호
- 강점: BABIP 노이즈 제거, 물리 기반 신호
- 약점: 32% PA 누락 (삼진, 볼넷)

**이벤트 가중 진영** (C2):
- 모든 PA 포함, 결과 기반 가변 K
- 시스템 엔지니어 선호
- 강점: 100% 커버리지, 구현 단순
- 약점: Statcast 고유 데이터 미활용

---

## 5. Statcast 특화 재평가 (2차)

### 5.1 평가 대상

1차 결과에서 상위 4개 제안 + 하이브리드 옵션:

- **D1: BBT** (zone-based EV+LA, BIP only)
- **A1: BBQ** (continuous f(EV,LA), BIP only)
- **C2: Contact Impact** (event-based, all PA)
- **Hybrid D1+C2** (D1 물리 레이어 + C2 이벤트 레이어)

### 5.2 재평가 기준 (Statcast 활용 특화)

| 기준 | 설명 |
|------|------|
| Statcast Data Utilization | 물리 측정 데이터(EV, LA, spin, velocity) 활용 정도 |
| Signal Quality Improvement | KBO 대비 SNR 개선 폭 |
| Coverage Robustness | 68% EV/LA 커버리지 갭 처리 |
| Information Efficiency | PA당 추가 예측 정보량 |
| Future Extensibility | bat_speed, spray_angle 등 향후 확장성 |

### 5.3 재평가 결과

#### 전문가별 총점 (각 50점 만점)

| 전문가 | D1: BBT | A1: BBQ | C2: Contact | Hybrid D1+C2 |
|--------|---------|---------|-------------|---------------|
| A. 세이버메트릭스 | 36 | 37 | 23 | 38 |
| B. 게임이론 | 30 | **37** | 24 | 32 |
| C. ELO 전문가 | 32 | 35 | 33 | **42** |
| D. 구단 분석가 | 32 | 27 | 26 | **43** |
| E. 알고리즘 엔지니어 | 29 | 35 | 24 | **39** |
| **합계** | **159** | **171** | **130** | **194** |

#### 기준별 상세 점수 (5인 합산)

| 기준 | D1 | A1 | C2 | Hybrid |
|------|-----|-----|-----|--------|
| Statcast Utilization | 41 | 43 | 15 | 44 |
| Signal Quality | 33 | 39 | 26 | 38 |
| Coverage Robustness | 19 | 18 | **48** | 41 |
| Information Efficiency | 30 | 34 | 22 | 37 |
| Future Extensibility | 36 | 37 | 19 | 34* |

*Note: Extensibility에서 A1이 Hybrid보다 높은 것은 A1의 연속 함수가 새 변수 추가에 더 자연스럽기 때문.

### 5.4 최종 순위

| 순위 | 제안 | 총점 (/250) | 1위 선정 수 |
|------|------|-------------|-----------|
| **1위** | **Hybrid D1+C2** | **194** | 3명 (ELO, 구단, 엔지니어) |
| **2위** | **A1: BBQ** | **171** | 2명 (세이버, 게임이론) |
| **3위** | **D1: BBT** | **159** | 0명 |
| **4위** | **C2: Contact Impact** | **130** | 0명 |

---

## 6. 전문가 핵심 의견

### 6.1 전원 합의

- C2 단독은 Statcast 데이터 장점을 살리지 못함 (최하위)
- EV/LA 물리 데이터 직접 활용이 MLB Statcast의 핵심 가치
- 68% 커버리지 갭은 반드시 아키텍처적으로 해결 필요

### 6.2 세이버메트릭스 전문가 (Expert A)

> "A1의 연속 함수가 D1 zone 이산화보다 정보 효율이 높다. 최적 구조는 **A1을 BIP 레이어로, C2를 이벤트 레이어로** 결합하는 Hybrid A1+C2이다."

핵심 제안: BIP에서 `alpha * A1_delta + (1-alpha) * C2_delta` (alpha=0.6-0.7)

### 6.3 게임이론 전문가 (Expert B)

> "A1(BBQ)이 BIP 차원으로 최적이나 standalone 불가. **BBQ는 dimension이지 standalone system이 아니다.** 기존 delta_run_exp 파이프라인이 100% 커버리지를 제공하고, BBQ는 보조 차원으로 운용."

핵심 제안: 기존 ELO(100% 커버리지) + BBQ 보조 차원(68% BIP) 이중 구조

### 6.4 ELO 전문가 (Expert C)

> "Hybrid가 ELO 이론적으로 가장 정당하다. 결합 방식은 **K-modulation**을 추천: `K_effective = K_event(result_type) × physics_modifier(EV, LA)`. Zero-sum 자동 유지, 기존 엔진 확장점과 호환."

핵심 제안:

| 결과 | K_base | Physics modifier | K_effective 범위 |
|------|--------|-----------------|-----------------|
| HR | 15 | 1.0-1.2 | 15.0-18.0 |
| BIP hits | 12 | 0.7-1.3 | 8.4-15.6 |
| BIP outs | 10 | 0.8-1.2 | 8.0-12.0 |
| K | 6 | 1.0 (무적용) | 6.0 |
| BB/HBP | 6 | 1.0 (무적용) | 6.0 |

### 6.5 구단 분석가 (Expert D)

> "품질과 커버리지 모두 잡는 Hybrid가 정답. 단, **초기 alpha=0.3 (30% 물리, 70% 이벤트)**으로 보수적 시작 후, 물리 레이어가 예측력 향상을 증명하면 비중 확대."

핵심 제안: 검증 지표
- Hybrid ELO vs next-year wOBA: r > 0.55
- BIP physics layer vs barrel rate: r > 0.80
- Event layer K/BB vs K%-BB%: r > 0.75

### 6.6 알고리즘 엔지니어 (Expert E)

> "**xwOBA가 이미 99% 커버리지로 테이블에 있다.** xwOBA는 MLB가 EV+LA를 모델링한 결과물. 이걸 직접 쓰면 68% 커버리지 문제가 해소. Phase 1에서 xwOBA 기반 ELO를 먼저 구축하고, 검증 후 raw EV/LA 레이어 추가."

핵심 제안: 3단계 구현
1. **Phase 1**: xwOBA 기반 ELO (99% 커버리지, ~20줄 변경)
2. **Phase 2**: 이벤트별 가변 K-factor 추가
3. **Phase 3**: raw EV/LA 물리 레이어 (검증 후)

---

## 7. 수렴된 결론

### 최종 방향: Hybrid A1+C2 (xwOBA 활용형)

5인 전문가 의견이 수렴한 최적 아키텍처:

```
┌─────────────────────────────────────────┐
│         Hybrid A1+C2 Architecture       │
├─────────────────────────────────────────┤
│                                         │
│  모든 PA:                               │
│  ┌─────────────────────────────┐        │
│  │ C2 Event Layer              │        │
│  │ K_effective = K_event_table │        │
│  │ (K_HR=15, K_K=6, K_BB=6)   │        │
│  └─────────────────────────────┘        │
│            ×                            │
│  BIP PA (68%):                          │
│  ┌─────────────────────────────┐        │
│  │ A1 Physics Layer            │        │
│  │ physics_mod = f(EV, LA)     │        │
│  │ or xwOBA-based modifier     │        │
│  └─────────────────────────────┘        │
│            =                            │
│  K_final = K_event × physics_mod        │
│  delta = K_final × rv_diff              │
│  pitcher_delta = -delta (zero-sum)      │
│                                         │
└─────────────────────────────────────────┘
```

### 핵심 설계 결정

1. **K-modulation 결합**: 물리 레이어가 K-factor를 조절 (additive가 아닌 multiplicative)
2. **xwOBA 우선 활용**: 99% 커버리지의 xwOBA를 먼저 활용, raw EV/LA는 Phase 3
3. **보수적 시작**: 물리 가중치 30%에서 시작, 검증 후 확대
4. **zero-sum 유지**: `pitcher_delta = -batter_delta` 구조 불변

---

*이 문서의 설계 결정은 [2026-01-30-multi-dimensional-elo-design.md](2026-01-30-multi-dimensional-elo-design.md)에서 구체화됨.*
