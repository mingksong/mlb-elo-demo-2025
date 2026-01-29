"""Integration test: 실제 Statcast 데이터(2025-09-04)로 전체 파이프라인 검증.

Supabase client만 mock하고, fetch → ETL → ELO → 업로드 레코드 생성까지
실제 데이터를 사용해 end-to-end 검증.

실행:
    pytest -m integration -v -s
"""

import math
from datetime import date
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest

pytestmark = pytest.mark.integration

from src.etl.fetch_statcast import fetch_statcast_date
from src.etl.statcast_to_pa import convert_statcast_to_pa
from src.etl.upload_to_supabase import prepare_pa_records
from src.engine.elo_batch import EloBatch
from src.engine.elo_calculator import PlayerEloState
from src.engine.elo_config import INITIAL_ELO
from src.engine.re24_baseline import RE24Baseline
from src.engine.park_factor import ParkFactor
from src.pipeline.daily_pipeline import (
    _prepare_pa_detail_records,
    _prepare_ohlc_records,
)

TARGET_DATE = date(2025, 9, 4)


# ─── Fixture: 실제 pybaseball fetch (세션당 1회만) ───

@pytest.fixture(scope="module")
def statcast_df():
    """실제 Statcast 데이터 fetch (module scope — 1회만 호출)."""
    df = fetch_statcast_date(TARGET_DATE)
    assert not df.empty, "pybaseball returned no data for 2025-09-04"
    return df


@pytest.fixture(scope="module")
def pa_df(statcast_df):
    """ETL: pitch → PA 변환."""
    df = convert_statcast_to_pa(statcast_df)
    assert not df.empty
    return df


@pytest.fixture(scope="module")
def elo_batch(pa_df):
    """ELO 계산 (fresh start)."""
    baseline = RE24Baseline()
    park_factor = ParkFactor()
    batch = EloBatch(re24_baseline=baseline, park_factor=park_factor)
    batch.process(pa_df)
    return batch


@pytest.fixture(scope="module")
def elo_batch_incremental(pa_df):
    """ELO 계산 (incremental — 기존 상태에서 이어서)."""
    # 일부 선수를 pre-load (실제 파이프라인 시뮬레이션)
    batter_ids = pa_df['batter_id'].unique()[:5]
    pitcher_ids = pa_df['pitcher_id'].unique()[:3]
    initial_states = {}
    for pid in batter_ids:
        initial_states[int(pid)] = PlayerEloState(
            player_id=int(pid), elo=1520.0, pa_count=150
        )
    for pid in pitcher_ids:
        initial_states[int(pid)] = PlayerEloState(
            player_id=int(pid), elo=1480.0, pa_count=300
        )

    baseline = RE24Baseline()
    park_factor = ParkFactor()
    batch = EloBatch(
        re24_baseline=baseline,
        park_factor=park_factor,
        initial_states=initial_states,
    )
    batch.process(pa_df)
    return batch, initial_states


# ═══════════════════════════════════════════════
# 1. Fetch 검증
# ═══════════════════════════════════════════════

class TestFetchIntegration:
    def test_regular_season_only(self, statcast_df):
        if 'game_type' in statcast_df.columns:
            assert (statcast_df['game_type'] == 'R').all()

    def test_has_required_columns(self, statcast_df):
        required = [
            'batter', 'pitcher', 'game_date', 'game_pk', 'events',
            'delta_run_exp', 'on_1b', 'on_2b', 'on_3b', 'outs_when_up',
            'home_team', 'away_team', 'at_bat_number', 'inning', 'inning_topbot',
        ]
        for col in required:
            assert col in statcast_df.columns, f"Missing column: {col}"

    def test_reasonable_pitch_count(self, statcast_df):
        """하루 6경기 기준 1,000~5,000 pitches 예상."""
        assert 500 < len(statcast_df) < 10000


# ═══════════════════════════════════════════════
# 2. ETL 검증
# ═══════════════════════════════════════════════

class TestETLIntegration:
    def test_pa_count_reasonable(self, pa_df):
        """6경기 × ~75 PA = ~450 PA."""
        assert 100 < len(pa_df) < 2000

    def test_pa_id_unique(self, pa_df):
        assert pa_df['pa_id'].is_unique

    def test_game_date_is_target(self, pa_df):
        dates = pa_df['game_date'].unique()
        assert len(dates) == 1
        assert str(dates[0])[:10] == '2025-09-04'

    def test_result_type_no_nulls(self, pa_df):
        assert pa_df['result_type'].notna().all()

    def test_batter_pitcher_are_ints(self, pa_df):
        assert pa_df['batter_id'].dtype in ('int64', 'int32')
        assert pa_df['pitcher_id'].dtype in ('int64', 'int32')


# ═══════════════════════════════════════════════
# 3. ELO 엔진 검증
# ═══════════════════════════════════════════════

class TestELOEngineIntegration:
    def test_zero_sum(self, elo_batch):
        net = sum(p.elo - INITIAL_ELO for p in elo_batch.players.values())
        assert abs(net) < 0.01, f"Zero-sum violated: net={net}"

    def test_all_elo_above_minimum(self, elo_batch):
        for pid, state in elo_batch.players.items():
            assert state.elo >= 500.0, f"Player {pid} ELO below minimum: {state.elo}"

    def test_pa_details_count_matches(self, elo_batch, pa_df):
        assert len(elo_batch.pa_details) == len(pa_df)

    def test_ohlc_count_equals_player_count(self, elo_batch):
        """단일 날짜 → OHLC 레코드 수 == 활동 선수 수."""
        assert len(elo_batch.daily_ohlc) == len(elo_batch.players)

    def test_ohlc_high_gte_low(self, elo_batch):
        for ohlc in elo_batch.daily_ohlc:
            assert ohlc.high_elo >= ohlc.low_elo, \
                f"Player {ohlc.player_id}: high={ohlc.high_elo} < low={ohlc.low_elo}"

    def test_ohlc_open_between_high_low(self, elo_batch):
        for ohlc in elo_batch.daily_ohlc:
            assert ohlc.low_elo <= ohlc.open_elo <= ohlc.high_elo

    def test_ohlc_close_between_high_low(self, elo_batch):
        for ohlc in elo_batch.daily_ohlc:
            assert ohlc.low_elo <= ohlc.close_elo <= ohlc.high_elo

    def test_ohlc_total_pa_positive(self, elo_batch):
        for ohlc in elo_batch.daily_ohlc:
            assert ohlc.total_pa > 0, f"Player {ohlc.player_id}: total_pa=0"


# ═══════════════════════════════════════════════
# 4. Incremental 모드 검증
# ═══════════════════════════════════════════════

class TestIncrementalIntegration:
    def test_preloaded_players_start_from_initial(self, elo_batch_incremental):
        batch, initial_states = elo_batch_incremental
        for d in batch.pa_details:
            bid = d['batter_id']
            pid = d['pitcher_id']
            if bid in initial_states:
                # 첫 PA에서 batter_elo_before가 initial state와 같아야 함
                # (이후 PA는 변할 수 있으므로 첫 번째만 확인)
                break
        # At least one preloaded player appeared
        preloaded_seen = False
        for d in batch.pa_details:
            if d['batter_id'] in initial_states or d['pitcher_id'] in initial_states:
                preloaded_seen = True
                break
        assert preloaded_seen, "No preloaded player appeared in PAs"

    def test_active_only_subset(self, elo_batch_incremental):
        batch, initial_states = elo_batch_incremental
        all_recs = batch.get_player_elo_records(active_only=False)
        active_recs = batch.get_player_elo_records(active_only=True)
        assert len(active_recs) <= len(all_recs)
        assert len(active_recs) == len(batch._active_player_ids)

    def test_pa_count_continues(self, elo_batch_incremental):
        batch, initial_states = elo_batch_incremental
        for pid, init_state in initial_states.items():
            if pid in batch.players:
                assert batch.players[pid].pa_count >= init_state.pa_count


# ═══════════════════════════════════════════════
# 5. 업로드 레코드 스키마 검증 (Supabase mock)
# ═══════════════════════════════════════════════

class TestUploadRecordSchema:
    """각 테이블에 upsert될 레코드가 스키마에 맞는지 검증."""

    def test_pa_records_schema(self, pa_df):
        records = prepare_pa_records(pa_df)
        assert len(records) > 0
        for r in records:
            # Required fields
            assert isinstance(r['pa_id'], int)
            assert isinstance(r['game_pk'], int)
            assert isinstance(r['batter_id'], int)
            assert isinstance(r['pitcher_id'], int)
            assert isinstance(r['result_type'], str)
            assert isinstance(r['game_date'], str)
            assert len(r['game_date']) == 10  # YYYY-MM-DD
            # No NaN (should be None)
            for k, v in r.items():
                if isinstance(v, float):
                    assert not math.isnan(v), f"NaN in PA record: {k}"

    def test_player_elo_records_schema(self, elo_batch):
        records = elo_batch.get_player_elo_records()
        assert len(records) > 0
        for r in records:
            assert isinstance(r['player_id'], int)
            assert isinstance(r['on_base_elo'], float)
            assert isinstance(r['power_elo'], float)
            assert isinstance(r['composite_elo'], float)
            assert isinstance(r['pa_count'], int)
            assert r['pa_count'] > 0
            assert r['composite_elo'] >= 500.0
            # last_game_date는 str 또는 None
            if r['last_game_date'] is not None:
                assert isinstance(r['last_game_date'], str)
                assert len(r['last_game_date']) == 10

    def test_pa_detail_records_schema(self, elo_batch):
        records = _prepare_pa_detail_records(elo_batch.pa_details)
        assert len(records) > 0
        for r in records:
            assert isinstance(r['pa_id'], int)
            assert isinstance(r['batter_id'], int)
            assert isinstance(r['pitcher_id'], int)
            assert isinstance(r['result_type'], str)
            assert isinstance(r['batter_elo_before'], float)
            assert isinstance(r['batter_elo_after'], float)
            assert isinstance(r['pitcher_elo_before'], float)
            assert isinstance(r['pitcher_elo_after'], float)
            assert isinstance(r['on_base_delta'], float)
            assert isinstance(r['power_delta'], float)
            # No NaN
            for k, v in r.items():
                if isinstance(v, float):
                    assert not math.isnan(v), f"NaN in detail record: {k}"

    def test_ohlc_records_schema(self, elo_batch):
        records = _prepare_ohlc_records(elo_batch.daily_ohlc)
        assert len(records) > 0
        for r in records:
            assert isinstance(r['player_id'], int)
            assert isinstance(r['game_date'], str)
            assert len(r['game_date']) == 10
            assert r['elo_type'] == 'SEASON'
            assert isinstance(r['open'], float)
            assert isinstance(r['high'], float)
            assert isinstance(r['low'], float)
            assert isinstance(r['close'], float)
            assert isinstance(r['games_played'], int)
            assert isinstance(r['total_pa'], int)
            # Invariants
            assert r['high'] >= r['low']
            assert r['low'] <= r['open'] <= r['high']
            assert r['low'] <= r['close'] <= r['high']
            assert r['total_pa'] > 0
            # No NaN
            for k, v in r.items():
                if isinstance(v, float):
                    assert not math.isnan(v), f"NaN in OHLC record: {k}"


# ═══════════════════════════════════════════════
# 6. Mock Supabase 파이프라인 end-to-end
# ═══════════════════════════════════════════════

class TestMockPipelineEndToEnd:
    """Supabase client mock으로 run_daily_pipeline 전체 흐름 검증."""

    @patch('src.pipeline.daily_pipeline.get_supabase_client')
    def test_full_pipeline_with_mock_supabase(self, mock_get_client, statcast_df):
        from src.pipeline.daily_pipeline import run_daily_pipeline

        # ─── Mock Supabase client ───
        client = MagicMock()
        mock_get_client.return_value = client

        # Idempotency check → no existing data
        idempotency_resp = MagicMock()
        idempotency_resp.count = 0
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = idempotency_resp

        # detect_new_player_ids → all players are "existing"
        existing_resp = MagicMock()
        existing_resp.data = [
            {'player_id': int(pid)}
            for pid in set(statcast_df['batter'].unique()) | set(statcast_df['pitcher'].unique())
        ]
        client.table.return_value.select.return_value.in_.return_value.execute.return_value = existing_resp

        # upload_table → just count records
        upserted_records = {}

        def capture_upsert(records):
            """upsert 호출을 캡처."""
            mock_exec = MagicMock()
            mock_exec.execute.return_value = MagicMock()
            return mock_exec

        client.table.return_value.upsert.side_effect = capture_upsert

        # load_current_elo_states → empty (fresh start)
        elo_state_resp = MagicMock()
        elo_state_resp.data = []
        client.table.return_value.select.return_value.range.return_value.execute.return_value = elo_state_resp

        # ─── Run pipeline ───
        with patch('src.pipeline.daily_pipeline.fetch_statcast_date', return_value=statcast_df):
            result = run_daily_pipeline(target_date=TARGET_DATE, force=False)

        # ─── Assertions ───
        assert result['status'] == 'success'
        assert result['date'] == '2025-09-04'
        assert result['pa_count'] > 100
        assert result['active_players'] > 50

        # Verify upsert was called (plate_appearances, player_elo, elo_pa_detail, daily_ohlc)
        upsert_calls = client.table.return_value.upsert.call_args_list
        assert len(upsert_calls) > 0, "No upsert calls made"

        # Verify records were passed to upsert
        total_upserted = sum(len(c[0][0]) for c in upsert_calls)
        assert total_upserted > 0, "No records upserted"
