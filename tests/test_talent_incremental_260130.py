"""Talent Incremental Tests — initial states, correctness, backward compat, active_only."""
import pandas as pd
import pytest
import numpy as np

from src.engine.talent_batch import TalentBatch
from src.engine.talent_state_manager import (
    TalentStateManager,
    DualBatterState,
    DualPitcherState,
)
from src.engine.multi_elo_types import (
    BatterTalentState,
    PitcherTalentState,
    DEFAULT_ELO,
    BATTER_DIM_NAMES,
    PITCHER_DIM_NAMES,
    BATTER_DIM_COUNT,
    PITCHER_DIM_COUNT,
)


def _make_pa_df(rows):
    return pd.DataFrame(rows).sort_values(['game_date', 'pa_id']).reset_index(drop=True)


def _make_pa_row(pa_id, game_date, batter_id, pitcher_id, result_type, on_2b=False, on_3b=False):
    return {
        'pa_id': pa_id, 'game_pk': 100, 'game_date': game_date,
        'batter_id': batter_id, 'pitcher_id': pitcher_id,
        'result_type': result_type,
        'on_1b': False, 'on_2b': on_2b, 'on_3b': on_3b,
    }


class TestTalentStateManagerInitialStates:

    def test_initial_batters_loaded(self):
        batter_state = DualBatterState(player_id=10)
        batter_state.season.elo_dimensions[:] = 1600.0
        batter_state.career.elo_dimensions[:] = 1600.0

        mgr = TalentStateManager(initial_batters={10: batter_state})
        result = mgr.get_or_create_batter(10)
        assert float(result.season.elo_dimensions[0]) == pytest.approx(1600.0)

    def test_initial_pitchers_loaded(self):
        pitcher_state = DualPitcherState(player_id=20)
        pitcher_state.season.elo_dimensions[:] = 1700.0
        pitcher_state.career.elo_dimensions[:] = 1700.0

        mgr = TalentStateManager(initial_pitchers={20: pitcher_state})
        result = mgr.get_or_create_pitcher(20)
        assert float(result.season.elo_dimensions[0]) == pytest.approx(1700.0)

    def test_new_player_still_default(self):
        """Player not in initial states gets default 1500."""
        mgr = TalentStateManager(initial_batters={})
        result = mgr.get_or_create_batter(99)
        assert float(result.season.elo_dimensions[0]) == pytest.approx(DEFAULT_ELO)

    def test_backward_compat_no_args(self):
        mgr = TalentStateManager()
        assert len(mgr.all_batters) == 0
        assert len(mgr.all_pitchers) == 0


class TestTalentBatchWithInitialStates:

    def test_initial_states_resume_from_custom_elo(self):
        """Pre-loaded states resume from custom ELO, not 1500."""
        batter_state = DualBatterState(player_id=10)
        batter_state.season.elo_dimensions[:] = 1700.0
        batter_state.season.pa_count = 100
        batter_state.career.elo_dimensions[:] = 1700.0
        batter_state.career.pa_count = 100

        pitcher_state = DualPitcherState(player_id=20)
        pitcher_state.season.elo_dimensions[:] = 1600.0
        pitcher_state.season.bfp_count = 50
        pitcher_state.career.elo_dimensions[:] = 1600.0
        pitcher_state.career.bfp_count = 50

        pa_df = _make_pa_df([
            _make_pa_row(1001, '2025-06-15', 10, 20, 'HR'),
        ])
        batch = TalentBatch(initial_batters={10: batter_state}, initial_pitchers={20: pitcher_state})
        batch.process(pa_df)

        batter = batch.state_mgr.all_batters[10]
        pitcher = batch.state_mgr.all_pitchers[20]

        # PA count should be incremented from initial
        assert batter.season.pa_count == 101
        assert pitcher.season.bfp_count == 51

        # Power dimension should have moved from 1700, not from 1500
        power_elo = float(batter.season.elo_dimensions[BatterTalentState.POWER])
        assert power_elo != pytest.approx(DEFAULT_ELO, abs=1.0)  # Not near default

    def test_backward_compat_no_initial_states(self):
        """No initial states = same behavior as before."""
        pa_df = _make_pa_df([
            _make_pa_row(1001, '2025-04-01', 10, 20, 'HR'),
        ])

        batch_old = TalentBatch()
        batch_old.process(pa_df)

        batch_new = TalentBatch(initial_batters=None, initial_pitchers=None)
        batch_new.process(pa_df)

        old_batter = batch_old.state_mgr.all_batters[10].season.elo_dimensions
        new_batter = batch_new.state_mgr.all_batters[10].season.elo_dimensions
        np.testing.assert_array_almost_equal(old_batter, new_batter)


class TestTalentIncrementalCorrectness:

    def test_incremental_matches_full_season(self):
        """Day1+Day2 full == Day1 then Day2 incremental."""
        day1_rows = [
            _make_pa_row(1001, '2025-04-01', 10, 20, 'HR'),
            _make_pa_row(1002, '2025-04-01', 11, 20, 'StrikeOut'),
            _make_pa_row(1003, '2025-04-01', 10, 21, 'BB'),
        ]
        day2_rows = [
            _make_pa_row(2001, '2025-04-02', 10, 20, 'Single'),
            _make_pa_row(2002, '2025-04-02', 11, 21, 'HR'),
        ]

        # Full run: all PAs at once
        full_df = _make_pa_df(day1_rows + day2_rows)
        full_batch = TalentBatch()
        full_batch.process(full_df)

        # Incremental: day1 first, extract states, then day2
        day1_df = _make_pa_df(day1_rows)
        day1_batch = TalentBatch()
        day1_batch.process(day1_df)

        # Extract states from day1
        init_batters = dict(day1_batch.state_mgr.all_batters)
        init_pitchers = dict(day1_batch.state_mgr.all_pitchers)

        day2_df = _make_pa_df(day2_rows)
        day2_batch = TalentBatch(initial_batters=init_batters, initial_pitchers=init_pitchers)
        day2_batch.process(day2_df)

        # Compare final states
        for pid in full_batch.state_mgr.all_batters:
            full_elo = full_batch.state_mgr.all_batters[pid].season.elo_dimensions
            incr_elo = day2_batch.state_mgr.all_batters[pid].season.elo_dimensions
            np.testing.assert_array_almost_equal(
                full_elo, incr_elo, decimal=6,
                err_msg=f"Batter {pid} ELO mismatch: full vs incremental"
            )

        for pid in full_batch.state_mgr.all_pitchers:
            full_elo = full_batch.state_mgr.all_pitchers[pid].season.elo_dimensions
            incr_elo = day2_batch.state_mgr.all_pitchers[pid].season.elo_dimensions
            np.testing.assert_array_almost_equal(
                full_elo, incr_elo, decimal=6,
                err_msg=f"Pitcher {pid} ELO mismatch: full vs incremental"
            )


class TestTalentActiveOnlyFilter:

    def test_active_only_filter(self):
        """3 players pre-loaded, 2 active in new PAs, active_only=True returns only 2."""
        # Pre-load 3 batters
        b1 = DualBatterState(player_id=10)
        b2 = DualBatterState(player_id=11)
        b3 = DualBatterState(player_id=12)  # Inactive — won't appear in PAs

        p1 = DualPitcherState(player_id=20)

        pa_df = _make_pa_df([
            _make_pa_row(1001, '2025-04-01', 10, 20, 'HR'),
            _make_pa_row(1002, '2025-04-01', 11, 20, 'StrikeOut'),
        ])

        batch = TalentBatch(
            initial_batters={10: b1, 11: b2, 12: b3},
            initial_pitchers={20: p1},
        )
        batch.process(pa_df)

        # All records (includes inactive player 12)
        all_records = batch.get_talent_player_records(active_only=False)
        all_pids = {r['player_id'] for r in all_records}
        assert 12 in all_pids

        # Active only (excludes inactive player 12)
        active_records = batch.get_talent_player_records(active_only=True)
        active_pids = {r['player_id'] for r in active_records}
        assert 10 in active_pids
        assert 11 in active_pids
        assert 20 in active_pids
        assert 12 not in active_pids

    def test_active_only_default_false(self):
        """Default active_only=False returns all."""
        b1 = DualBatterState(player_id=10)
        b2 = DualBatterState(player_id=11)
        p1 = DualPitcherState(player_id=20)

        pa_df = _make_pa_df([
            _make_pa_row(1001, '2025-04-01', 10, 20, 'HR'),
        ])
        batch = TalentBatch(
            initial_batters={10: b1, 11: b2},
            initial_pitchers={20: p1},
        )
        batch.process(pa_df)

        all_records = batch.get_talent_player_records()  # default
        all_pids = {r['player_id'] for r in all_records}
        # Player 11 was pre-loaded but not active — still included because active_only=False
        assert 11 in all_pids
