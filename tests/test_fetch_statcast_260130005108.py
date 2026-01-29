"""Tests for src/etl/fetch_statcast.py — pybaseball wrapper."""

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from src.etl.fetch_statcast import (
    fetch_statcast_date,
    fetch_statcast_range,
    get_yesterday,
)


class TestGetYesterday:
    def test_returns_date(self):
        result = get_yesterday()
        assert isinstance(result, date)

    def test_is_yesterday(self):
        result = get_yesterday()
        assert result == date.today() - timedelta(days=1)


class TestFetchStatcastDate:
    @patch('src.etl.fetch_statcast.statcast')
    def test_calls_pybaseball_with_correct_date(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame()
        fetch_statcast_date(date(2026, 4, 15))
        mock_statcast.assert_called_once_with(
            start_dt='2026-04-15', end_dt='2026-04-15'
        )

    @patch('src.etl.fetch_statcast.statcast')
    def test_empty_result_returns_empty_df(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame()
        result = fetch_statcast_date(date(2026, 1, 15))
        assert result.empty

    @patch('src.etl.fetch_statcast.statcast')
    def test_none_result_returns_empty_df(self, mock_statcast):
        mock_statcast.return_value = None
        result = fetch_statcast_date(date(2026, 1, 15))
        assert result.empty

    @patch('src.etl.fetch_statcast.statcast')
    def test_filters_regular_season_only(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame({
            'game_type': ['R', 'R', 'S', 'E'],
            'batter': [100, 101, 102, 103],
            'pitcher': [200, 201, 202, 203],
        })
        result = fetch_statcast_date(date(2026, 4, 15))
        assert len(result) == 2
        assert (result['game_type'] == 'R').all()

    @patch('src.etl.fetch_statcast.statcast')
    def test_all_non_regular_season_returns_empty(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame({
            'game_type': ['S', 'E', 'F'],
            'batter': [100, 101, 102],
        })
        result = fetch_statcast_date(date(2026, 3, 10))
        assert result.empty

    @patch('src.etl.fetch_statcast.statcast')
    def test_no_game_type_column_returns_all(self, mock_statcast):
        """game_type 컬럼이 없으면 모든 데이터 반환."""
        mock_statcast.return_value = pd.DataFrame({
            'batter': [100, 101, 102],
            'pitcher': [200, 201, 202],
        })
        result = fetch_statcast_date(date(2026, 4, 15))
        assert len(result) == 3

    @patch('src.etl.fetch_statcast.statcast')
    def test_reset_index(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame({
            'game_type': ['S', 'R', 'R'],
            'batter': [100, 101, 102],
        })
        result = fetch_statcast_date(date(2026, 4, 15))
        assert list(result.index) == [0, 1]


class TestFetchStatcastRange:
    @patch('src.etl.fetch_statcast.statcast')
    def test_calls_pybaseball_with_range(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame()
        fetch_statcast_range(date(2026, 4, 1), date(2026, 4, 3))
        mock_statcast.assert_called_once_with(
            start_dt='2026-04-01', end_dt='2026-04-03'
        )

    @patch('src.etl.fetch_statcast.statcast')
    def test_filters_regular_season(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame({
            'game_type': ['R', 'S', 'R', 'F', 'R'],
            'batter': [100, 101, 102, 103, 104],
        })
        result = fetch_statcast_range(date(2026, 4, 1), date(2026, 4, 3))
        assert len(result) == 3
        assert (result['game_type'] == 'R').all()

    @patch('src.etl.fetch_statcast.statcast')
    def test_empty_range_returns_empty_df(self, mock_statcast):
        mock_statcast.return_value = pd.DataFrame()
        result = fetch_statcast_range(date(2026, 1, 1), date(2026, 1, 3))
        assert result.empty

    @patch('src.etl.fetch_statcast.statcast')
    def test_none_result_returns_empty_df(self, mock_statcast):
        mock_statcast.return_value = None
        result = fetch_statcast_range(date(2026, 1, 1), date(2026, 1, 3))
        assert result.empty
