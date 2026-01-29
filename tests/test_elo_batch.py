"""V5.3 ELO 배치 프로세서 + OHLC 테스트."""

import pandas as pd
from datetime import date

from src.engine.elo_config import INITIAL_ELO, K_FACTOR
from src.engine.elo_batch import EloBatch, DailyOhlc


# === DailyOhlc Tests ===

def test_daily_ohlc_delta():
    """delta = close - open."""
    ohlc = DailyOhlc(
        player_id=1, game_date=date(2025, 4, 1), elo_type='SEASON',
        open_elo=1500.0, high_elo=1520.0, low_elo=1490.0, close_elo=1510.0,
    )
    assert abs(ohlc.delta - 10.0) < 1e-10


def test_daily_ohlc_range():
    """range = high - low."""
    ohlc = DailyOhlc(
        player_id=1, game_date=date(2025, 4, 1), elo_type='SEASON',
        open_elo=1500.0, high_elo=1520.0, low_elo=1490.0, close_elo=1510.0,
    )
    assert abs(ohlc.elo_range - 30.0) < 1e-10


# === EloBatch Tests ===

def _make_pa_df(rows):
    """테스트용 PA DataFrame 생성."""
    return pd.DataFrame(rows).sort_values(['game_date', 'pa_id']).reset_index(drop=True)


def test_batch_single_pa():
    """단일 타석 처리."""
    pa_df = _make_pa_df([{
        'pa_id': 1001001,
        'game_pk': 1001,
        'game_date': '2025-04-01',
        'batter_id': 100,
        'pitcher_id': 200,
        'result_type': 'Single',
        'delta_run_exp': 0.45,
    }])

    batch = EloBatch()
    batch.process(pa_df)

    # 타자 ELO 상승
    assert batch.players[100].elo > INITIAL_ELO
    # 투수 ELO 하락
    assert batch.players[200].elo < INITIAL_ELO
    # PA 디테일 기록
    assert len(batch.pa_details) == 1
    assert batch.pa_details[0]['pa_id'] == 1001001


def test_batch_zero_sum():
    """전체 시스템 Zero-Sum 확인."""
    pa_df = _make_pa_df([
        {'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 100, 'pitcher_id': 200, 'result_type': 'HR',
         'delta_run_exp': 1.4},
        {'pa_id': 1001002, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 101, 'pitcher_id': 200, 'result_type': 'StrikeOut',
         'delta_run_exp': -0.3},
        {'pa_id': 1001003, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 100, 'pitcher_id': 201, 'result_type': 'OUT',
         'delta_run_exp': -0.25},
    ])

    batch = EloBatch()
    batch.process(pa_df)

    total_delta = sum(p.elo - INITIAL_ELO for p in batch.players.values())
    assert abs(total_delta) < 1e-6, f"Zero-sum violated: net={total_delta}"


def test_batch_null_rv_handled():
    """delta_run_exp가 None인 PA 처리."""
    pa_df = _make_pa_df([
        {'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 100, 'pitcher_id': 200, 'result_type': 'StrikeOut',
         'delta_run_exp': None},
    ])

    batch = EloBatch()
    batch.process(pa_df)

    assert batch.players[100].elo == INITIAL_ELO
    assert len(batch.pa_details) == 1


def test_batch_ohlc_single_day():
    """단일 날짜 OHLC 생성."""
    pa_df = _make_pa_df([
        {'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 100, 'pitcher_id': 200, 'result_type': 'HR',
         'delta_run_exp': 1.4},
        {'pa_id': 1001002, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 100, 'pitcher_id': 200, 'result_type': 'OUT',
         'delta_run_exp': -0.25},
    ])

    batch = EloBatch()
    batch.process(pa_df)

    ohlc_list = batch.daily_ohlc
    # player 100 should have OHLC
    batter_ohlc = [o for o in ohlc_list if o.player_id == 100]
    assert len(batter_ohlc) == 1

    ohlc = batter_ohlc[0]
    assert ohlc.open_elo == INITIAL_ELO
    assert ohlc.close_elo == 100 + K_FACTOR * (1.4 - 0.25) + INITIAL_ELO - 100  # computed
    assert ohlc.high_elo >= ohlc.open_elo
    assert ohlc.low_elo <= ohlc.close_elo
    assert ohlc.total_pa == 2


def test_batch_ohlc_multi_day():
    """여러 날짜 OHLC: Open은 전일 Close."""
    pa_df = _make_pa_df([
        {'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 100, 'pitcher_id': 200, 'result_type': 'HR',
         'delta_run_exp': 1.0},
        {'pa_id': 1002001, 'game_pk': 1002, 'game_date': '2025-04-02',
         'batter_id': 100, 'pitcher_id': 201, 'result_type': 'OUT',
         'delta_run_exp': -0.2},
    ])

    batch = EloBatch()
    batch.process(pa_df)

    ohlc_list = [o for o in batch.daily_ohlc if o.player_id == 100]
    assert len(ohlc_list) == 2

    day1 = [o for o in ohlc_list if str(o.game_date) == '2025-04-01'][0]
    day2 = [o for o in ohlc_list if str(o.game_date) == '2025-04-02'][0]

    # Day 2 open = Day 1 close
    assert abs(day2.open_elo - day1.close_elo) < 1e-10


def test_batch_pa_detail_records():
    """PA 디테일 레코드 형식."""
    pa_df = _make_pa_df([{
        'pa_id': 1001001,
        'game_pk': 1001,
        'game_date': '2025-04-01',
        'batter_id': 100,
        'pitcher_id': 200,
        'result_type': 'Single',
        'delta_run_exp': 0.45,
    }])

    batch = EloBatch()
    batch.process(pa_df)

    detail = batch.pa_details[0]
    assert detail['pa_id'] == 1001001
    assert detail['batter_id'] == 100
    assert detail['pitcher_id'] == 200
    assert detail['result_type'] == 'Single'
    assert detail['batter_elo_before'] == INITIAL_ELO
    assert detail['batter_elo_after'] > INITIAL_ELO
    assert detail['pitcher_elo_before'] == INITIAL_ELO
    assert detail['pitcher_elo_after'] < INITIAL_ELO
    assert 'elo_delta' in detail


def test_batch_player_elo_records():
    """player_elo 레코드 생성."""
    pa_df = _make_pa_df([
        {'pa_id': 1001001, 'game_pk': 1001, 'game_date': '2025-04-01',
         'batter_id': 100, 'pitcher_id': 200, 'result_type': 'HR',
         'delta_run_exp': 1.4},
    ])

    batch = EloBatch()
    batch.process(pa_df)

    records = batch.get_player_elo_records()
    assert len(records) == 2  # batter + pitcher

    batter_rec = [r for r in records if r['player_id'] == 100][0]
    assert batter_rec['composite_elo'] > INITIAL_ELO
    assert batter_rec['pa_count'] == 1
    assert batter_rec['last_game_date'] == '2025-04-01'
