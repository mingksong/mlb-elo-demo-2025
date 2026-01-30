"""V5.3 Engine Upgrade Tests — State Normalization + Park Factor."""

import os
import tempfile

import pandas as pd
import pytest

from src.engine.elo_config import INITIAL_ELO, K_FACTOR, ADJUSTMENT_SCALE, EVENT_K_FACTORS
from src.engine.elo_calculator import PlayerEloState, EloCalculator
from src.engine.elo_batch import EloBatch
from src.engine.re24_baseline import RE24Baseline
from src.engine.park_factor import ParkFactor


# === Helpers ===

def _make_baseline_csv(tmp_path):
    """테스트용 RE24 baseline CSV 생성."""
    data = {
        'state_id': [0, 1, 8, 16],
        'state_name': ['Empty 0Out', '1B 0Out', 'Empty 1Out', 'Empty 2Out'],
        'sample_count': [1000, 500, 800, 600],
        'mean_rv': [-0.002, 0.007, 0.001, 0.006],
        'std_rv': [0.38, 0.39, 0.42, 0.53],
        'median_rv': [-0.19, -0.17, -0.18, -0.18],
    }
    path = os.path.join(tmp_path, 'baseline.csv')
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def _make_park_csv(tmp_path):
    """테스트용 Park Factor CSV 생성."""
    data = {
        'home_team': ['COL', 'SEA', 'NYY'],
        'venue': ['Coors Field', 'T-Mobile Park', 'Yankee Stadium'],
        'park_factor': [1.13, 0.91, 1.00],
    }
    path = os.path.join(tmp_path, 'park.csv')
    pd.DataFrame(data).to_csv(path, index=False)
    return path


def _make_pa_df(rows):
    """테스트용 PA DataFrame 생성."""
    return pd.DataFrame(rows).sort_values(['game_date', 'pa_id']).reset_index(drop=True)


# === Config Tests ===

def test_adjustment_scale_config():
    """ADJUSTMENT_SCALE 설정 확인."""
    assert ADJUSTMENT_SCALE == 0.1


# === RE24 Baseline Tests ===

def test_re24_baseline_load():
    """RE24 baseline CSV 로드."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_baseline_csv(tmp)
        baseline = RE24Baseline(csv_path=path)
        assert baseline.get_expected_rv(0) == pytest.approx(-0.002)
        assert baseline.get_expected_rv(1) == pytest.approx(0.007)


def test_re24_baseline_missing_state():
    """없는 state → 0.0 반환."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_baseline_csv(tmp)
        baseline = RE24Baseline(csv_path=path)
        assert baseline.get_expected_rv(99) == 0.0


def test_re24_baseline_default_path():
    """기본 경로에서 실제 CSV 로드 (data/mlb_re24_baseline.csv 존재 시)."""
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'mlb_re24_baseline.csv')
    if os.path.exists(csv_path):
        baseline = RE24Baseline()
        # 24 states should all be present
        for state_id in range(24):
            rv = baseline.get_expected_rv(state_id)
            assert isinstance(rv, float)


# === Park Factor Tests ===

def test_park_factor_load():
    """Park factor CSV 로드."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_park_csv(tmp)
        pf = ParkFactor(csv_path=path)
        assert pf.get_park_factor('COL') == pytest.approx(1.13)
        assert pf.get_park_factor('SEA') == pytest.approx(0.91)


def test_park_factor_missing_team():
    """없는 팀 → PF 1.0 (neutral)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_park_csv(tmp)
        pf = ParkFactor(csv_path=path)
        assert pf.get_park_factor('UNKNOWN') == 1.0


def test_park_factor_adjustment_col():
    """COL adjustment = (1.13 - 1.0) × 0.1 = 0.013."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_park_csv(tmp)
        pf = ParkFactor(csv_path=path)
        assert pf.get_adjustment('COL') == pytest.approx(0.013)


def test_park_factor_adjustment_sea():
    """SEA adjustment = (0.91 - 1.0) × 0.1 = -0.009."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_park_csv(tmp)
        pf = ParkFactor(csv_path=path)
        assert pf.get_adjustment('SEA') == pytest.approx(-0.009)


def test_park_factor_adjustment_neutral():
    """NYY (PF=1.00) → adjustment = 0.0."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_park_csv(tmp)
        pf = ParkFactor(csv_path=path)
        assert pf.get_adjustment('NYY') == pytest.approx(0.0)


def test_park_factor_adjust_rv():
    """adjust_rv = actual_rv - adjustment."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _make_park_csv(tmp)
        pf = ParkFactor(csv_path=path)
        # COL: adjustment = 0.013
        adjusted = pf.adjust_rv(0.5, 'COL')
        assert adjusted == pytest.approx(0.5 - 0.013)


# === State Encoding Tests ===

def test_state_encoding_empty_0out():
    """Empty bases, 0 outs → state 0."""
    from scripts.derive_re24_baseline import encode_base_out_state
    assert encode_base_out_state(None, None, None, 0) == 0


def test_state_encoding_1b_0out():
    """Runner on 1B, 0 outs → state 1."""
    from scripts.derive_re24_baseline import encode_base_out_state
    assert encode_base_out_state(True, None, None, 0) == 1


def test_state_encoding_loaded_2out():
    """Bases loaded, 2 outs → state 23."""
    from scripts.derive_re24_baseline import encode_base_out_state
    assert encode_base_out_state(True, True, True, 2) == 23


def test_state_encoding_all_24_states():
    """모든 24 states (0~23) 인코딩 검증."""
    from scripts.derive_re24_baseline import encode_base_out_state
    seen = set()
    for outs in range(3):
        for on_3b in [False, True]:
            for on_2b in [False, True]:
                for on_1b in [False, True]:
                    state = encode_base_out_state(on_1b, on_2b, on_3b, outs)
                    assert 0 <= state <= 23
                    seen.add(state)
    assert seen == set(range(24))


# === Integrated ELO Tests ===

def test_elo_with_state_normalization():
    """State normalization: rv_diff = adjusted_rv - expected_rv."""
    with tempfile.TemporaryDirectory() as tmp:
        baseline_path = _make_baseline_csv(tmp)
        baseline = RE24Baseline(csv_path=baseline_path)
        calc = EloCalculator(re24_baseline=baseline)

        batter = PlayerEloState(player_id=1)
        pitcher = PlayerEloState(player_id=2)

        # State 0: mean_rv = -0.002, actual_rv = 0.5
        # rv_diff = 0.5 - (-0.002) = 0.502
        result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5, state=0)

        expected_delta = K_FACTOR * (0.5 - (-0.002))
        assert result.batter_delta == pytest.approx(expected_delta)
        assert result.pitcher_delta == pytest.approx(-expected_delta)


def test_elo_with_park_factor():
    """Park factor adjustment: adjusted_rv = rv - adjustment."""
    with tempfile.TemporaryDirectory() as tmp:
        park_path = _make_park_csv(tmp)
        pf = ParkFactor(csv_path=park_path)
        calc = EloCalculator(park_factor_obj=pf)

        batter = PlayerEloState(player_id=1)
        pitcher = PlayerEloState(player_id=2)

        # COL: adjustment = 0.013, actual_rv = 0.5
        # adjusted_rv = 0.5 - 0.013 = 0.487
        result = calc.process_plate_appearance(
            batter, pitcher, delta_run_exp=0.5, home_team='COL'
        )

        expected_delta = K_FACTOR * (0.5 - 0.013)
        assert result.batter_delta == pytest.approx(expected_delta)


def test_elo_with_state_and_park():
    """State + Park Factor 동시 적용."""
    with tempfile.TemporaryDirectory() as tmp:
        baseline_path = _make_baseline_csv(tmp)
        park_path = _make_park_csv(tmp)
        baseline = RE24Baseline(csv_path=baseline_path)
        pf = ParkFactor(csv_path=park_path)
        calc = EloCalculator(re24_baseline=baseline, park_factor_obj=pf)

        batter = PlayerEloState(player_id=1)
        pitcher = PlayerEloState(player_id=2)

        # COL (adj=0.013), state 0 (mean_rv=-0.002), actual=0.5
        # adjusted_rv = 0.5 - 0.013 = 0.487
        # rv_diff = 0.487 - (-0.002) = 0.489
        result = calc.process_plate_appearance(
            batter, pitcher, delta_run_exp=0.5, state=0, home_team='COL'
        )

        expected_delta = K_FACTOR * (0.5 - 0.013 - (-0.002))
        assert result.batter_delta == pytest.approx(expected_delta)


# === Field Error Handling Tests ===

def test_field_error_caps_batter_delta():
    """E result_type → batter_delta > 0 인 경우 0으로 cap."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    # 양의 RV + E → batter should NOT gain ELO
    result = calc.process_plate_appearance(
        batter, pitcher, delta_run_exp=0.5, result_type='E'
    )

    assert result.batter_delta == 0.0
    assert result.pitcher_delta == 0.0
    # ELO unchanged
    assert batter.batting_elo == INITIAL_ELO
    assert pitcher.pitching_elo == INITIAL_ELO


def test_field_error_negative_rv_unchanged():
    """E result_type → K_base=0.0이므로 delta=0 (K-Modulation: 에러는 실력 무관)."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(
        batter, pitcher, delta_run_exp=-0.3, result_type='E'
    )

    # E has K_base=0.0 → delta = 0 regardless of rv
    assert result.batter_delta == 0.0
    assert result.pitcher_delta == 0.0


def test_field_error_cumulative_rv_still_tracked():
    """E result_type에서도 cumulative_rv는 원래 RV로 추적."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5, result_type='E')

    assert batter.cumulative_rv == pytest.approx(0.5)
    assert pitcher.cumulative_rv == pytest.approx(-0.5)


# === Zero-Sum Tests ===

def test_zero_sum_with_state_and_park():
    """State + Park Factor 적용 후에도 Zero-Sum 유지."""
    with tempfile.TemporaryDirectory() as tmp:
        baseline_path = _make_baseline_csv(tmp)
        park_path = _make_park_csv(tmp)
        baseline = RE24Baseline(csv_path=baseline_path)
        pf = ParkFactor(csv_path=park_path)

        pa_df = _make_pa_df([
            {'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
             'batter_id': 100, 'pitcher_id': 200, 'result_type': 'HR',
             'delta_run_exp': 1.4, 'on_1b': False, 'on_2b': False,
             'on_3b': False, 'outs_when_up': 0, 'home_team': 'COL'},
            {'pa_id': 1001002, 'game_pk': 1001, 'game_date': '2025-04-01',
             'batter_id': 101, 'pitcher_id': 200, 'result_type': 'StrikeOut',
             'delta_run_exp': -0.3, 'on_1b': True, 'on_2b': False,
             'on_3b': False, 'outs_when_up': 1, 'home_team': 'COL'},
            {'pa_id': 1002001, 'game_pk': 1002, 'game_date': '2025-04-02',
             'batter_id': 100, 'pitcher_id': 201, 'result_type': 'OUT',
             'delta_run_exp': -0.25, 'on_1b': False, 'on_2b': False,
             'on_3b': False, 'outs_when_up': 2, 'home_team': 'SEA'},
        ])

        batch = EloBatch(re24_baseline=baseline, park_factor=pf)
        batch.process(pa_df)

        total_delta = sum(p.elo - INITIAL_ELO for p in batch.players.values())
        assert abs(total_delta) < 1e-6, f"Zero-sum violated: net={total_delta}"


# === Backward Compatibility Tests ===

def test_backward_compat_no_baseline_no_park():
    """baseline/park factor 없이 → 기존 동작과 동일."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5)

    expected_delta = K_FACTOR * 0.5
    assert result.batter_delta == pytest.approx(expected_delta)


def test_backward_compat_batch_no_extra_columns():
    """기존 형태의 PA DataFrame (state/home_team 없음)도 처리 가능."""
    pa_df = _make_pa_df([{
        'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
        'batter_id': 100, 'pitcher_id': 200, 'result_type': 'Single',
        'delta_run_exp': 0.45,
    }])

    batch = EloBatch()
    batch.process(pa_df)

    # K-Modulation: Single K_base=10.0, no xwoba → modifier=1.0
    expected_delta = EVENT_K_FACTORS['Single'] * 0.45
    assert batch.players[100].batting_elo == pytest.approx(INITIAL_ELO + expected_delta)


# === Batch with Upgrade Tests ===

def test_batch_with_upgrade_columns():
    """Upgraded batch: state + home_team + result_type 컬럼 포함."""
    with tempfile.TemporaryDirectory() as tmp:
        baseline_path = _make_baseline_csv(tmp)
        park_path = _make_park_csv(tmp)
        baseline = RE24Baseline(csv_path=baseline_path)
        pf = ParkFactor(csv_path=park_path)

        pa_df = _make_pa_df([{
            'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
            'batter_id': 100, 'pitcher_id': 200, 'result_type': 'Single',
            'delta_run_exp': 0.45, 'on_1b': False, 'on_2b': False,
            'on_3b': False, 'outs_when_up': 0, 'home_team': 'COL',
        }])

        batch = EloBatch(re24_baseline=baseline, park_factor=pf)
        batch.process(pa_df)

        # State 0 (empty 0out), COL (adj=0.013), mean_rv=-0.002
        # adjusted = 0.45 - 0.013 = 0.437
        # rv_diff = 0.437 - (-0.002) = 0.439
        # K-Modulation: Single K_base=10.0, no xwoba → modifier=1.0
        expected_delta = EVENT_K_FACTORS['Single'] * (0.45 - 0.013 - (-0.002))
        assert batch.players[100].batting_elo == pytest.approx(INITIAL_ELO + expected_delta)
