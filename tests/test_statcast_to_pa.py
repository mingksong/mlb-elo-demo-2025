"""Statcast → Plate Appearance 변환 테스트."""

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
