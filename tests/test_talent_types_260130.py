"""Multi-ELO Types Tests — BatterTalentState + PitcherTalentState."""
import numpy as np
import pytest

from src.engine.multi_elo_types import (
    BatterTalentState,
    PitcherTalentState,
    BATTER_DIM_COUNT,
    PITCHER_DIM_COUNT,
    BATTER_DIM_NAMES,
    PITCHER_DIM_NAMES,
    DEFAULT_ELO,
    ELO_MIN,
    ELO_MAX,
)


class TestBatterTalentState:

    def test_default_init(self):
        s = BatterTalentState(player_id=100)
        assert s.player_id == 100
        assert len(s.elo_dimensions) == BATTER_DIM_COUNT
        assert all(e == DEFAULT_ELO for e in s.elo_dimensions)
        assert s.pa_count == 0

    def test_composite_elo_default(self):
        s = BatterTalentState(player_id=100)
        assert s.composite_elo == pytest.approx(1500.0)

    def test_apply_deltas(self):
        s = BatterTalentState(player_id=100)
        deltas = np.array([10.0, -5.0, 3.0, 0.0, -2.0])
        s.apply_deltas(deltas)
        assert s.elo_dimensions[0] == pytest.approx(1510.0)
        assert s.elo_dimensions[1] == pytest.approx(1495.0)

    def test_clamp_elo_min(self):
        s = BatterTalentState(player_id=100)
        s.apply_deltas(np.array([-1500.0, 0, 0, 0, 0]))
        assert s.elo_dimensions[0] == ELO_MIN

    def test_clamp_elo_max(self):
        s = BatterTalentState(player_id=100)
        s.apply_deltas(np.array([2000.0, 0, 0, 0, 0]))
        assert s.elo_dimensions[0] == ELO_MAX

    def test_dimension_indices(self):
        assert BatterTalentState.CONTACT == 0
        assert BatterTalentState.POWER == 1
        assert BatterTalentState.DISCIPLINE == 2
        assert BatterTalentState.SPEED == 3
        assert BatterTalentState.CLUTCH == 4

    def test_increment_pa(self):
        s = BatterTalentState(player_id=100)
        s.increment_pa()
        s.increment_pa()
        assert s.pa_count == 2


class TestPitcherTalentState:

    def test_default_init(self):
        s = PitcherTalentState(player_id=200)
        assert s.player_id == 200
        assert len(s.elo_dimensions) == PITCHER_DIM_COUNT
        assert s.bfp_count == 0

    def test_composite_elo_starter(self):
        s = PitcherTalentState(player_id=200, role="starter")
        assert s.composite_elo == pytest.approx(1500.0)

    def test_composite_elo_role_weights(self):
        """Different roles produce different composite ELOs for non-uniform dimensions."""
        s = PitcherTalentState(player_id=200, role="starter")
        # Set stuff=1600, command=1400 (others=1500)
        s.elo_dimensions = np.array([1600.0, 1500.0, 1400.0, 1500.0])
        # starter: stuff=0.25, bip_supp=0.20, command=0.40, clutch=0.15
        expected = 1600*0.25 + 1500*0.20 + 1400*0.40 + 1500*0.15
        assert s.composite_elo == pytest.approx(expected)

    def test_apply_deltas(self):
        s = PitcherTalentState(player_id=200)
        deltas = np.array([5.0, -3.0, 2.0, 1.0])
        s.apply_deltas(deltas)
        assert s.elo_dimensions[0] == pytest.approx(1505.0)

    def test_dimension_indices(self):
        assert PitcherTalentState.STUFF == 0
        assert PitcherTalentState.BIP_SUPPRESSION == 1
        assert PitcherTalentState.COMMAND == 2
        assert PitcherTalentState.CLUTCH == 3

    def test_increment_bfp(self):
        s = PitcherTalentState(player_id=200)
        s.increment_bfp()
        assert s.bfp_count == 1


class TestDimensionConstants:

    def test_batter_dim_count(self):
        assert BATTER_DIM_COUNT == 5

    def test_pitcher_dim_count(self):
        assert PITCHER_DIM_COUNT == 4

    def test_batter_dim_names(self):
        assert BATTER_DIM_NAMES == ["contact", "power", "discipline", "speed", "clutch"]

    def test_pitcher_dim_names(self):
        assert PITCHER_DIM_NAMES == ["stuff", "bip_suppression", "command", "clutch"]

    def test_elo_bounds(self):
        assert ELO_MIN == 500.0
        assert ELO_MAX == 3000.0
        assert DEFAULT_ELO == 1500.0
