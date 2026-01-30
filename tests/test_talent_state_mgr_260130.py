"""TalentStateManager Tests — Season/Career dual tracking."""
import numpy as np
import pytest

from src.engine.talent_state_manager import (
    TalentStateManager,
    DualBatterState,
    DualPitcherState,
)
from src.engine.multi_elo_types import DEFAULT_ELO


class TestDualBatterState:

    def test_init(self):
        s = DualBatterState(player_id=100)
        assert s.season.player_id == 100
        assert s.career.player_id == 100
        assert s.season.composite_elo == pytest.approx(DEFAULT_ELO)
        assert s.career.composite_elo == pytest.approx(DEFAULT_ELO)

    def test_apply_deltas_updates_both(self):
        s = DualBatterState(player_id=100)
        deltas = np.array([10.0, -5.0, 3.0, 0.0, -2.0])
        s.apply_deltas(deltas)
        assert s.season.elo_dimensions[0] == pytest.approx(1510.0)
        assert s.career.elo_dimensions[0] == pytest.approx(1510.0)

    def test_reset_season(self):
        s = DualBatterState(player_id=100)
        deltas = np.array([50.0, 0, 0, 0, 0])
        s.apply_deltas(deltas)
        s.reset_season()
        # Season resets, career preserves
        assert s.season.elo_dimensions[0] == pytest.approx(DEFAULT_ELO)
        assert s.career.elo_dimensions[0] == pytest.approx(1550.0)


class TestTalentStateManager:

    def test_get_or_create_batter(self):
        mgr = TalentStateManager()
        b = mgr.get_or_create_batter(100)
        assert b.player_id == 100
        # Same object on second call
        assert mgr.get_or_create_batter(100) is b

    def test_get_or_create_pitcher(self):
        mgr = TalentStateManager()
        p = mgr.get_or_create_pitcher(200)
        assert p.player_id == 200
        assert mgr.get_or_create_pitcher(200) is p

    def test_twp_player_separate_states(self):
        """TWP player has both batter and pitcher states."""
        mgr = TalentStateManager()
        b = mgr.get_or_create_batter(660271)  # Ohtani
        p = mgr.get_or_create_pitcher(660271)
        assert b.player_id == 660271
        assert p.player_id == 660271
        # Independent states
        b.apply_deltas(np.array([20.0, 0, 0, 0, 0]))
        assert b.season.elo_dimensions[0] == pytest.approx(1520.0)
        assert p.season.elo_dimensions[0] == pytest.approx(1500.0)

    def test_reset_season_all(self):
        mgr = TalentStateManager()
        b = mgr.get_or_create_batter(100)
        p = mgr.get_or_create_pitcher(200)
        b.apply_deltas(np.array([30.0, 0, 0, 0, 0]))
        p.apply_deltas(np.array([20.0, 0, 0, 0]))
        mgr.reset_season(2026)
        assert mgr.current_season == 2026
        assert b.season.elo_dimensions[0] == pytest.approx(DEFAULT_ELO)
        assert b.career.elo_dimensions[0] == pytest.approx(1530.0)
        assert p.season.elo_dimensions[0] == pytest.approx(DEFAULT_ELO)
        assert p.career.elo_dimensions[0] == pytest.approx(1520.0)

    def test_all_batters_pitchers(self):
        mgr = TalentStateManager()
        mgr.get_or_create_batter(100)
        mgr.get_or_create_batter(101)
        mgr.get_or_create_pitcher(200)
        assert len(mgr.all_batters) == 2
        assert len(mgr.all_pitchers) == 1
