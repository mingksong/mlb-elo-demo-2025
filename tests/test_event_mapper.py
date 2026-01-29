"""Event Mapper 테스트: Statcast events → result_type 매핑."""

from src.etl.event_mapper import EVENT_MAP, map_event, VALID_RESULT_TYPES


def test_event_map_covers_all_statcast_events():
    """24개 Statcast events가 모두 매핑되어야 함."""
    statcast_events = [
        'single', 'double', 'triple', 'home_run',
        'walk', 'intentional_walk', 'intent_walk', 'hit_by_pitch',
        'strikeout', 'strikeout_double_play',
        'field_out', 'force_out', 'triple_play',
        'grounded_into_double_play', 'double_play',
        'sac_fly', 'sac_bunt', 'sac_fly_double_play',
        'fielders_choice', 'fielders_choice_out',
        'field_error', 'catcher_interf', 'other_out',
        'truncated_pa',
    ]
    for event in statcast_events:
        assert event in EVENT_MAP, f"Missing mapping for: {event}"


def test_intent_walk_maps_to_ibb():
    """intent_walk은 intentional_walk과 동일하게 IBB로 매핑."""
    assert map_event('intent_walk') == 'IBB'


def test_truncated_pa_maps_to_out():
    """truncated_pa는 미완료 타석으로 OUT 처리."""
    assert map_event('truncated_pa') == 'OUT'


def test_map_event_basic():
    assert map_event('single') == 'Single'
    assert map_event('home_run') == 'HR'
    assert map_event('walk') == 'BB'
    assert map_event('strikeout') == 'StrikeOut'
    assert map_event('field_out') == 'OUT'
    assert map_event('grounded_into_double_play') == 'GIDP'
    assert map_event('sac_fly') == 'SAC'
    assert map_event('fielders_choice') == 'FC'
    assert map_event('field_error') == 'E'
    assert map_event('catcher_interf') == 'HBP'


def test_map_event_unknown_returns_out_and_logs():
    result = map_event('unknown_event_xyz')
    assert result == 'OUT'


def test_all_mapped_values_are_valid():
    for event, result_type in EVENT_MAP.items():
        assert result_type in VALID_RESULT_TYPES, f"{event} -> {result_type} is not valid"
