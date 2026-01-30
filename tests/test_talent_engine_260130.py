"""Multi-ELO Engine Tests — 9D talent calculation."""
import numpy as np
import pytest

from src.engine.multi_elo_engine import MultiEloEngine
from src.engine.multi_elo_config import MultiEloConfig
from src.engine.multi_elo_types import (
    BatterTalentState, PitcherTalentState,
    DEFAULT_ELO, BATTER_DIM_NAMES, PITCHER_DIM_NAMES,
    MIN_RELIABILITY,
)


@pytest.fixture
def engine():
    return MultiEloEngine()


@pytest.fixture
def batter():
    return BatterTalentState(player_id=100)


@pytest.fixture
def pitcher():
    return PitcherTalentState(player_id=200)


class TestExpectedScore:

    def test_equal_elo_returns_half(self, engine):
        assert engine.calculate_expected_score(1500, 1500) == pytest.approx(0.5)

    def test_higher_elo_favored(self, engine):
        assert engine.calculate_expected_score(1600, 1500) > 0.5

    def test_lower_elo_unfavored(self, engine):
        assert engine.calculate_expected_score(1400, 1500) < 0.5

    def test_symmetric(self, engine):
        e1 = engine.calculate_expected_score(1600, 1500)
        e2 = engine.calculate_expected_score(1500, 1600)
        assert e1 + e2 == pytest.approx(1.0)


class TestReliability:

    def test_zero_events(self, engine):
        assert engine.calculate_reliability(0, "contact") == pytest.approx(MIN_RELIABILITY)

    def test_full_threshold(self, engine):
        """contact threshold=400 -> event_count=400 -> reliability=1.0."""
        assert engine.calculate_reliability(400, "contact") == pytest.approx(1.0)

    def test_half_threshold(self, engine):
        """contact threshold=400 -> 200 events -> 0.3 + 0.7*(200/400) = 0.65."""
        assert engine.calculate_reliability(200, "contact") == pytest.approx(0.65)

    def test_speed_low_threshold(self, engine):
        """speed threshold=50 -> 50 events -> 1.0."""
        assert engine.calculate_reliability(50, "speed") == pytest.approx(1.0)


class TestClutchMultiplier:

    def test_low_leverage(self, engine):
        assert engine.get_clutch_multiplier(0.5) == 0.0

    def test_exactly_one(self, engine):
        assert engine.get_clutch_multiplier(1.0) == 0.0

    def test_high_leverage(self, engine):
        assert engine.get_clutch_multiplier(4.0) == pytest.approx(2.0)

    def test_moderate_leverage(self, engine):
        assert engine.get_clutch_multiplier(3.0) == pytest.approx(1.5)


class TestProcessPA:

    def test_hr_increases_power(self, engine, batter, pitcher):
        """HR -> power weight=1.0 -> power ELO should increase."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="HR"
        )
        assert result.batter_deltas[BatterTalentState.POWER] > 0

    def test_hr_increases_contact_slightly(self, engine, batter, pitcher):
        """HR -> contact weight=0.2 -> small positive contact delta."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="HR"
        )
        contact_delta = result.batter_deltas[BatterTalentState.CONTACT]
        power_delta = result.batter_deltas[BatterTalentState.POWER]
        assert contact_delta > 0
        assert contact_delta < power_delta  # Contact signal weaker

    def test_strikeout_decreases_contact(self, engine, batter, pitcher):
        """StrikeOut -> contact weight=-1.0 -> contact ELO decreases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="StrikeOut"
        )
        assert result.batter_deltas[BatterTalentState.CONTACT] < 0

    def test_strikeout_discipline_zero(self, engine, batter, pitcher):
        """V2: StrikeOut discipline=0.0 (K removed from discipline)."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="StrikeOut"
        )
        assert result.batter_deltas[BatterTalentState.DISCIPLINE] == 0.0

    def test_bb_increases_discipline(self, engine, batter, pitcher):
        """BB -> discipline weight=1.0 -> discipline increases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="BB"
        )
        assert result.batter_deltas[BatterTalentState.DISCIPLINE] > 0

    def test_pitcher_strikeout_stuff(self, engine, batter, pitcher):
        """StrikeOut -> pitcher stuff=1.0 -> stuff ELO increases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="StrikeOut"
        )
        assert result.pitcher_deltas[PitcherTalentState.STUFF] > 0

    def test_pitcher_bb_command(self, engine, batter, pitcher):
        """BB -> pitcher command=-1.0 -> command ELO decreases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="BB"
        )
        assert result.pitcher_deltas[PitcherTalentState.COMMAND] < 0

    def test_pitcher_hr_stuff_decreases(self, engine, batter, pitcher):
        """HR -> pitcher stuff=-0.8 -> stuff ELO decreases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="HR"
        )
        assert result.pitcher_deltas[PitcherTalentState.STUFF] < 0

    def test_error_minimal_impact(self, engine, batter, pitcher):
        """E -> batter contact=0.1 (small), pitcher bip_supp=-0.1 (small)."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="E"
        )
        # Very small deltas due to low weights
        assert abs(result.batter_deltas[BatterTalentState.CONTACT]) < 5.0

    def test_state_updated(self, engine, batter, pitcher):
        """Player ELO states actually change after PA."""
        before_bat = batter.elo_dimensions.copy()
        engine.process_plate_appearance(batter, pitcher, result_type="HR")
        assert not np.array_equal(batter.elo_dimensions, before_bat)

    def test_pa_count_incremented(self, engine, batter, pitcher):
        engine.process_plate_appearance(batter, pitcher, result_type="Single")
        assert batter.pa_count == 1
        assert pitcher.bfp_count == 1

    def test_event_counts_updated(self, engine, batter, pitcher):
        """Non-zero deltas increment event counts for affected dimensions."""
        engine.process_plate_appearance(batter, pitcher, result_type="HR")
        # HR affects contact(0.2), power(1.0), clutch
        assert batter.event_counts[BatterTalentState.POWER] == 1
        assert batter.event_counts[BatterTalentState.CONTACT] == 1
        # HR does NOT affect discipline or speed
        assert batter.event_counts[BatterTalentState.DISCIPLINE] == 0
        assert batter.event_counts[BatterTalentState.SPEED] == 0

    def test_clutch_risp(self, engine, batter, pitcher):
        """RISP=True -> clutch delta is amplified."""
        result_no_risp = engine.process_plate_appearance(
            BatterTalentState(player_id=1),
            PitcherTalentState(player_id=2),
            result_type="Single",
            is_risp=False,
        )
        result_risp = engine.process_plate_appearance(
            BatterTalentState(player_id=3),
            PitcherTalentState(player_id=4),
            result_type="Single",
            is_risp=True,
        )
        # RISP activates clutch multiplier
        assert abs(result_risp.batter_deltas[BatterTalentState.CLUTCH]) >= \
               abs(result_no_risp.batter_deltas[BatterTalentState.CLUTCH])


class TestMatchupEffect:

    def test_strong_batter_vs_weak_pitcher(self, engine):
        """High-contact batter vs low-stuff pitcher -> lower expected -> larger delta."""
        strong = BatterTalentState(player_id=1)
        strong.elo_dimensions[BatterTalentState.CONTACT] = 1700.0
        weak_p = PitcherTalentState(player_id=2)
        weak_p.elo_dimensions[PitcherTalentState.STUFF] = 1300.0

        avg_b = BatterTalentState(player_id=3)
        avg_p = PitcherTalentState(player_id=4)

        r1 = engine.process_plate_appearance(strong, weak_p, result_type="Single")
        r2 = engine.process_plate_appearance(avg_b, avg_p, result_type="Single")

        # Strong batter expected to get hit -> lower delta (already expected)
        assert r1.batter_deltas[BatterTalentState.CONTACT] < \
               r2.batter_deltas[BatterTalentState.CONTACT]

    def test_speed_has_no_matchup(self, engine):
        """Speed dimension uses 0.5 baseline (no pitcher matchup)."""
        b = BatterTalentState(player_id=1)
        p = PitcherTalentState(player_id=2)
        # Even if pitcher is very strong, speed delta should be independent
        p.elo_dimensions[:] = 1800.0  # Very strong pitcher
        result = engine.process_plate_appearance(b, p, result_type="Triple")
        # Speed delta should be non-zero (Triple has speed=0.8)
        assert result.batter_deltas[BatterTalentState.SPEED] != 0.0
