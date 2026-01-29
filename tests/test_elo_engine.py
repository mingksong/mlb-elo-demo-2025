"""V5.3 ELO Engine 테스트 (MLB 포팅)."""

import pytest
from src.engine.elo_config import INITIAL_ELO, MIN_ELO, K_FACTOR
from src.engine.elo_calculator import PlayerEloState, EloCalculator


# === Config Tests ===

def test_config_constants():
    """ELO 설정 상수 확인."""
    assert INITIAL_ELO == 1500.0
    assert MIN_ELO == 500.0
    assert K_FACTOR == 12.0


# === PlayerEloState Tests ===

def test_player_state_defaults():
    """선수 초기 상태."""
    state = PlayerEloState(player_id=660271)
    assert state.elo == INITIAL_ELO
    assert state.pa_count == 0
    assert state.cumulative_rv == 0.0


def test_player_state_apply_delta():
    """ELO 변화 적용."""
    state = PlayerEloState(player_id=660271)
    state.apply_delta(10.0)
    assert state.elo == 1510.0


def test_player_state_min_elo_clamp():
    """ELO 하한선 (500) 보장."""
    state = PlayerEloState(player_id=660271, elo=510.0)
    state.apply_delta(-20.0)
    assert state.elo == MIN_ELO  # 500.0, not 490.0


# === EloCalculator Tests ===

def test_process_pa_positive_rv():
    """양의 Run Value → 타자 ELO 상승, 투수 ELO 하락."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5)

    assert result.batter_delta > 0
    assert result.pitcher_delta < 0
    assert batter.elo > INITIAL_ELO
    assert pitcher.elo < INITIAL_ELO


def test_process_pa_negative_rv():
    """음의 Run Value → 타자 ELO 하락, 투수 ELO 상승."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=-0.3)

    assert result.batter_delta < 0
    assert result.pitcher_delta > 0


def test_zero_sum_guarantee():
    """Zero-Sum: batter_delta + pitcher_delta = 0."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.45)

    assert abs(result.batter_delta + result.pitcher_delta) < 1e-10


def test_delta_formula():
    """ELO delta = K * delta_run_exp."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    rv = 0.25
    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=rv)

    expected_delta = K_FACTOR * rv
    assert abs(result.batter_delta - expected_delta) < 1e-10


def test_pa_count_incremented():
    """타석 수 증가 확인."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.1)

    assert batter.pa_count == 1
    assert pitcher.pa_count == 1


def test_cumulative_rv_tracked():
    """누적 Run Value 추적."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5)
    calc.process_plate_appearance(batter, pitcher, delta_run_exp=-0.3)

    assert abs(batter.cumulative_rv - 0.2) < 1e-10
    assert abs(pitcher.cumulative_rv - (-0.2)) < 1e-10


def test_null_rv_skipped():
    """delta_run_exp가 None이면 ELO 변화 없음."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=None)

    assert result.batter_delta == 0.0
    assert result.pitcher_delta == 0.0
    assert batter.elo == INITIAL_ELO
    assert pitcher.elo == INITIAL_ELO
    # PA count still increments (the PA happened)
    assert batter.pa_count == 1
    assert pitcher.pa_count == 1


def test_multiple_pas_accumulate():
    """여러 타석의 ELO가 누적."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    # HR-like positive RV
    calc.process_plate_appearance(batter, pitcher, delta_run_exp=1.4)
    # Strikeout-like negative RV
    calc.process_plate_appearance(batter, pitcher, delta_run_exp=-0.3)
    # Walk-like small positive RV
    calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.3)

    total_rv = 1.4 - 0.3 + 0.3
    expected_elo = INITIAL_ELO + K_FACTOR * total_rv
    assert abs(batter.elo - expected_elo) < 1e-10
    assert batter.pa_count == 3


def test_result_contains_elo_before_after():
    """결과에 before/after ELO 포함."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5)

    assert result.batter_elo_before == INITIAL_ELO
    assert result.batter_elo_after == batter.elo
    assert result.pitcher_elo_before == INITIAL_ELO
    assert result.pitcher_elo_after == pitcher.elo
