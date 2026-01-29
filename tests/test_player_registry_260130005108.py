"""Tests for src/etl/player_registry.py — new player detection + MLB API registration."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.etl.player_registry import (
    detect_new_player_ids_batch,
    fetch_player_from_mlb_api,
    register_new_players,
)


class TestDetectNewPlayerIds:
    def _make_client(self, existing_ids: list[int]):
        """Mock Supabase client that returns existing player IDs."""
        client = MagicMock()
        response = MagicMock()
        response.data = [{'player_id': pid} for pid in existing_ids]
        client.table.return_value.select.return_value.in_.return_value.execute.return_value = response
        return client

    def test_all_existing_returns_empty(self):
        pa_df = pd.DataFrame({
            'batter_id': [100, 101],
            'pitcher_id': [200, 201],
        })
        client = self._make_client([100, 101, 200, 201])
        result = detect_new_player_ids_batch(pa_df, client)
        assert result == set()

    def test_new_batter_detected(self):
        pa_df = pd.DataFrame({
            'batter_id': [100, 999],
            'pitcher_id': [200, 200],
        })
        client = self._make_client([100, 200])
        result = detect_new_player_ids_batch(pa_df, client)
        assert 999 in result

    def test_new_pitcher_detected(self):
        pa_df = pd.DataFrame({
            'batter_id': [100, 100],
            'pitcher_id': [200, 888],
        })
        client = self._make_client([100, 200])
        result = detect_new_player_ids_batch(pa_df, client)
        assert 888 in result

    def test_empty_pa_returns_empty(self):
        pa_df = pd.DataFrame({'batter_id': [], 'pitcher_id': []})
        client = self._make_client([])
        result = detect_new_player_ids_batch(pa_df, client)
        assert result == set()

    def test_deduplicates_ids(self):
        """같은 선수가 여러 PA에 나와도 한 번만 반환."""
        pa_df = pd.DataFrame({
            'batter_id': [999, 999, 999],
            'pitcher_id': [200, 200, 200],
        })
        client = self._make_client([200])
        result = detect_new_player_ids_batch(pa_df, client)
        assert result == {999}


class TestFetchPlayerFromMlbApi:
    @patch('src.etl.player_registry.requests.get')
    def test_successful_fetch(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            'people': [{
                'firstName': 'Mike',
                'lastName': 'Trout',
                'fullName': 'Mike Trout',
                'currentTeam': {'abbreviation': 'LAA'},
                'primaryPosition': {'abbreviation': 'CF'},
            }]
        }
        result = fetch_player_from_mlb_api(545361)
        assert result['player_id'] == 545361
        assert result['first_name'] == 'Mike'
        assert result['last_name'] == 'Trout'
        assert result['full_name'] == 'Mike Trout'
        assert result['team'] == 'LAA'
        assert result['position'] == 'CF'

    @patch('src.etl.player_registry.requests.get')
    def test_api_returns_empty_people(self, mock_get):
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {'people': []}
        result = fetch_player_from_mlb_api(999999)
        assert result is None

    @patch('src.etl.player_registry.requests.get')
    def test_api_network_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.ConnectionError("timeout")
        result = fetch_player_from_mlb_api(545361)
        assert result is None

    @patch('src.etl.player_registry.requests.get')
    def test_api_http_error(self, mock_get):
        import requests
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("404")
        result = fetch_player_from_mlb_api(999999)
        assert result is None

    @patch('src.etl.player_registry.requests.get')
    def test_missing_optional_fields(self, mock_get):
        """currentTeam, primaryPosition 없어도 동작."""
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.json.return_value = {
            'people': [{
                'firstName': 'John',
                'lastName': 'Doe',
                'fullName': 'John Doe',
            }]
        }
        result = fetch_player_from_mlb_api(12345)
        assert result['team'] == ''
        assert result['position'] == ''


class TestRegisterNewPlayers:
    @patch('src.etl.player_registry.fetch_player_from_mlb_api')
    def test_registers_via_mlb_api(self, mock_fetch):
        mock_fetch.return_value = {
            'player_id': 999,
            'first_name': 'New',
            'last_name': 'Player',
            'full_name': 'New Player',
            'team': 'NYY',
            'position': 'SS',
        }
        client = MagicMock()
        pa_df = pd.DataFrame({'batter_id': [999], 'pitcher_id': [200]})

        count = register_new_players({999}, pa_df, client)
        assert count == 1
        client.table.return_value.upsert.assert_called_once()

    @patch('src.etl.player_registry.fetch_player_from_mlb_api')
    def test_fallback_on_api_failure(self, mock_fetch):
        """API 실패 시 fallback 레코드 생성."""
        mock_fetch.return_value = None
        client = MagicMock()
        pa_df = pd.DataFrame({'batter_id': [888], 'pitcher_id': [200]})

        count = register_new_players({888}, pa_df, client)
        assert count == 1
        # fallback record check
        upsert_call = client.table.return_value.upsert.call_args[0][0]
        assert upsert_call[0]['full_name'] == 'Player 888'

    def test_empty_ids_returns_zero(self):
        client = MagicMock()
        pa_df = pd.DataFrame({'batter_id': [], 'pitcher_id': []})
        count = register_new_players(set(), pa_df, client)
        assert count == 0

    @patch('src.etl.player_registry.fetch_player_from_mlb_api')
    def test_multiple_new_players(self, mock_fetch):
        mock_fetch.side_effect = [
            {'player_id': 111, 'first_name': 'A', 'last_name': 'B',
             'full_name': 'A B', 'team': 'BOS', 'position': 'C'},
            None,  # second player API fails
        ]
        client = MagicMock()
        pa_df = pd.DataFrame({'batter_id': [111, 222], 'pitcher_id': [200, 200]})

        count = register_new_players({111, 222}, pa_df, client)
        assert count == 2
