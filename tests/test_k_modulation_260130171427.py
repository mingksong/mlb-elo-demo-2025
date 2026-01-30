"""Tests for K-Modulation (Hybrid A1+C2).

Phase 1: xwOBA-based K-Modulation.
- Layer 1 (C2): Event-type K-factor table
- Layer 2 (A1): xwOBA physics modifier
- Combined: K_effective = K_base × physics_modifier

Test classes:
- TestEventKFactor: EVENT_K_FACTORS 테이블 검증
- TestPhysicsModifier: calculate_physics_modifier() 검증
- TestKModulationIntegration: EloCalculator 통합 검증
- TestKModulationBatch: EloBatch에서 xwoba 전달 + pa_details 확장 검증
- TestIncrementalConsistency: 전체/증분 처리 결과 동일 검증
"""

import pandas as pd
import pytest

from src.engine.elo_config import (
    EVENT_K_FACTORS,
    INITIAL_ELO,
    K_FACTOR,
    LEAGUE_AVG_XWOBA,
    NON_BIP_TYPES,
    PHYSICS_ALPHA,
    PHYSICS_MOD_MAX,
    PHYSICS_MOD_MIN,
)
from src.engine.elo_calculator import (
    EloCalculator,
    EloUpdateResult,
    PlayerEloState,
    calculate_physics_modifier,
)
from src.engine.elo_batch import EloBatch


# ─── Layer 1: Event K-Factor Table ───


class TestEventKFactor:
    def test_hr_gets_highest_k(self):
        """HR은 K=15.0 (방어/운 무관, 최고 신뢰도)."""
        assert EVENT_K_FACTORS['HR'] == 15.0

    def test_triple_gets_high_k(self):
        """Triple은 K=14.0."""
        assert EVENT_K_FACTORS['Triple'] == 14.0

    def test_double_gets_standard_k(self):
        """Double은 K=12.0."""
        assert EVENT_K_FACTORS['Double'] == 12.0

    def test_single_gets_moderate_k(self):
        """Single은 K=10.0 (BABIP 노이즈 포함)."""
        assert EVENT_K_FACTORS['Single'] == 10.0

    def test_out_gets_moderate_k(self):
        """OUT은 K=10.0."""
        assert EVENT_K_FACTORS['OUT'] == 10.0

    def test_strikeout_gets_low_k(self):
        """StrikeOut은 K=6.0 (확실하지만 낮은 delta)."""
        assert EVENT_K_FACTORS['StrikeOut'] == 6.0

    def test_bb_gets_low_k(self):
        """BB는 K=6.0."""
        assert EVENT_K_FACTORS['BB'] == 6.0

    def test_ibb_gets_minimal_k(self):
        """IBB는 K=3.0 (전략적 선택)."""
        assert EVENT_K_FACTORS['IBB'] == 3.0

    def test_hbp_gets_minimal_k(self):
        """HBP는 K=3.0 (우연적)."""
        assert EVENT_K_FACTORS['HBP'] == 3.0

    def test_sac_gets_minimal_k(self):
        """SAC는 K=3.0."""
        assert EVENT_K_FACTORS['SAC'] == 3.0

    def test_error_gets_zero_k(self):
        """E는 K=0.0 (수비 에러, 실력 무관)."""
        assert EVENT_K_FACTORS['E'] == 0.0

    def test_all_result_types_covered(self):
        """모든 result_type이 EVENT_K_FACTORS에 등록."""
        expected_types = {
            'HR', 'Triple', 'Double', 'Single',
            'OUT', 'GIDP', 'FC',
            'StrikeOut', 'BB', 'IBB', 'HBP', 'SAC', 'E',
        }
        assert set(EVENT_K_FACTORS.keys()) == expected_types

    def test_non_bip_types_defined(self):
        """NON_BIP_TYPES에 삼진, 볼넷 등 포함."""
        assert 'StrikeOut' in NON_BIP_TYPES
        assert 'BB' in NON_BIP_TYPES
        assert 'IBB' in NON_BIP_TYPES
        assert 'HBP' in NON_BIP_TYPES
        assert 'SAC' in NON_BIP_TYPES
        assert 'E' in NON_BIP_TYPES


# ─── Layer 2: Physics Modifier ───


class TestPhysicsModifier:
    def test_non_bip_strikeout_returns_1(self):
        """StrikeOut → modifier=1.0 (BIP 아님)."""
        assert calculate_physics_modifier('StrikeOut', 0.5) == 1.0

    def test_non_bip_bb_returns_1(self):
        """BB → modifier=1.0."""
        assert calculate_physics_modifier('BB', 0.5) == 1.0

    def test_non_bip_hbp_returns_1(self):
        """HBP → modifier=1.0."""
        assert calculate_physics_modifier('HBP', 0.5) == 1.0

    def test_non_bip_ibb_returns_1(self):
        """IBB → modifier=1.0."""
        assert calculate_physics_modifier('IBB', 0.5) == 1.0

    def test_non_bip_sac_returns_1(self):
        """SAC → modifier=1.0."""
        assert calculate_physics_modifier('SAC', 0.5) == 1.0

    def test_non_bip_error_returns_1(self):
        """E → modifier=1.0."""
        assert calculate_physics_modifier('E', 0.5) == 1.0

    def test_none_xwoba_returns_1(self):
        """xwoba=None → modifier=1.0 (graceful degradation)."""
        assert calculate_physics_modifier('Single', None) == 1.0

    def test_high_xwoba_increases_modifier(self):
        """xwoba=1.5 (barrel-like) → modifier > 1.0."""
        mod = calculate_physics_modifier('Single', 1.5)
        assert mod > 1.0

    def test_low_xwoba_decreases_modifier(self):
        """xwoba=0.05 (weak contact) → modifier < 1.0."""
        mod = calculate_physics_modifier('Single', 0.05)
        assert mod < 1.0

    def test_league_avg_xwoba_returns_near_1(self):
        """xwoba=리그 평균(0.315) → modifier≈1.0."""
        mod = calculate_physics_modifier('Single', LEAGUE_AVG_XWOBA)
        assert abs(mod - 1.0) < 0.01

    def test_modifier_clamped_high(self):
        """매우 높은 xwoba → modifier <= PHYSICS_MOD_MAX(1.3)."""
        mod = calculate_physics_modifier('HR', 2.5)  # extreme xwoba
        assert mod <= PHYSICS_MOD_MAX

    def test_modifier_clamped_low(self):
        """xwoba=0.0 → modifier >= PHYSICS_MOD_MIN(0.7)."""
        mod = calculate_physics_modifier('OUT', 0.0)
        assert mod >= PHYSICS_MOD_MIN

    def test_bip_hit_types_use_modifier(self):
        """Single, Double, Triple, HR은 BIP → modifier != 1.0 (xwoba≠avg)."""
        for rt in ['Single', 'Double', 'Triple', 'HR']:
            mod = calculate_physics_modifier(rt, 1.0)  # above avg
            assert mod > 1.0, f"{rt} should get modifier > 1.0"

    def test_bip_out_types_use_modifier(self):
        """OUT, GIDP, FC도 BIP → modifier 적용."""
        for rt in ['OUT', 'GIDP', 'FC']:
            mod = calculate_physics_modifier(rt, 0.05)  # below avg
            assert mod < 1.0, f"{rt} should get modifier < 1.0"


# ─── Integration: EloCalculator with K-Modulation ───


class TestKModulationIntegration:
    def setup_method(self):
        self.calc = EloCalculator()
        self.batter = PlayerEloState(player_id=100)
        self.pitcher = PlayerEloState(player_id=200)

    def test_barrel_hr_gets_high_k_effective(self):
        """배럴 HR (xwoba=1.95): K_effective = 15 × 1.3 = 19.5."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=1.4,
            result_type='HR',
            xwoba=1.95,
        )
        # K_effective should be ~19.5, delta = 19.5 * 1.4 = 27.3
        assert abs(result.batter_delta) > abs(K_FACTOR * 1.4)  # bigger than flat K=12

    def test_weak_out_gets_low_k_effective(self):
        """약한 플라이아웃 (xwoba=0.05): K_effective = 10 × 0.7 = 7.0."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=-0.2,
            result_type='OUT',
            xwoba=0.05,
        )
        # K_effective should be ~7.0, delta = 7.0 * (-0.2) = -1.4
        assert abs(result.batter_delta) < abs(K_FACTOR * (-0.2))  # smaller than flat K=12

    def test_zero_sum_preserved(self):
        """K-modulation 후에도 batter_delta = -pitcher_delta."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=0.8,
            result_type='Double',
            xwoba=1.2,
        )
        assert abs(result.batter_delta + result.pitcher_delta) < 1e-10

    def test_zero_sum_preserved_all_event_types(self):
        """모든 이벤트 유형에서 zero-sum 유지."""
        for rt in EVENT_K_FACTORS:
            batter = PlayerEloState(player_id=100)
            pitcher = PlayerEloState(player_id=200)
            result = self.calc.process_plate_appearance(
                batter, pitcher,
                delta_run_exp=0.5,
                result_type=rt,
                xwoba=0.8,
            )
            assert abs(result.batter_delta + result.pitcher_delta) < 1e-10, \
                f"Zero-sum violated for {rt}"

    def test_backward_compat_no_xwoba(self):
        """xwoba=None → modifier=1.0, K_base만 적용."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=0.5,
            result_type='Single',
            xwoba=None,
        )
        # K_base for Single = 10.0, modifier = 1.0
        # delta = 10.0 * 0.5 = 5.0
        expected_delta = EVENT_K_FACTORS['Single'] * 0.5
        assert abs(result.batter_delta - expected_delta) < 1e-10

    def test_backward_compat_no_result_type(self):
        """result_type=None → 기본 K_FACTOR(12.0) 사용."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=0.5,
            result_type=None,
        )
        expected_delta = K_FACTOR * 0.5
        assert abs(result.batter_delta - expected_delta) < 1e-10

    def test_error_event_zero_positive_delta(self):
        """E(에러) → 기존 로직: 타자 유리 delta 차단."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=1.0,
            result_type='E',
            xwoba=0.5,
        )
        # E has K_base=0.0, so delta should be 0
        assert result.batter_delta == 0.0
        assert result.pitcher_delta == 0.0

    def test_strikeout_uses_only_event_k(self):
        """StrikeOut → K_base=6.0, modifier=1.0 (non-BIP)."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=-0.3,
            result_type='StrikeOut',
            xwoba=None,
        )
        expected_delta = 6.0 * (-0.3)
        assert abs(result.batter_delta - expected_delta) < 1e-10

    def test_elo_update_result_has_k_fields(self):
        """EloUpdateResult에 k_base, physics_mod, k_effective 포함."""
        result = self.calc.process_plate_appearance(
            self.batter, self.pitcher,
            delta_run_exp=0.5,
            result_type='HR',
            xwoba=1.5,
        )
        assert hasattr(result, 'k_base')
        assert hasattr(result, 'physics_mod')
        assert hasattr(result, 'k_effective')
        assert result.k_base == 15.0
        assert result.physics_mod > 1.0
        assert abs(result.k_effective - result.k_base * result.physics_mod) < 1e-10


# ─── Batch: xwoba pass-through + pa_details ───


def _make_pa_df(rows: list[dict]) -> pd.DataFrame:
    """테스트용 PA DataFrame 생성 (xwoba 포함)."""
    defaults = {
        'game_pk': 1000,
        'game_date': '2026-04-15',
        'result_type': 'Single',
        'delta_run_exp': 0.5,
        'on_1b': False,
        'on_2b': False,
        'on_3b': False,
        'outs_when_up': 0,
        'home_team': 'NYY',
        'xwoba': 0.5,
    }
    data = []
    for i, row in enumerate(rows):
        r = {**defaults, **row}
        r.setdefault('pa_id', (i + 1) * 1000 + 1)
        r.setdefault('batter_id', r.get('batter_id', 100))
        r.setdefault('pitcher_id', r.get('pitcher_id', 200))
        r.setdefault('at_bat_number', i + 1)
        data.append(r)
    return pd.DataFrame(data)


class TestKModulationBatch:
    def test_pa_details_include_k_fields(self):
        """EloBatch pa_details에 k_base, physics_mod, k_effective 포함."""
        batch = EloBatch()
        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 200,
             'result_type': 'HR', 'delta_run_exp': 1.4, 'xwoba': 1.95},
        ])
        batch.process(pa_df)

        detail = batch.pa_details[0]
        assert 'k_base' in detail
        assert 'physics_mod' in detail
        assert 'k_effective' in detail
        assert detail['k_base'] == 15.0
        assert detail['physics_mod'] > 1.0

    def test_batch_xwoba_nan_handled(self):
        """xwoba=NaN → modifier=1.0 (graceful degradation)."""
        batch = EloBatch()
        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 200,
             'result_type': 'OUT', 'delta_run_exp': -0.2, 'xwoba': float('nan')},
        ])
        batch.process(pa_df)

        detail = batch.pa_details[0]
        assert detail['physics_mod'] == 1.0

    def test_batch_missing_xwoba_column(self):
        """xwoba 컬럼이 없는 DataFrame에서도 동작 (하위 호환)."""
        batch = EloBatch()
        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 200,
             'result_type': 'Single', 'delta_run_exp': 0.3},
        ])
        # Remove xwoba column to simulate old data
        if 'xwoba' in pa_df.columns:
            pa_df = pa_df.drop(columns=['xwoba'])
        batch.process(pa_df)

        # Should still process without error
        assert len(batch.pa_details) == 1
        assert batch.pa_details[0]['physics_mod'] == 1.0


# ─── Incremental Consistency ───


class TestIncrementalConsistency:
    def test_full_vs_incremental_with_k_mod(self):
        """K-modulation 적용해도 전체/증분 처리 결과 동일."""
        day1_pa = _make_pa_df([
            {'pa_id': 1001, 'batter_id': 100, 'pitcher_id': 200,
             'game_date': '2026-04-15', 'result_type': 'Double',
             'delta_run_exp': 0.8, 'xwoba': 1.2},
            {'pa_id': 1002, 'batter_id': 101, 'pitcher_id': 200,
             'game_date': '2026-04-15', 'result_type': 'StrikeOut',
             'delta_run_exp': -0.3, 'xwoba': None},
        ])
        day2_pa = _make_pa_df([
            {'pa_id': 2001, 'batter_id': 100, 'pitcher_id': 201,
             'game_date': '2026-04-16', 'result_type': 'HR',
             'delta_run_exp': 1.4, 'xwoba': 1.95},
            {'pa_id': 2002, 'batter_id': 101, 'pitcher_id': 201,
             'game_date': '2026-04-16', 'result_type': 'OUT',
             'delta_run_exp': -0.1, 'xwoba': 0.1},
        ])

        # Full season
        full_df = pd.concat([day1_pa, day2_pa], ignore_index=True)
        batch_full = EloBatch()
        batch_full.process(full_df)

        # Incremental
        batch_day1 = EloBatch()
        batch_day1.process(day1_pa)
        day1_states = {
            pid: PlayerEloState(
                player_id=pid,
                batting_elo=s.batting_elo,
                pitching_elo=s.pitching_elo,
                batting_pa=s.batting_pa,
                pitching_pa=s.pitching_pa,
                cumulative_rv=0.0,
            )
            for pid, s in batch_day1.players.items()
        }
        batch_day2 = EloBatch(initial_states=day1_states)
        batch_day2.process(day2_pa)

        # Compare final ELOs
        for pid in batch_full.players:
            full_bat = batch_full.players[pid].batting_elo
            full_pit = batch_full.players[pid].pitching_elo
            if pid in batch_day2.players:
                incr_bat = batch_day2.players[pid].batting_elo
                incr_pit = batch_day2.players[pid].pitching_elo
            else:
                incr_bat = batch_day1.players[pid].batting_elo
                incr_pit = batch_day1.players[pid].pitching_elo
            assert abs(full_bat - incr_bat) < 1e-10, \
                f"Player {pid}: full batting={full_bat}, incr={incr_bat}"
            assert abs(full_pit - incr_pit) < 1e-10, \
                f"Player {pid}: full pitching={full_pit}, incr={incr_pit}"
