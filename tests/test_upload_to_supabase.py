"""Supabase 업로드 모듈 테스트."""

import pandas as pd
import math
from src.etl.upload_to_supabase import prepare_pa_records, prepare_player_records


def test_prepare_player_records():
    """players DataFrame을 Supabase upsert용 dict 리스트로 변환."""
    df = pd.DataFrame([
        {'player_id': 660271, 'first_name': 'Shohei', 'last_name': 'Ohtani',
         'full_name': 'Shohei Ohtani', 'team': 'Los Angeles Dodgers', 'position': 'two_way'},
    ])
    records = prepare_player_records(df)
    assert len(records) == 1
    assert records[0]['player_id'] == 660271
    assert records[0]['full_name'] == 'Shohei Ohtani'


def test_prepare_pa_records():
    """plate_appearances DataFrame을 Supabase upsert용 dict 리스트로 변환."""
    df = pd.DataFrame([{
        'pa_id': 717001001,
        'game_pk': 717001,
        'game_date': pd.Timestamp('2025-04-01'),
        'season_year': 2025,
        'batter_id': 660271,
        'pitcher_id': 543037,
        'result_type': 'Single',
        'inning': 1,
        'inning_half': 'Top',
        'at_bat_number': 1,
        'outs_when_up': 0,
        'on_1b': False,
        'on_2b': True,
        'on_3b': False,
        'home_team': 'NYY',
        'away_team': 'BOS',
        'bat_score': 0,
        'fld_score': 0,
        'launch_speed': 95.2,
        'launch_angle': 12.0,
        'xwoba': 0.380,
        'delta_run_exp': 0.45,
    }])
    records = prepare_pa_records(df)
    assert len(records) == 1
    r = records[0]
    assert r['pa_id'] == 717001001
    assert r['game_date'] == '2025-04-01'  # ISO string
    assert r['on_2b'] is True


def test_prepare_pa_records_nan_to_none():
    """NaN 값은 None으로 변환."""
    df = pd.DataFrame([{
        'pa_id': 717001001,
        'game_pk': 717001,
        'game_date': pd.Timestamp('2025-04-01'),
        'season_year': 2025,
        'batter_id': 660271,
        'pitcher_id': 543037,
        'result_type': 'StrikeOut',
        'inning': 1,
        'inning_half': 'Top',
        'at_bat_number': 1,
        'outs_when_up': 0,
        'on_1b': False,
        'on_2b': False,
        'on_3b': False,
        'home_team': 'NYY',
        'away_team': 'BOS',
        'bat_score': 0,
        'fld_score': 0,
        'launch_speed': float('nan'),
        'launch_angle': float('nan'),
        'xwoba': float('nan'),
        'delta_run_exp': 0.0,
    }])
    records = prepare_pa_records(df)
    r = records[0]
    assert r['launch_speed'] is None
    assert r['launch_angle'] is None
    assert r['xwoba'] is None
