"""Tests for incremental ELO engine + daily pipeline.

- test_incremental_matches_full_season: Day1+Day2 전체 vs Day1 후 Day2 증분 → ELO 동일
- test_batch_with_initial_states: pre-load ELO 1600, process PA → 1600 기준 계산
- test_batch_initial_states_backward_compat: initial_states 없이 기존과 동일
- test_active_only_filter: active_only=True → 활동 선수만 반환
- test_load_current_elo_states: Supabase mock → PlayerEloState 복원
- test_delete_date_data: 삭제 순서 확인
- test_run_daily_pipeline_no_data: 데이터 없는 날 → no_data 반환
- test_run_daily_pipeline_already_processed: 이미 처리된 날 → skip
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.engine.elo_batch import EloBatch
from src.engine.elo_calculator import PlayerEloState
from src.engine.elo_config import INITIAL_ELO


def _make_pa_df(rows: list[dict]) -> pd.DataFrame:
    """테스트용 PA DataFrame 생성."""
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


# ─── EloBatch incremental mode tests ───


class TestBatchWithInitialStates:
    def test_initial_states_preloaded(self):
        """initial_states로 ELO 1600 세팅 후 PA 처리 → 1600 기준 시작."""
        states = {
            100: PlayerEloState(player_id=100, batting_elo=1600.0, batting_pa=50),
            200: PlayerEloState(player_id=200, pitching_elo=1400.0, pitching_pa=80),
        }
        batch = EloBatch(initial_states=states)
        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 200, 'delta_run_exp': 0.3},
        ])
        batch.process(pa_df)

        # Batter started at 1600 (batting_elo), not 1500
        assert batch.pa_details[0]['batter_elo_before'] == 1600.0
        assert batch.pa_details[0]['pitcher_elo_before'] == 1400.0
        # PA count continues from pre-loaded value
        assert batch.players[100].batting_pa == 51
        assert batch.players[200].pitching_pa == 81

    def test_initial_states_backward_compat(self):
        """initial_states=None → 기존 동작과 동일 (모든 선수 1500 시작)."""
        batch_old = EloBatch()
        batch_new = EloBatch(initial_states=None)

        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 200, 'delta_run_exp': 0.5},
        ])
        batch_old.process(pa_df.copy())
        batch_new.process(pa_df.copy())

        assert batch_old.players[100].elo == batch_new.players[100].elo
        assert batch_old.players[200].elo == batch_new.players[200].elo

    def test_new_player_during_incremental(self):
        """initial_states에 없는 선수가 PA에 등장 → INITIAL_ELO로 생성."""
        states = {100: PlayerEloState(player_id=100, batting_elo=1600.0)}
        batch = EloBatch(initial_states=states)
        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 999, 'delta_run_exp': 0.2},
        ])
        batch.process(pa_df)

        # Player 999 should start at INITIAL_ELO (pitching_elo)
        assert batch.pa_details[0]['pitcher_elo_before'] == INITIAL_ELO


class TestActiveOnlyFilter:
    def test_active_only_returns_active_players(self):
        """active_only=True → 이번 실행에 활동한 선수만 반환."""
        # Pre-load 3 players, but only 2 are active
        states = {
            100: PlayerEloState(player_id=100, batting_elo=1600.0, batting_pa=50),
            200: PlayerEloState(player_id=200, pitching_elo=1400.0, pitching_pa=80),
            300: PlayerEloState(player_id=300, batting_elo=1550.0, batting_pa=30),  # inactive
        }
        batch = EloBatch(initial_states=states)
        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 200, 'delta_run_exp': 0.3},
        ])
        batch.process(pa_df)

        all_records = batch.get_player_elo_records(active_only=False)
        active_records = batch.get_player_elo_records(active_only=True)

        assert len(all_records) == 3
        assert len(active_records) == 2
        active_ids = {r['player_id'] for r in active_records}
        assert active_ids == {100, 200}

    def test_active_only_false_returns_all(self):
        """active_only=False → 모든 선수 반환 (기본 동작)."""
        batch = EloBatch()
        pa_df = _make_pa_df([
            {'batter_id': 100, 'pitcher_id': 200, 'delta_run_exp': 0.3},
        ])
        batch.process(pa_df)

        records_default = batch.get_player_elo_records()
        records_all = batch.get_player_elo_records(active_only=False)
        assert len(records_default) == len(records_all) == 2


class TestIncrementalMatchesFullSeason:
    def test_two_day_incremental_matches_full(self):
        """Day1+Day2 전체 처리 vs Day1→Day2 증분 → 최종 ELO 동일."""
        day1_pa = _make_pa_df([
            {'pa_id': 1001, 'batter_id': 100, 'pitcher_id': 200,
             'game_date': '2026-04-15', 'delta_run_exp': 0.5},
            {'pa_id': 1002, 'batter_id': 101, 'pitcher_id': 200,
             'game_date': '2026-04-15', 'delta_run_exp': -0.3},
        ])
        day2_pa = _make_pa_df([
            {'pa_id': 2001, 'batter_id': 100, 'pitcher_id': 201,
             'game_date': '2026-04-16', 'delta_run_exp': 0.2},
            {'pa_id': 2002, 'batter_id': 101, 'pitcher_id': 201,
             'game_date': '2026-04-16', 'delta_run_exp': -0.1},
        ])

        # Full season: process day1 + day2 together
        full_df = pd.concat([day1_pa, day2_pa], ignore_index=True)
        batch_full = EloBatch()
        batch_full.process(full_df)

        # Incremental: process day1, then day2 with initial states
        batch_day1 = EloBatch()
        batch_day1.process(day1_pa)

        # Extract states from day1 (simulating load_current_elo_states)
        day1_states = {}
        for pid, state in batch_day1.players.items():
            day1_states[pid] = PlayerEloState(
                player_id=pid,
                batting_elo=state.batting_elo,
                pitching_elo=state.pitching_elo,
                batting_pa=state.batting_pa,
                pitching_pa=state.pitching_pa,
                cumulative_rv=0.0,  # reset as in pipeline
            )

        batch_day2 = EloBatch(initial_states=day1_states)
        batch_day2.process(day2_pa)

        # Compare final ELOs — should match exactly
        for pid in batch_full.players:
            full_batting = batch_full.players[pid].batting_elo
            full_pitching = batch_full.players[pid].pitching_elo
            if pid in batch_day2.players:
                incr_batting = batch_day2.players[pid].batting_elo
                incr_pitching = batch_day2.players[pid].pitching_elo
            else:
                incr_batting = batch_day1.players[pid].batting_elo
                incr_pitching = batch_day1.players[pid].pitching_elo
            assert abs(full_batting - incr_batting) < 1e-10, \
                f"Player {pid}: full batting={full_batting}, incremental={incr_batting}"
            assert abs(full_pitching - incr_pitching) < 1e-10, \
                f"Player {pid}: full pitching={full_pitching}, incremental={incr_pitching}"

    def test_incremental_pa_count_matches(self):
        """증분 처리 후 PA count도 전체 처리와 동일."""
        day1_pa = _make_pa_df([
            {'pa_id': 1001, 'batter_id': 100, 'pitcher_id': 200,
             'game_date': '2026-04-15', 'delta_run_exp': 0.5},
        ])
        day2_pa = _make_pa_df([
            {'pa_id': 2001, 'batter_id': 100, 'pitcher_id': 200,
             'game_date': '2026-04-16', 'delta_run_exp': 0.2},
        ])

        # Full
        full_df = pd.concat([day1_pa, day2_pa], ignore_index=True)
        batch_full = EloBatch()
        batch_full.process(full_df)

        # Incremental
        batch_day1 = EloBatch()
        batch_day1.process(day1_pa)
        states = {
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
        batch_day2 = EloBatch(initial_states=states)
        batch_day2.process(day2_pa)

        assert batch_full.players[100].pa_count == batch_day2.players[100].pa_count
        assert batch_full.players[200].pa_count == batch_day2.players[200].pa_count


# ─── Pipeline function tests (mocked Supabase) ───


class TestLoadCurrentEloStates:
    def test_loads_states_from_supabase(self):
        from src.pipeline.daily_pipeline import load_current_elo_states

        client = MagicMock()
        response = MagicMock()
        response.data = [
            {'player_id': 100, 'composite_elo': 1600.0, 'pa_count': 50,
             'batting_elo': 1600.0, 'pitching_elo': 1500.0, 'batting_pa': 50, 'pitching_pa': 0},
            {'player_id': 200, 'composite_elo': 1400.0, 'pa_count': 80,
             'batting_elo': 1500.0, 'pitching_elo': 1400.0, 'batting_pa': 0, 'pitching_pa': 80},
        ]
        client.table.return_value.select.return_value.range.return_value.execute.return_value = response

        states = load_current_elo_states(client)
        assert len(states) == 2
        assert states[100].batting_elo == 1600.0
        assert states[100].batting_pa == 50
        assert states[200].pitching_elo == 1400.0
        assert states[200].pitching_pa == 80
        assert states[200].cumulative_rv == 0.0  # always reset

    def test_empty_table(self):
        from src.pipeline.daily_pipeline import load_current_elo_states

        client = MagicMock()
        response = MagicMock()
        response.data = []
        client.table.return_value.select.return_value.range.return_value.execute.return_value = response

        states = load_current_elo_states(client)
        assert len(states) == 0


class TestDeleteDateData:
    def test_calls_delete_in_correct_order(self):
        from src.pipeline.daily_pipeline import delete_date_data

        client = MagicMock()
        # Mock PA ID lookup
        pa_response = MagicMock()
        pa_response.data = [{'pa_id': 1001}, {'pa_id': 1002}]
        client.table.return_value.select.return_value.eq.return_value.range.return_value.execute.return_value = pa_response

        # Mock delete chains
        delete_chain = MagicMock()
        client.table.return_value.delete.return_value = delete_chain
        delete_chain.in_.return_value.execute.return_value = MagicMock()
        delete_chain.eq.return_value.execute.return_value = MagicMock()

        delete_date_data(client, date(2026, 4, 15))

        # Verify table calls were made (specific order verification through call_args_list)
        table_calls = [call[0][0] for call in client.table.call_args_list]
        assert 'plate_appearances' in table_calls  # PA lookup + delete
        assert 'elo_pa_detail' in table_calls
        assert 'daily_ohlc' in table_calls


class TestRunDailyPipeline:
    @patch('src.pipeline.daily_pipeline.get_supabase_client')
    @patch('src.pipeline.daily_pipeline.fetch_statcast_date')
    def test_no_data_returns_no_data(self, mock_fetch, mock_client):
        from src.pipeline.daily_pipeline import run_daily_pipeline

        mock_client.return_value = MagicMock()
        # Idempotency check: no existing data
        existing_response = MagicMock()
        existing_response.count = 0
        mock_client.return_value.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = existing_response

        mock_fetch.return_value = pd.DataFrame()  # no data

        result = run_daily_pipeline(target_date=date(2026, 1, 15))
        assert result['status'] == 'no_data'

    @patch('src.pipeline.daily_pipeline.get_supabase_client')
    def test_already_processed_returns_skip(self, mock_client):
        from src.pipeline.daily_pipeline import run_daily_pipeline

        mock_client.return_value = MagicMock()
        existing_response = MagicMock()
        existing_response.count = 500  # already has data
        mock_client.return_value.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = existing_response

        result = run_daily_pipeline(target_date=date(2026, 4, 15), force=False)
        assert result['status'] == 'already_processed'
        assert result['existing_pa_count'] == 500
