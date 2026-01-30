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
    assert state.batting_elo == INITIAL_ELO
    assert state.pitching_elo == INITIAL_ELO
    assert state.batting_pa == 0
    assert state.pitching_pa == 0
    assert state.elo == INITIAL_ELO  # composite property
    assert state.pa_count == 0  # composite property
    assert state.cumulative_rv == 0.0


def test_player_state_apply_batting_delta():
    """타자 ELO 변화 적용."""
    state = PlayerEloState(player_id=660271)
    state.apply_batting_delta(10.0)
    assert state.batting_elo == 1510.0
    assert state.pitching_elo == INITIAL_ELO  # unchanged


def test_player_state_apply_pitching_delta():
    """투수 ELO 변화 적용."""
    state = PlayerEloState(player_id=660271)
    state.apply_pitching_delta(-10.0)
    assert state.pitching_elo == 1490.0
    assert state.batting_elo == INITIAL_ELO  # unchanged


def test_player_state_min_elo_clamp_batting():
    """타자 ELO 하한선 (500) 보장."""
    state = PlayerEloState(player_id=660271, batting_elo=510.0)
    state.apply_batting_delta(-20.0)
    assert state.batting_elo == MIN_ELO  # 500.0, not 490.0


def test_player_state_min_elo_clamp_pitching():
    """투수 ELO 하한선 (500) 보장."""
    state = PlayerEloState(player_id=660271, pitching_elo=510.0)
    state.apply_pitching_delta(-20.0)
    assert state.pitching_elo == MIN_ELO  # 500.0, not 490.0


def test_player_state_composite_elo():
    """Composite ELO = weighted average of batting and pitching."""
    state = PlayerEloState(player_id=1, batting_elo=1600.0, pitching_elo=1400.0,
                           batting_pa=100, pitching_pa=100)
    assert state.elo == 1500.0  # (1600*100 + 1400*100) / 200


# === EloCalculator Tests ===

def test_process_pa_positive_rv():
    """양의 Run Value → 타자 batting_elo 상승, 투수 pitching_elo 하락."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5)

    assert result.batter_delta > 0
    assert result.pitcher_delta < 0
    assert batter.batting_elo > INITIAL_ELO
    assert pitcher.pitching_elo < INITIAL_ELO


def test_process_pa_negative_rv():
    """음의 Run Value → 타자 batting_elo 하락, 투수 pitching_elo 상승."""
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
    """타석 수 증가 확인 (batting_pa / pitching_pa)."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.1)

    assert batter.batting_pa == 1
    assert batter.pitching_pa == 0
    assert pitcher.pitching_pa == 1
    assert pitcher.batting_pa == 0
    # Composite pa_count
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
    assert batter.batting_elo == INITIAL_ELO
    assert pitcher.pitching_elo == INITIAL_ELO
    # PA count still increments (the PA happened)
    assert batter.batting_pa == 1
    assert pitcher.pitching_pa == 1


def test_multiple_pas_accumulate():
    """여러 타석의 batting_elo가 누적."""
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
    assert abs(batter.batting_elo - expected_elo) < 1e-10
    assert batter.batting_pa == 3


def test_result_contains_elo_before_after():
    """결과에 before/after ELO 포함 (batting/pitching)."""
    calc = EloCalculator()
    batter = PlayerEloState(player_id=1)
    pitcher = PlayerEloState(player_id=2)

    result = calc.process_plate_appearance(batter, pitcher, delta_run_exp=0.5)

    assert result.batter_elo_before == INITIAL_ELO
    assert result.batter_elo_after == batter.batting_elo
    assert result.pitcher_elo_before == INITIAL_ELO
    assert result.pitcher_elo_after == pitcher.pitching_elo


# === Two-Way Player (TWP) Tests ===

def test_twp_independent_elo():
    """TWP: 같은 선수가 타석/투구 시 batting_elo와 pitching_elo가 독립 변동."""
    calc = EloCalculator()
    twp = PlayerEloState(player_id=660271)  # Ohtani-like
    opponent_pitcher = PlayerEloState(player_id=100)
    opponent_batter = PlayerEloState(player_id=200)

    # TWP가 타자로 출전: batting_elo 변동
    calc.process_plate_appearance(twp, opponent_pitcher, delta_run_exp=1.0)
    assert twp.batting_elo == INITIAL_ELO + K_FACTOR * 1.0
    assert twp.pitching_elo == INITIAL_ELO  # pitching unchanged

    # TWP가 투수로 출전: pitching_elo 변동
    calc.process_plate_appearance(opponent_batter, twp, delta_run_exp=-0.5)
    assert twp.pitching_elo == INITIAL_ELO + K_FACTOR * 0.5  # pitcher gains on negative rv
    assert twp.batting_elo == INITIAL_ELO + K_FACTOR * 1.0  # batting unchanged

    # PA counts
    assert twp.batting_pa == 1
    assert twp.pitching_pa == 1
    assert twp.pa_count == 2


def test_twp_composite_elo_weighted():
    """TWP: composite ELO는 PA 가중 평균."""
    calc = EloCalculator()
    twp = PlayerEloState(player_id=660271)
    opp_p = PlayerEloState(player_id=100)
    opp_b = PlayerEloState(player_id=200)

    # 2 batting PAs: +1.0 each → batting_elo = 1500 + 12*1.0 + 12*1.0 = 1524
    calc.process_plate_appearance(twp, opp_p, delta_run_exp=1.0)
    calc.process_plate_appearance(twp, opp_p, delta_run_exp=1.0)
    # 1 pitching PA: opp hits -0.3 → pitcher gains 0.3 → pitching_elo = 1500 + 12*0.3 = 1503.6
    calc.process_plate_appearance(opp_b, twp, delta_run_exp=-0.3)

    expected_composite = (twp.batting_elo * 2 + twp.pitching_elo * 1) / 3
    assert abs(twp.elo - expected_composite) < 1e-10
