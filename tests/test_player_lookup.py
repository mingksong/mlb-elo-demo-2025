"""Players 테이블 구축 테스트."""

import pandas as pd
from src.etl.player_lookup import (
    collect_player_ids,
    extract_pitcher_names_from_statcast,
    parse_statcast_name,
    build_players_dataframe,
    determine_player_roles,
    parse_mongo_player,
)


def _make_pa_row(**overrides):
    defaults = {
        'batter': 660271,
        'pitcher': 543037,
        'player_name': 'Verlander, Justin',
        'events': 'single',
    }
    defaults.update(overrides)
    return defaults


def test_collect_player_ids():
    """PA 데이터에서 batter + pitcher 고유 ID를 모두 수집."""
    rows = [
        _make_pa_row(batter=660271, pitcher=543037),
        _make_pa_row(batter=592450, pitcher=543037),
        _make_pa_row(batter=660271, pitcher=477132),
    ]
    df = pd.DataFrame(rows)
    ids = collect_player_ids(df)
    assert ids == {660271, 592450, 543037, 477132}


def test_extract_pitcher_names_from_statcast():
    """Statcast player_name에서 pitcher_id → 이름 매핑 추출."""
    rows = [
        _make_pa_row(pitcher=543037, player_name='Verlander, Justin'),
        _make_pa_row(pitcher=543037, player_name='Verlander, Justin'),
        _make_pa_row(pitcher=477132, player_name='Kershaw, Clayton'),
    ]
    df = pd.DataFrame(rows)
    name_map = extract_pitcher_names_from_statcast(df)
    assert name_map[543037] == 'Verlander, Justin'
    assert name_map[477132] == 'Kershaw, Clayton'
    assert len(name_map) == 2


def test_parse_statcast_name():
    """'Last, First' 형식을 first_name, last_name으로 분리."""
    first, last = parse_statcast_name('Verlander, Justin')
    assert first == 'Justin'
    assert last == 'Verlander'


def test_parse_statcast_name_with_accent():
    first, last = parse_statcast_name('Ramírez, José')
    assert first == 'José'
    assert last == 'Ramírez'


def test_parse_statcast_name_with_suffix():
    """Jr., III 등 접미사가 있는 이름."""
    first, last = parse_statcast_name('Guerrero Jr., Vladimir')
    assert first == 'Vladimir'
    assert last == 'Guerrero Jr.'


def test_build_players_dataframe():
    """API 결과 + Statcast 이름으로 players DataFrame 구성."""
    api_results = {
        660271: {
            'first_name': 'Shohei',
            'last_name': 'Ohtani',
            'full_name': 'Shohei Ohtani',
            'position': 'TWP',
        },
    }
    statcast_names = {
        543037: 'Verlander, Justin',
    }
    all_ids = {660271, 543037}

    df = build_players_dataframe(all_ids, api_results, statcast_names)

    assert len(df) == 2
    assert set(df.columns) >= {'player_id', 'first_name', 'last_name', 'full_name', 'position'}

    ohtani = df[df['player_id'] == 660271].iloc[0]
    assert ohtani['first_name'] == 'Shohei'
    assert ohtani['last_name'] == 'Ohtani'
    assert ohtani['full_name'] == 'Shohei Ohtani'
    assert ohtani['position'] == 'TWP'

    verlander = df[df['player_id'] == 543037].iloc[0]
    assert verlander['first_name'] == 'Justin'
    assert verlander['last_name'] == 'Verlander'
    assert verlander['full_name'] == 'Justin Verlander'


def test_build_players_dataframe_api_overrides_statcast():
    """API 결과가 있으면 Statcast 이름보다 우선."""
    api_results = {
        543037: {
            'first_name': 'Justin',
            'last_name': 'Verlander',
            'full_name': 'Justin Verlander',
            'position': 'P',
        },
    }
    statcast_names = {
        543037: 'Verlander, Justin',
    }
    all_ids = {543037}

    df = build_players_dataframe(all_ids, api_results, statcast_names)
    row = df[df['player_id'] == 543037].iloc[0]
    assert row['position'] == 'P'  # API provides position, Statcast doesn't


def test_determine_player_roles():
    """PA 데이터에서 batter/pitcher/two_way 역할 판별."""
    rows = [
        _make_pa_row(batter=1, pitcher=10),
        _make_pa_row(batter=2, pitcher=10),
        _make_pa_row(batter=10, pitcher=3),  # 10은 투수이면서 타자
    ]
    df = pd.DataFrame(rows)
    roles = determine_player_roles(df)
    assert roles[1] == 'batter'
    assert roles[2] == 'batter'
    assert roles[3] == 'pitcher'
    assert roles[10] == 'two_way'


def test_parse_mongo_player():
    """MongoDB 문서를 player dict로 변환."""
    doc = {'player_id': '660271', 'name': 'Shohei Ohtani', 'current_team': 'Los Angeles Dodgers'}
    result = parse_mongo_player(doc)
    assert result['player_id'] == 660271
    assert result['first_name'] == 'Shohei'
    assert result['last_name'] == 'Ohtani'
    assert result['full_name'] == 'Shohei Ohtani'
    assert result['team'] == 'Los Angeles Dodgers'


def test_parse_mongo_player_single_name():
    """이름이 한 단어인 선수."""
    doc = {'player_id': '123456', 'name': 'Ichiro', 'current_team': ''}
    result = parse_mongo_player(doc)
    assert result['first_name'] == 'Ichiro'
    assert result['last_name'] == ''


def test_parse_mongo_player_three_part_name():
    """이름이 세 파트인 선수 (예: De La Cruz)."""
    doc = {'player_id': '123', 'name': 'Elly De La Cruz', 'current_team': 'Cincinnati Reds'}
    result = parse_mongo_player(doc)
    assert result['first_name'] == 'Elly'
    assert result['last_name'] == 'De La Cruz'
    assert result['full_name'] == 'Elly De La Cruz'
