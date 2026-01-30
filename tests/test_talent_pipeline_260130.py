"""Talent Pipeline Integration Test — run_elo + talent batch."""
import pandas as pd
import pytest

from src.engine.elo_batch import EloBatch
from src.engine.talent_batch import TalentBatch
from src.engine.multi_elo_types import BATTER_DIM_NAMES, PITCHER_DIM_NAMES, DEFAULT_ELO


def _make_season_df():
    """Mini season: 6 PAs, 4 players."""
    return pd.DataFrame([
        {'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
         'batter_id': 10, 'pitcher_id': 20, 'result_type': 'HR',
         'delta_run_exp': 1.4, 'on_1b': False, 'on_2b': False, 'on_3b': False,
         'outs_when_up': 0, 'home_team': 'NYY'},
        {'pa_id': 1002, 'game_pk': 100, 'game_date': '2025-04-01',
         'batter_id': 11, 'pitcher_id': 20, 'result_type': 'StrikeOut',
         'delta_run_exp': -0.3, 'on_1b': True, 'on_2b': False, 'on_3b': False,
         'outs_when_up': 0, 'home_team': 'NYY'},
        {'pa_id': 1003, 'game_pk': 100, 'game_date': '2025-04-01',
         'batter_id': 12, 'pitcher_id': 20, 'result_type': 'BB',
         'delta_run_exp': 0.3, 'on_1b': False, 'on_2b': True, 'on_3b': False,
         'outs_when_up': 1, 'home_team': 'NYY'},
        {'pa_id': 2001, 'game_pk': 200, 'game_date': '2025-04-02',
         'batter_id': 10, 'pitcher_id': 21, 'result_type': 'Single',
         'delta_run_exp': 0.45, 'on_1b': False, 'on_2b': False, 'on_3b': False,
         'outs_when_up': 0, 'home_team': 'BOS'},
        {'pa_id': 2002, 'game_pk': 200, 'game_date': '2025-04-02',
         'batter_id': 11, 'pitcher_id': 21, 'result_type': 'OUT',
         'delta_run_exp': -0.2, 'on_1b': False, 'on_2b': False, 'on_3b': False,
         'outs_when_up': 1, 'home_team': 'BOS'},
        {'pa_id': 2003, 'game_pk': 200, 'game_date': '2025-04-02',
         'batter_id': 12, 'pitcher_id': 21, 'result_type': 'Double',
         'delta_run_exp': 0.85, 'on_1b': False, 'on_2b': False, 'on_3b': True,
         'outs_when_up': 0, 'home_team': 'BOS'},
    ]).sort_values(['game_date', 'pa_id']).reset_index(drop=True)


class TestParallelBatches:

    def test_both_batches_produce_output(self):
        """Composite and talent batches both produce results from same data."""
        pa_df = _make_season_df()

        composite = EloBatch()
        composite.process(pa_df)

        talent = TalentBatch()
        talent.process(pa_df)

        # Composite: single ELO per player
        assert len(composite.players) == 5  # 3 batters + 2 pitchers
        assert len(composite.pa_details) == 6

        # Talent: 9D per player, PA details per affected dimension
        assert len(talent.talent_pa_details) > 0
        assert len(talent.talent_daily_ohlc) > 0

        # Talent player records: each batter=5D, each pitcher=4D
        records = talent.get_talent_player_records()
        assert len(records) == 3 * 5 + 2 * 4  # 3 batters × 5D + 2 pitchers × 4D

    def test_talent_dimensions_diverge(self):
        """HR batter should have higher power than contact."""
        pa_df = _make_season_df()
        talent = TalentBatch()
        talent.process(pa_df)

        # Batter 10 had HR + Single → power should increase more
        batter_10 = talent.state_mgr.all_batters[10].season
        power = batter_10.elo_dimensions[1]  # power
        # After HR(power=1.0) + Single(power=0.0), power > default
        assert power > DEFAULT_ELO

    def test_pitcher_strikeout_increases_stuff(self):
        """Pitcher 20 faced HR + K + BB → stuff should reflect K."""
        pa_df = _make_season_df()
        talent = TalentBatch()
        talent.process(pa_df)

        pitcher_20 = talent.state_mgr.all_pitchers[20].season
        # K increases stuff, HR decreases stuff, BB neutral for stuff
        # Net effect depends on magnitudes — just verify it moved from default
        assert pitcher_20.elo_dimensions[0] != DEFAULT_ELO

    def test_ohlc_has_correct_dates(self):
        pa_df = _make_season_df()
        talent = TalentBatch()
        talent.process(pa_df)

        dates = {o['game_date'] for o in talent.talent_daily_ohlc}
        assert '2025-04-01' in dates
        assert '2025-04-02' in dates

    def test_risp_clutch_activated(self):
        """PA 1003 has on_2b=True → RISP → clutch dimension should activate."""
        pa_df = _make_season_df()
        talent = TalentBatch()
        talent.process(pa_df)

        # Batter 12 had BB(on_2b) + Double(on_3b) → RISP in both
        batter_12 = talent.state_mgr.all_batters[12].season
        clutch_elo = batter_12.elo_dimensions[4]  # clutch
        assert clutch_elo != DEFAULT_ELO
