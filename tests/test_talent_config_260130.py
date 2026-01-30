"""Multi-ELO Config Tests."""
import pytest
from src.engine.multi_elo_config import MultiEloConfig


class TestMultiEloConfig:
    """YAML 기반 Multi-ELO 설정 로더 테스트."""

    @pytest.fixture
    def config(self):
        return MultiEloConfig()

    def test_version(self, config):
        assert config.version == "2.0"

    def test_batter_dimensions_count(self, config):
        assert len(config.batter_dimensions) == 5

    def test_pitcher_dimensions_count(self, config):
        assert len(config.pitcher_dimensions) == 4

    def test_batter_dimension_names(self, config):
        names = [d["name"] for d in config.batter_dimensions]
        assert names == ["contact", "power", "discipline", "speed", "clutch"]

    def test_pitcher_dimension_names(self, config):
        names = [d["name"] for d in config.pitcher_dimensions]
        assert names == ["stuff", "bip_suppression", "command", "clutch"]

    def test_batter_k_factor_contact(self, config):
        assert config.get_batter_k_factor("contact") == 12.0

    def test_batter_k_factor_power(self, config):
        assert config.get_batter_k_factor("power") == 14.4

    def test_batter_k_factor_speed(self, config):
        assert config.get_batter_k_factor("speed") == 36.0

    def test_pitcher_k_factor_stuff(self, config):
        assert config.get_pitcher_k_factor("stuff") == 12.0

    def test_pitcher_k_factor_bip_suppression(self, config):
        """BIP Suppression has low K (BABIP noise)."""
        assert config.get_pitcher_k_factor("bip_suppression") == 4.0

    def test_event_weights_hr(self, config):
        w = config.get_event_weights("HR")
        assert w["power"] == 1.0
        assert w["contact"] == 0.2
        assert w["discipline"] == 0.0

    def test_event_weights_strikeout(self, config):
        w = config.get_event_weights("StrikeOut")
        assert w["contact"] == -1.0
        assert w["discipline"] == 0.0  # V2: K removed from discipline

    def test_event_weights_bb(self, config):
        w = config.get_event_weights("BB")
        assert w["discipline"] == 1.0
        assert w["contact"] == 0.0

    def test_pitcher_event_weights_strikeout(self, config):
        w = config.get_pitcher_event_weights("StrikeOut")
        assert w["stuff"] == 1.0
        assert w["command"] == 0.3

    def test_pitcher_event_weights_bb(self, config):
        w = config.get_pitcher_event_weights("BB")
        assert w["command"] == -1.0
        assert w["stuff"] == 0.0

    def test_pitcher_event_weights_hr(self, config):
        w = config.get_pitcher_event_weights("HR")
        assert w["stuff"] == -0.8
        assert w["bip_suppression"] == -0.5

    def test_unknown_event_returns_zeros(self, config):
        w = config.get_event_weights("UNKNOWN")
        assert all(v == 0.0 for v in w.values())

    def test_reliability_threshold_contact(self, config):
        assert config.get_reliability_threshold("contact") == 400

    def test_reliability_threshold_speed(self, config):
        assert config.get_reliability_threshold("speed") == 50

    def test_expected_divisor_contact(self, config):
        assert config.get_expected_divisor("contact", is_pitcher=False) == 127.0

    def test_batter_scale_power(self, config):
        assert config.get_batter_scale("power") == 10.0

    def test_pitcher_scale_bip_suppression(self, config):
        assert config.get_pitcher_scale("bip_suppression") == 3.0

    def test_composite_weights_batter(self, config):
        w = config.get_batter_composite_weights()
        assert sum(w.values()) == pytest.approx(1.0)

    def test_composite_weights_pitcher_starter(self, config):
        w = config.get_pitcher_composite_weights("starter")
        assert w["command"] == 0.40
        assert sum(w.values()) == pytest.approx(1.0)

    def test_composite_weights_pitcher_closer(self, config):
        w = config.get_pitcher_composite_weights("closer")
        assert w["stuff"] == 0.35

    def test_clutch_config(self, config):
        assert config.leverage_threshold == 2.0
        assert config.max_clutch_multiplier == 2.0
