"""TalentBatch Tests — Full-season 9D processing."""
import pandas as pd
import pytest
import numpy as np

from src.engine.talent_batch import TalentBatch
from src.engine.multi_elo_types import (
    BatterTalentState, PitcherTalentState, DEFAULT_ELO,
    BATTER_DIM_NAMES, PITCHER_DIM_NAMES,
)


def _make_pa_df(rows):
    return pd.DataFrame(rows).sort_values(['game_date', 'pa_id']).reset_index(drop=True)


class TestTalentBatchBasic:

    def test_single_pa(self):
        pa_df = _make_pa_df([{
            'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
            'batter_id': 10, 'pitcher_id': 20,
            'result_type': 'HR',
            'on_1b': False, 'on_2b': False, 'on_3b': False,
        }])
        batch = TalentBatch()
        batch.process(pa_df)

        assert 10 in batch.state_mgr.all_batters
        assert 20 in batch.state_mgr.all_pitchers
        batter = batch.state_mgr.all_batters[10]
        assert batter.season.pa_count == 1
        # HR should increase power
        assert batter.season.elo_dimensions[BatterTalentState.POWER] > DEFAULT_ELO

    def test_multiple_pas(self):
        pa_df = _make_pa_df([
            {'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
             'batter_id': 10, 'pitcher_id': 20, 'result_type': 'HR',
             'on_1b': False, 'on_2b': False, 'on_3b': False},
            {'pa_id': 1002, 'game_pk': 100, 'game_date': '2025-04-01',
             'batter_id': 11, 'pitcher_id': 20, 'result_type': 'StrikeOut',
             'on_1b': False, 'on_2b': False, 'on_3b': False},
        ])
        batch = TalentBatch()
        batch.process(pa_df)

        assert batch.state_mgr.all_pitchers[20].season.bfp_count == 2

    def test_twp_player(self):
        """Same player_id as batter and pitcher → separate states."""
        pa_df = _make_pa_df([
            {'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
             'batter_id': 660271, 'pitcher_id': 20, 'result_type': 'HR',
             'on_1b': False, 'on_2b': False, 'on_3b': False},
            {'pa_id': 1002, 'game_pk': 100, 'game_date': '2025-04-01',
             'batter_id': 30, 'pitcher_id': 660271, 'result_type': 'StrikeOut',
             'on_1b': False, 'on_2b': False, 'on_3b': False},
        ])
        batch = TalentBatch()
        batch.process(pa_df)

        # Ohtani as batter
        assert 660271 in batch.state_mgr.all_batters
        assert batch.state_mgr.all_batters[660271].season.pa_count == 1
        # Ohtani as pitcher
        assert 660271 in batch.state_mgr.all_pitchers
        assert batch.state_mgr.all_pitchers[660271].season.bfp_count == 1

    def test_risp_clutch(self):
        """on_2b=True → RISP → clutch multiplier activated."""
        pa_df_risp = _make_pa_df([{
            'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
            'batter_id': 10, 'pitcher_id': 20, 'result_type': 'Single',
            'on_1b': False, 'on_2b': True, 'on_3b': False,
        }])
        pa_df_no_risp = _make_pa_df([{
            'pa_id': 1002, 'game_pk': 100, 'game_date': '2025-04-01',
            'batter_id': 11, 'pitcher_id': 21, 'result_type': 'Single',
            'on_1b': False, 'on_2b': False, 'on_3b': False,
        }])

        batch_risp = TalentBatch()
        batch_risp.process(pa_df_risp)
        batch_no = TalentBatch()
        batch_no.process(pa_df_no_risp)

        clutch_risp = abs(
            batch_risp.state_mgr.all_batters[10].season.elo_dimensions[BatterTalentState.CLUTCH]
            - DEFAULT_ELO
        )
        clutch_no = abs(
            batch_no.state_mgr.all_batters[11].season.elo_dimensions[BatterTalentState.CLUTCH]
            - DEFAULT_ELO
        )
        assert clutch_risp >= clutch_no


class TestTalentBatchOutput:

    def test_pa_details_generated(self):
        pa_df = _make_pa_df([{
            'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
            'batter_id': 10, 'pitcher_id': 20, 'result_type': 'HR',
            'on_1b': False, 'on_2b': False, 'on_3b': False,
        }])
        batch = TalentBatch()
        batch.process(pa_df)

        assert len(batch.talent_pa_details) > 0
        # Each PA generates records for each affected dimension
        detail = batch.talent_pa_details[0]
        assert 'pa_id' in detail
        assert 'player_id' in detail
        assert 'talent_type' in detail
        assert 'elo_before' in detail
        assert 'elo_after' in detail

    def test_ohlc_generated(self):
        pa_df = _make_pa_df([{
            'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
            'batter_id': 10, 'pitcher_id': 20, 'result_type': 'HR',
            'on_1b': False, 'on_2b': False, 'on_3b': False,
        }])
        batch = TalentBatch()
        batch.process(pa_df)

        assert len(batch.talent_daily_ohlc) > 0
        ohlc = batch.talent_daily_ohlc[0]
        assert 'player_id' in ohlc
        assert 'talent_type' in ohlc
        assert 'open' in ohlc
        assert 'close' in ohlc

    def test_player_current_records(self):
        pa_df = _make_pa_df([{
            'pa_id': 1001, 'game_pk': 100, 'game_date': '2025-04-01',
            'batter_id': 10, 'pitcher_id': 20, 'result_type': 'HR',
            'on_1b': False, 'on_2b': False, 'on_3b': False,
        }])
        batch = TalentBatch()
        batch.process(pa_df)

        records = batch.get_talent_player_records()
        # Should have records for batter (5D) and pitcher (4D)
        assert len(records) == 9  # 5 batter + 4 pitcher dims
        types = {r['talent_type'] for r in records}
        assert 'contact' in types
        assert 'stuff' in types
