# 9-Dimensional Talent ELO Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a 9-dimensional talent ELO system (Batter 5D + Pitcher 4D) alongside the existing composite ELO, ported from balltology-elo with MLB adaptations.

**Architecture:** Separate parallel engine. The existing composite ELO (K-modulation) is unchanged. A new talent engine processes the same PA DataFrame independently, using binary matchup-based expected scores per dimension with event-dimension weight matrices. Each PA produces per-dimension deltas for both batter (5D) and pitcher (4D). TWP players appear in both batter and pitcher state dictionaries.

**Tech Stack:** Python 3.11+, numpy, pandas, PyYAML, pytest. Reference: balltology-elo (KBO) at `/Users/mksong/Documents/balltology-elo`.

**Key Design Decisions:**
- **Binary matchup model** per dimension (not rv_diff): `delta = K × scale × |weight| × (actual - expected) × reliability`. This isolates each skill signal.
- **Asymmetric pitcher weights** (DIPS): Pitcher dimensions are calculated independently, NOT as negated batter deltas. Stuff/Command/BIP_Supp have separate weight matrices.
- **Parallel, not replacement**: Talent ELO runs alongside composite ELO. Same PA data, separate state.
- **player_id: int** (MLB uses integer IDs, not strings like KBO).
- **No leverage_index yet**: Use RISP (on_2b/on_3b) as clutch proxy. Full LI deferred to Phase 2.

---

## Task 1: YAML Config + Config Loader

**Files:**
- Create: `config/multi_elo_config.yaml`
- Create: `src/engine/multi_elo_config.py`
- Test: `tests/test_talent_config_260130.py`

### Step 1: Write failing tests

```python
# tests/test_talent_config_260130.py
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
```

### Step 2: Run test to verify it fails

```bash
pytest tests/test_talent_config_260130.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.engine.multi_elo_config'`

### Step 3: Create YAML config

Create `config/multi_elo_config.yaml` — copy from balltology-elo verbatim (it uses the same event types). File at `/Users/mksong/Documents/balltology-elo/config/multi_elo_config.yaml`. Copy the entire file.

### Step 4: Create config loader

Create `src/engine/multi_elo_config.py`:

```python
"""Multi-ELO Config Loader (9D Talent System)."""
from pathlib import Path
from typing import Any
import yaml


class MultiEloConfig:
    """YAML-based Multi-ELO configuration."""

    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "multi_elo_config.yaml"

    def __init__(self, config_path: Path | str | None = None):
        path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        with open(path, encoding="utf-8") as f:
            self._config = yaml.safe_load(f)
        self._build_indices()

    def _build_indices(self) -> None:
        self._batter_dim_map = {d["name"]: d for d in self._config["batter_dimensions"]}
        self._pitcher_dim_map = {d["name"]: d for d in self._config["pitcher_dimensions"]}

    @property
    def version(self) -> str:
        return self._config["version"]

    @property
    def batter_dimensions(self) -> list[dict]:
        return self._config["batter_dimensions"]

    @property
    def pitcher_dimensions(self) -> list[dict]:
        return self._config["pitcher_dimensions"]

    def get_event_weights(self, event_type: str) -> dict[str, float]:
        weights = self._config["event_weights"].get(event_type, {})
        result = {"contact": 0.0, "power": 0.0, "discipline": 0.0, "speed": 0.0, "clutch_base": 0.0}
        result.update(weights)
        return result

    def get_pitcher_event_weights(self, event_type: str) -> dict[str, float]:
        weights = self._config.get("pitcher_event_weights", {}).get(event_type, {})
        result = {"stuff": 0.0, "bip_suppression": 0.0, "command": 0.0, "clutch_base": 0.0}
        result.update(weights)
        return result

    def get_batter_k_factor(self, dimension: str) -> float:
        return self._batter_dim_map.get(dimension, {}).get("k_factor", 12.0)

    def get_pitcher_k_factor(self, dimension: str) -> float:
        return self._pitcher_dim_map.get(dimension, {}).get("k_factor", 12.0)

    def get_batter_scale(self, dimension: str) -> float:
        return self._batter_dim_map.get(dimension, {}).get("scale", 5.0)

    def get_pitcher_scale(self, dimension: str) -> float:
        return self._pitcher_dim_map.get(dimension, {}).get("scale", 5.0)

    def get_reliability_threshold(self, dimension: str, is_pitcher: bool = False) -> int:
        dim_map = self._pitcher_dim_map if is_pitcher else self._batter_dim_map
        return dim_map.get(dimension, {}).get("reliability_threshold", 400)

    def get_expected_divisor(self, dimension: str, is_pitcher: bool = False) -> float:
        dim_map = self._pitcher_dim_map if is_pitcher else self._batter_dim_map
        default = self._config.get("constants", {}).get("default_expected_divisor", 400.0)
        return dim_map.get(dimension, {}).get("expected_divisor", default)

    def get_batter_composite_weights(self) -> dict[str, float]:
        return self._config["composite_weights"]["batter"]["default"].copy()

    def get_pitcher_composite_weights(self, role: str = "starter") -> dict[str, float]:
        pw = self._config["composite_weights"]["pitcher"]
        return pw.get(role, pw["starter"]).copy()

    @property
    def leverage_threshold(self) -> float:
        return self._config["clutch_config"]["leverage_threshold"]

    @property
    def max_clutch_multiplier(self) -> float:
        return self._config["clutch_config"]["max_multiplier"]
```

### Step 5: Run tests to verify pass

```bash
pytest tests/test_talent_config_260130.py -v
```
Expected: ALL PASS

### Step 6: Commit

```bash
git add config/multi_elo_config.yaml src/engine/multi_elo_config.py tests/test_talent_config_260130.py
git commit -m "feat(talent): add 9D config YAML + MultiEloConfig loader"
```

---

## Task 2: Talent State Types (BatterTalentState, PitcherTalentState)

**Files:**
- Create: `src/engine/multi_elo_types.py`
- Test: `tests/test_talent_types_260130.py`

### Step 1: Write failing tests

```python
# tests/test_talent_types_260130.py
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
```

### Step 2: Run test to verify it fails

```bash
pytest tests/test_talent_types_260130.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.engine.multi_elo_types'`

### Step 3: Implement types

Create `src/engine/multi_elo_types.py`:

```python
"""Multi-Dimensional ELO Types (9D Talent System).

Batter 5D: Contact, Power, Discipline, Speed, Clutch
Pitcher 4D: Stuff, BIP_Suppression, Command, Clutch
"""
from dataclasses import dataclass, field

import numpy as np

# === Constants ===

DEFAULT_ELO = 1500.0
ELO_MIN = 500.0
ELO_MAX = 3000.0
MIN_RELIABILITY = 0.3

BATTER_DIM_COUNT = 5
BATTER_DIM_NAMES = ["contact", "power", "discipline", "speed", "clutch"]

PITCHER_DIM_COUNT = 4
PITCHER_DIM_NAMES = ["stuff", "bip_suppression", "command", "clutch"]

BATTER_DEFAULT_WEIGHTS = np.array([0.20, 0.20, 0.20, 0.20, 0.20])

PITCHER_ROLE_WEIGHTS = {
    "starter": np.array([0.25, 0.20, 0.40, 0.15]),
    "reliever": np.array([0.35, 0.20, 0.30, 0.15]),
    "closer": np.array([0.35, 0.25, 0.25, 0.15]),
}


@dataclass
class BatterTalentState:
    """Batter 5D talent ELO state."""
    player_id: int
    elo_dimensions: np.ndarray = field(default_factory=lambda: np.full(BATTER_DIM_COUNT, DEFAULT_ELO))
    event_counts: np.ndarray = field(default_factory=lambda: np.zeros(BATTER_DIM_COUNT))
    pa_count: int = 0

    CONTACT = 0
    POWER = 1
    DISCIPLINE = 2
    SPEED = 3
    CLUTCH = 4

    @property
    def composite_elo(self) -> float:
        return float(np.dot(self.elo_dimensions, BATTER_DEFAULT_WEIGHTS))

    def apply_deltas(self, deltas: np.ndarray) -> None:
        self.elo_dimensions = np.clip(self.elo_dimensions + deltas, ELO_MIN, ELO_MAX)

    def increment_pa(self) -> None:
        self.pa_count += 1


@dataclass
class PitcherTalentState:
    """Pitcher 4D talent ELO state."""
    player_id: int
    elo_dimensions: np.ndarray = field(default_factory=lambda: np.full(PITCHER_DIM_COUNT, DEFAULT_ELO))
    event_counts: np.ndarray = field(default_factory=lambda: np.zeros(PITCHER_DIM_COUNT))
    bfp_count: int = 0
    role: str = "starter"

    STUFF = 0
    BIP_SUPPRESSION = 1
    COMMAND = 2
    CLUTCH = 3

    @property
    def composite_elo(self) -> float:
        weights = PITCHER_ROLE_WEIGHTS.get(self.role, PITCHER_ROLE_WEIGHTS["starter"])
        return float(np.dot(self.elo_dimensions, weights))

    def apply_deltas(self, deltas: np.ndarray) -> None:
        self.elo_dimensions = np.clip(self.elo_dimensions + deltas, ELO_MIN, ELO_MAX)

    def increment_bfp(self) -> None:
        self.bfp_count += 1
```

### Step 4: Run tests

```bash
pytest tests/test_talent_types_260130.py -v
```
Expected: ALL PASS

### Step 5: Commit

```bash
git add src/engine/multi_elo_types.py tests/test_talent_types_260130.py
git commit -m "feat(talent): add BatterTalentState(5D) + PitcherTalentState(4D)"
```

---

## Task 3: TalentStateManager

**Files:**
- Create: `src/engine/talent_state_manager.py`
- Test: `tests/test_talent_state_mgr_260130.py`

### Step 1: Write failing tests

```python
# tests/test_talent_state_mgr_260130.py
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
```

### Step 2: Verify fails

```bash
pytest tests/test_talent_state_mgr_260130.py -v
```
Expected: FAIL with `ModuleNotFoundError`

### Step 3: Implement

Create `src/engine/talent_state_manager.py`:

```python
"""Talent State Manager — Season/Career dual tracking for 9D talent."""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.engine.multi_elo_types import BatterTalentState, PitcherTalentState, DEFAULT_ELO


@dataclass
class DualBatterState:
    """Batter dual state: Season (resets yearly) + Career (cumulative)."""
    player_id: int
    season: BatterTalentState = field(default=None)
    career: BatterTalentState = field(default=None)

    def __post_init__(self):
        if self.season is None:
            self.season = BatterTalentState(player_id=self.player_id)
        if self.career is None:
            self.career = BatterTalentState(player_id=self.player_id)

    def apply_deltas(self, deltas: np.ndarray) -> None:
        self.season.apply_deltas(deltas)
        self.career.apply_deltas(deltas)
        self.season.increment_pa()
        self.career.increment_pa()

    def reset_season(self) -> None:
        self.season = BatterTalentState(player_id=self.player_id)


@dataclass
class DualPitcherState:
    """Pitcher dual state: Season (resets yearly) + Career (cumulative)."""
    player_id: int
    season: PitcherTalentState = field(default=None)
    career: PitcherTalentState = field(default=None)

    def __post_init__(self):
        if self.season is None:
            self.season = PitcherTalentState(player_id=self.player_id)
        if self.career is None:
            self.career = PitcherTalentState(player_id=self.player_id)

    def apply_deltas(self, deltas: np.ndarray) -> None:
        self.season.apply_deltas(deltas)
        self.career.apply_deltas(deltas)
        self.season.increment_bfp()
        self.career.increment_bfp()

    def reset_season(self) -> None:
        self.season = PitcherTalentState(player_id=self.player_id)


class TalentStateManager:
    """Manages all batter and pitcher talent states."""

    def __init__(self):
        self._batters: dict[int, DualBatterState] = {}
        self._pitchers: dict[int, DualPitcherState] = {}
        self._current_season: Optional[int] = None

    def get_or_create_batter(self, player_id: int) -> DualBatterState:
        if player_id not in self._batters:
            self._batters[player_id] = DualBatterState(player_id=player_id)
        return self._batters[player_id]

    def get_or_create_pitcher(self, player_id: int) -> DualPitcherState:
        if player_id not in self._pitchers:
            self._pitchers[player_id] = DualPitcherState(player_id=player_id)
        return self._pitchers[player_id]

    def reset_season(self, new_season: int) -> None:
        for b in self._batters.values():
            b.reset_season()
        for p in self._pitchers.values():
            p.reset_season()
        self._current_season = new_season

    @property
    def all_batters(self) -> dict[int, DualBatterState]:
        return self._batters

    @property
    def all_pitchers(self) -> dict[int, DualPitcherState]:
        return self._pitchers

    @property
    def current_season(self) -> Optional[int]:
        return self._current_season
```

### Step 4: Run tests

```bash
pytest tests/test_talent_state_mgr_260130.py -v
```
Expected: ALL PASS

### Step 5: Commit

```bash
git add src/engine/talent_state_manager.py tests/test_talent_state_mgr_260130.py
git commit -m "feat(talent): add TalentStateManager with Season/Career dual tracking"
```

---

## Task 4: MultiEloEngine (Core 9D Calculation)

**Files:**
- Create: `src/engine/multi_elo_engine.py`
- Test: `tests/test_talent_engine_260130.py`

### Step 1: Write failing tests

```python
# tests/test_talent_engine_260130.py
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
        """contact threshold=400 → event_count=400 → reliability=1.0."""
        assert engine.calculate_reliability(400, "contact") == pytest.approx(1.0)

    def test_half_threshold(self, engine):
        """contact threshold=400 → 200 events → 0.3 + 0.7*(200/400) = 0.65."""
        assert engine.calculate_reliability(200, "contact") == pytest.approx(0.65)

    def test_speed_low_threshold(self, engine):
        """speed threshold=50 → 50 events → 1.0."""
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
        """HR → power weight=1.0 → power ELO should increase."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="HR"
        )
        assert result.batter_deltas[BatterTalentState.POWER] > 0

    def test_hr_increases_contact_slightly(self, engine, batter, pitcher):
        """HR → contact weight=0.2 → small positive contact delta."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="HR"
        )
        contact_delta = result.batter_deltas[BatterTalentState.CONTACT]
        power_delta = result.batter_deltas[BatterTalentState.POWER]
        assert contact_delta > 0
        assert contact_delta < power_delta  # Contact signal weaker

    def test_strikeout_decreases_contact(self, engine, batter, pitcher):
        """StrikeOut → contact weight=-1.0 → contact ELO decreases."""
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
        """BB → discipline weight=1.0 → discipline increases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="BB"
        )
        assert result.batter_deltas[BatterTalentState.DISCIPLINE] > 0

    def test_pitcher_strikeout_stuff(self, engine, batter, pitcher):
        """StrikeOut → pitcher stuff=1.0 → stuff ELO increases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="StrikeOut"
        )
        assert result.pitcher_deltas[PitcherTalentState.STUFF] > 0

    def test_pitcher_bb_command(self, engine, batter, pitcher):
        """BB → pitcher command=-1.0 → command ELO decreases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="BB"
        )
        assert result.pitcher_deltas[PitcherTalentState.COMMAND] < 0

    def test_pitcher_hr_stuff_decreases(self, engine, batter, pitcher):
        """HR → pitcher stuff=-0.8 → stuff ELO decreases."""
        result = engine.process_plate_appearance(
            batter, pitcher, result_type="HR"
        )
        assert result.pitcher_deltas[PitcherTalentState.STUFF] < 0

    def test_error_minimal_impact(self, engine, batter, pitcher):
        """E → batter contact=0.1 (small), pitcher bip_supp=-0.1 (small)."""
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
        """RISP=True → clutch delta is amplified."""
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
        """High-contact batter vs low-stuff pitcher → lower expected → larger delta."""
        strong = BatterTalentState(player_id=1)
        strong.elo_dimensions[BatterTalentState.CONTACT] = 1700.0
        weak_p = PitcherTalentState(player_id=2)
        weak_p.elo_dimensions[PitcherTalentState.STUFF] = 1300.0

        avg_b = BatterTalentState(player_id=3)
        avg_p = PitcherTalentState(player_id=4)

        r1 = engine.process_plate_appearance(strong, weak_p, result_type="Single")
        r2 = engine.process_plate_appearance(avg_b, avg_p, result_type="Single")

        # Strong batter expected to get hit → lower delta (already expected)
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
```

### Step 2: Verify fails

```bash
pytest tests/test_talent_engine_260130.py -v
```
Expected: FAIL with `ModuleNotFoundError`

### Step 3: Implement engine

Create `src/engine/multi_elo_engine.py`:

```python
"""Multi-Dimensional ELO Engine (9D Talent System).

Batter 5D: Contact, Power, Discipline, Speed, Clutch
Pitcher 4D: Stuff, BIP_Suppression, Command, Clutch

Binary matchup model: delta = K × scale × |weight| × (actual - expected) × reliability
DIPS-based asymmetric pitcher weights (V2).
"""
from dataclasses import dataclass

import numpy as np

from src.engine.multi_elo_config import MultiEloConfig
from src.engine.multi_elo_types import (
    BatterTalentState,
    PitcherTalentState,
    BATTER_DIM_NAMES,
    PITCHER_DIM_NAMES,
    MIN_RELIABILITY,
)


@dataclass
class TalentUpdateResult:
    """Per-PA talent ELO update result."""
    batter_deltas: np.ndarray   # 5D
    pitcher_deltas: np.ndarray  # 4D
    batter_elo_after: np.ndarray
    pitcher_elo_after: np.ndarray
    event_type: str
    is_clutch: bool


class MultiEloEngine:
    """9-Dimensional Talent ELO Engine."""

    BATTER_TO_PITCHER = {
        "contact": "stuff",
        "power": "bip_suppression",
        "discipline": "command",
        "speed": None,
        "clutch": "clutch",
    }

    PITCHER_TO_BATTER = {
        "stuff": "contact",
        "bip_suppression": "contact",
        "command": "discipline",
        "clutch": "clutch",
    }

    def __init__(self, config: MultiEloConfig | None = None):
        self.config = config or MultiEloConfig()

    def calculate_expected_score(
        self, player_elo: float, opponent_elo: float, divisor: float = 400.0
    ) -> float:
        return 1.0 / (1.0 + 10.0 ** ((opponent_elo - player_elo) / divisor))

    def calculate_reliability(
        self, event_count: int, dimension: str, is_pitcher: bool = False
    ) -> float:
        threshold = self.config.get_reliability_threshold(dimension, is_pitcher)
        if event_count >= threshold:
            return 1.0
        return MIN_RELIABILITY + (1 - MIN_RELIABILITY) * (event_count / threshold)

    def get_clutch_multiplier(self, leverage_index: float) -> float:
        if leverage_index <= 1.0:
            return 0.0
        max_mult = self.config.max_clutch_multiplier
        return min(max_mult, leverage_index / 2.0)

    def process_plate_appearance(
        self,
        batter: BatterTalentState,
        pitcher: PitcherTalentState,
        result_type: str,
        leverage_index: float = 1.0,
        is_risp: bool = False,
    ) -> TalentUpdateResult:
        batter_weights = self.config.get_event_weights(result_type)
        pitcher_weights = self.config.get_pitcher_event_weights(result_type)
        clutch_mult = self.get_clutch_multiplier(leverage_index)
        is_clutch = leverage_index > self.config.leverage_threshold or is_risp

        # RISP triggers minimum clutch activation
        if is_risp and clutch_mult == 0.0:
            clutch_mult = 0.5

        # GIDP clutch multiplier
        if result_type == "GIDP":
            gidp_mult = batter_weights.get("clutch_multiplier", 1.0)
            clutch_mult *= gidp_mult

        batter_deltas = np.zeros(5)
        pitcher_deltas = np.zeros(4)

        # === Batter loop (5D) ===
        for b_idx, b_dim in enumerate(BATTER_DIM_NAMES):
            weight = batter_weights.get(b_dim, 0.0)

            if b_dim == "clutch":
                base_weight = batter_weights.get("clutch_base", 0.0)
                if clutch_mult > 0:
                    weight = base_weight * (1.0 + clutch_mult)
                else:
                    weight = base_weight * 0.5

            if weight == 0.0:
                continue

            p_dim = self.BATTER_TO_PITCHER.get(b_dim)
            k = self.config.get_batter_k_factor(b_dim)
            scale = self.config.get_batter_scale(b_dim)
            reliability = self.calculate_reliability(
                int(batter.event_counts[b_idx]), b_dim
            )

            if p_dim is None:
                # Speed: no pitcher matchup
                actual = 1.0 if weight > 0 else 0.0
                expected = 0.5
            else:
                p_idx = PITCHER_DIM_NAMES.index(p_dim)
                b_divisor = self.config.get_expected_divisor(b_dim, is_pitcher=False)
                p_divisor = self.config.get_expected_divisor(p_dim, is_pitcher=True)
                divisor = (b_divisor + p_divisor) / 2

                expected = self.calculate_expected_score(
                    batter.elo_dimensions[b_idx],
                    pitcher.elo_dimensions[p_idx],
                    divisor=divisor,
                )
                actual = 1.0 if weight > 0 else 0.0

            delta = k * scale * abs(weight) * (actual - expected) * reliability
            batter_deltas[b_idx] = delta

        # === Pitcher loop (4D, V2: independent) ===
        for p_idx, p_dim in enumerate(PITCHER_DIM_NAMES):
            weight = pitcher_weights.get(p_dim, 0.0)

            if p_dim == "clutch":
                base_weight = pitcher_weights.get("clutch_base", 0.0)
                if clutch_mult > 0:
                    weight = base_weight * (1.0 + clutch_mult)
                else:
                    weight = base_weight * 0.5

            if weight == 0.0:
                continue

            b_dim = self.PITCHER_TO_BATTER.get(p_dim)
            b_idx = BATTER_DIM_NAMES.index(b_dim) if b_dim else None

            k = self.config.get_pitcher_k_factor(p_dim)
            scale = self.config.get_pitcher_scale(p_dim)
            reliability = self.calculate_reliability(
                int(pitcher.event_counts[p_idx]), p_dim, is_pitcher=True
            )

            if b_idx is not None:
                b_divisor = self.config.get_expected_divisor(b_dim, is_pitcher=False)
                p_divisor = self.config.get_expected_divisor(p_dim, is_pitcher=True)
                divisor = (b_divisor + p_divisor) / 2
                expected = self.calculate_expected_score(
                    pitcher.elo_dimensions[p_idx],
                    batter.elo_dimensions[b_idx],
                    divisor=divisor,
                )
            else:
                expected = 0.5

            actual = 1.0 if weight > 0 else 0.0
            delta = k * scale * abs(weight) * (actual - expected) * reliability
            pitcher_deltas[p_idx] += delta

        # Update states
        batter.apply_deltas(batter_deltas)
        pitcher.apply_deltas(pitcher_deltas)

        # Event counts
        for b_idx in range(5):
            if batter_deltas[b_idx] != 0:
                batter.event_counts[b_idx] += 1
        for p_idx in range(4):
            if pitcher_deltas[p_idx] != 0:
                pitcher.event_counts[p_idx] += 1

        batter.increment_pa()
        pitcher.increment_bfp()

        return TalentUpdateResult(
            batter_deltas=batter_deltas,
            pitcher_deltas=pitcher_deltas,
            batter_elo_after=batter.elo_dimensions.copy(),
            pitcher_elo_after=pitcher.elo_dimensions.copy(),
            event_type=result_type,
            is_clutch=is_clutch,
        )
```

### Step 4: Run tests

```bash
pytest tests/test_talent_engine_260130.py -v
```
Expected: ALL PASS

### Step 5: Commit

```bash
git add src/engine/multi_elo_engine.py tests/test_talent_engine_260130.py
git commit -m "feat(talent): add MultiEloEngine with 9D matchup calculation"
```

---

## Task 5: TalentBatch Processor

**Files:**
- Create: `src/engine/talent_batch.py`
- Test: `tests/test_talent_batch_260130.py`

### Step 1: Write failing tests

```python
# tests/test_talent_batch_260130.py
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
```

### Step 2: Verify fails

```bash
pytest tests/test_talent_batch_260130.py -v
```

### Step 3: Implement

Create `src/engine/talent_batch.py`:

```python
"""Talent Batch Processor — 9D talent ELO batch computation.

Processes PA DataFrame to produce:
- talent_pa_details: per-PA per-dimension ELO changes
- talent_daily_ohlc: daily OHLC per dimension
- talent_player_records: current snapshot per dimension
"""
import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from src.engine.multi_elo_config import MultiEloConfig
from src.engine.multi_elo_engine import MultiEloEngine
from src.engine.multi_elo_types import (
    BatterTalentState,
    PitcherTalentState,
    BATTER_DIM_NAMES,
    PITCHER_DIM_NAMES,
    DEFAULT_ELO,
)
from src.engine.talent_state_manager import TalentStateManager

logger = logging.getLogger(__name__)


class TalentBatch:
    """9D Talent ELO batch processor."""

    def __init__(self, config: MultiEloConfig | None = None):
        self.config = config or MultiEloConfig()
        self.engine = MultiEloEngine(config=self.config)
        self.state_mgr = TalentStateManager()

        self.talent_pa_details: list[dict] = []
        self.talent_daily_ohlc: list[dict] = []

        # OHLC tracking: key = (player_id, talent_type)
        self._current_date: Optional[str] = None
        self._day_open: dict[tuple, float] = {}
        self._day_high: dict[tuple, float] = {}
        self._day_low: dict[tuple, float] = {}
        self._day_pa_count: dict[tuple, int] = {}

    def _record_ohlc_open(self, player_id: int, talent_type: str, elo: float):
        key = (player_id, talent_type)
        if key not in self._day_open:
            self._day_open[key] = elo
            self._day_high[key] = elo
            self._day_low[key] = elo
            self._day_pa_count[key] = 0

    def _update_ohlc(self, player_id: int, talent_type: str, elo: float):
        key = (player_id, talent_type)
        if key in self._day_high:
            self._day_high[key] = max(self._day_high[key], elo)
        if key in self._day_low:
            self._day_low[key] = min(self._day_low[key], elo)
        if key in self._day_pa_count:
            self._day_pa_count[key] += 1

    def _finalize_day(self, game_date_str: str):
        game_date_val = date.fromisoformat(game_date_str)
        for (player_id, talent_type) in list(self._day_open.keys()):
            # Get current ELO for close value
            close_elo = self._get_current_elo(player_id, talent_type)
            self.talent_daily_ohlc.append({
                'player_id': player_id,
                'game_date': game_date_val.isoformat(),
                'talent_type': talent_type,
                'elo_type': 'SEASON',
                'open': self._day_open[(player_id, talent_type)],
                'high': self._day_high[(player_id, talent_type)],
                'low': self._day_low[(player_id, talent_type)],
                'close': close_elo,
                'total_pa': self._day_pa_count.get((player_id, talent_type), 0),
            })
        self._day_open.clear()
        self._day_high.clear()
        self._day_low.clear()
        self._day_pa_count.clear()

    def _get_current_elo(self, player_id: int, talent_type: str) -> float:
        """Get current ELO for a player's talent dimension."""
        if talent_type in BATTER_DIM_NAMES:
            idx = BATTER_DIM_NAMES.index(talent_type)
            if player_id in self.state_mgr.all_batters:
                return float(self.state_mgr.all_batters[player_id].season.elo_dimensions[idx])
        if talent_type in PITCHER_DIM_NAMES:
            idx = PITCHER_DIM_NAMES.index(talent_type)
            if player_id in self.state_mgr.all_pitchers:
                return float(self.state_mgr.all_pitchers[player_id].season.elo_dimensions[idx])
        return DEFAULT_ELO

    def process(self, pa_df: pd.DataFrame):
        """Process PA DataFrame for 9D talent ELO."""
        total = len(pa_df)

        for idx, row in pa_df.iterrows():
            game_date_str = str(row['game_date'])[:10]

            if self._current_date is not None and game_date_str != self._current_date:
                self._finalize_day(self._current_date)
            self._current_date = game_date_str

            batter_id = int(row['batter_id'])
            pitcher_id = int(row['pitcher_id'])
            result_type = row.get('result_type', 'OUT')

            batter_dual = self.state_mgr.get_or_create_batter(batter_id)
            pitcher_dual = self.state_mgr.get_or_create_pitcher(pitcher_id)

            batter = batter_dual.season
            pitcher = pitcher_dual.season

            # RISP from base state
            is_risp = bool(row.get('on_2b', False)) or bool(row.get('on_3b', False))

            # Record OHLC opens (before PA)
            for b_idx, dim_name in enumerate(BATTER_DIM_NAMES):
                self._record_ohlc_open(batter_id, dim_name, float(batter.elo_dimensions[b_idx]))
            for p_idx, dim_name in enumerate(PITCHER_DIM_NAMES):
                self._record_ohlc_open(pitcher_id, dim_name, float(pitcher.elo_dimensions[p_idx]))

            # Snapshot before
            batter_before = batter.elo_dimensions.copy()
            pitcher_before = pitcher.elo_dimensions.copy()

            # Process PA
            result = self.engine.process_plate_appearance(
                batter, pitcher,
                result_type=result_type,
                is_risp=is_risp,
            )

            # Apply same deltas to career
            batter_dual.career.apply_deltas(result.batter_deltas)
            batter_dual.career.increment_pa()
            pitcher_dual.career.apply_deltas(result.pitcher_deltas)
            pitcher_dual.career.increment_bfp()
            # Career event counts
            for b_idx in range(5):
                if result.batter_deltas[b_idx] != 0:
                    batter_dual.career.event_counts[b_idx] += 1
            for p_idx in range(4):
                if result.pitcher_deltas[p_idx] != 0:
                    pitcher_dual.career.event_counts[p_idx] += 1

            # Record OHLC updates (after PA)
            for b_idx, dim_name in enumerate(BATTER_DIM_NAMES):
                self._update_ohlc(batter_id, dim_name, float(batter.elo_dimensions[b_idx]))
            for p_idx, dim_name in enumerate(PITCHER_DIM_NAMES):
                self._update_ohlc(pitcher_id, dim_name, float(pitcher.elo_dimensions[p_idx]))

            # PA detail records (per affected dimension)
            pa_id = int(row['pa_id'])
            for b_idx, dim_name in enumerate(BATTER_DIM_NAMES):
                if result.batter_deltas[b_idx] != 0:
                    self.talent_pa_details.append({
                        'pa_id': pa_id,
                        'player_id': batter_id,
                        'player_role': 'batter',
                        'talent_type': dim_name,
                        'elo_before': float(batter_before[b_idx]),
                        'elo_after': float(batter.elo_dimensions[b_idx]),
                        'delta': float(result.batter_deltas[b_idx]),
                    })
            for p_idx, dim_name in enumerate(PITCHER_DIM_NAMES):
                if result.pitcher_deltas[p_idx] != 0:
                    self.talent_pa_details.append({
                        'pa_id': pa_id,
                        'player_id': pitcher_id,
                        'player_role': 'pitcher',
                        'talent_type': dim_name,
                        'elo_before': float(pitcher_before[p_idx]),
                        'elo_after': float(pitcher.elo_dimensions[p_idx]),
                        'delta': float(result.pitcher_deltas[p_idx]),
                    })

            if (idx + 1) % 50000 == 0:
                logger.info(f"  Talent: Processed {idx + 1:,} / {total:,} PAs")

        # Finalize last day
        if self._current_date is not None:
            self._finalize_day(self._current_date)

        logger.info(
            f"  Talent: Completed {total:,} PAs, "
            f"{len(self.talent_pa_details):,} detail records, "
            f"{len(self.talent_daily_ohlc):,} OHLC records"
        )

    def get_talent_player_records(self) -> list[dict]:
        """Generate talent_player_current table records."""
        records = []
        for pid, dual in self.state_mgr.all_batters.items():
            for b_idx, dim_name in enumerate(BATTER_DIM_NAMES):
                records.append({
                    'player_id': pid,
                    'player_role': 'batter',
                    'talent_type': dim_name,
                    'season_elo': float(dual.season.elo_dimensions[b_idx]),
                    'career_elo': float(dual.career.elo_dimensions[b_idx]),
                    'event_count': int(dual.season.event_counts[b_idx]),
                    'pa_count': dual.season.pa_count,
                })
        for pid, dual in self.state_mgr.all_pitchers.items():
            for p_idx, dim_name in enumerate(PITCHER_DIM_NAMES):
                records.append({
                    'player_id': pid,
                    'player_role': 'pitcher',
                    'talent_type': dim_name,
                    'season_elo': float(dual.season.elo_dimensions[p_idx]),
                    'career_elo': float(dual.career.elo_dimensions[p_idx]),
                    'event_count': int(dual.season.event_counts[p_idx]),
                    'pa_count': dual.season.bfp_count,
                })
        return records
```

### Step 4: Run tests

```bash
pytest tests/test_talent_batch_260130.py -v
```
Expected: ALL PASS

### Step 5: Commit

```bash
git add src/engine/talent_batch.py tests/test_talent_batch_260130.py
git commit -m "feat(talent): add TalentBatch processor for 9D season computation"
```

---

## Task 6: DB Migration SQL

**Files:**
- Create: `scripts/migrations/004_talent_schema.sql`
- No automated test (SQL migration tested via Supabase dashboard)

### Step 1: Create migration

```sql
-- scripts/migrations/004_talent_schema.sql
-- Phase 8: 9-Dimensional Talent ELO Schema
-- 3 new tables: talent_player_current, talent_pa_detail, talent_daily_ohlc

-- 1. Talent Player Current (per player × dimension snapshot)
CREATE TABLE IF NOT EXISTS talent_player_current (
  player_id      INTEGER NOT NULL REFERENCES players(player_id),
  player_role    VARCHAR(10) NOT NULL,  -- 'batter' or 'pitcher'
  talent_type    VARCHAR(20) NOT NULL,  -- dimension name
  season_elo     REAL DEFAULT 1500.0,
  career_elo     REAL DEFAULT 1500.0,
  event_count    INTEGER DEFAULT 0,
  pa_count       INTEGER DEFAULT 0,
  PRIMARY KEY (player_id, talent_type, player_role)
);
CREATE INDEX IF NOT EXISTS idx_talent_current_type ON talent_player_current(talent_type);
CREATE INDEX IF NOT EXISTS idx_talent_current_role ON talent_player_current(player_role);

-- 2. Talent PA Detail (per PA × player × dimension)
CREATE TABLE IF NOT EXISTS talent_pa_detail (
  id             SERIAL PRIMARY KEY,
  pa_id          BIGINT NOT NULL REFERENCES plate_appearances(pa_id),
  player_id      INTEGER NOT NULL,
  player_role    VARCHAR(10) NOT NULL,
  talent_type    VARCHAR(20) NOT NULL,
  elo_before     REAL NOT NULL,
  elo_after      REAL NOT NULL,
  delta          REAL GENERATED ALWAYS AS (elo_after - elo_before) STORED,
  UNIQUE (pa_id, player_id, talent_type)
);
CREATE INDEX IF NOT EXISTS idx_talent_pa_player ON talent_pa_detail(player_id, talent_type);
CREATE INDEX IF NOT EXISTS idx_talent_pa_date ON talent_pa_detail(pa_id);

-- 3. Talent Daily OHLC (per player × dimension × date)
CREATE TABLE IF NOT EXISTS talent_daily_ohlc (
  id             SERIAL PRIMARY KEY,
  player_id      INTEGER NOT NULL REFERENCES players(player_id),
  game_date      DATE NOT NULL,
  talent_type    VARCHAR(20) NOT NULL,
  elo_type       VARCHAR(10) NOT NULL DEFAULT 'SEASON',
  open           REAL NOT NULL,
  high           REAL NOT NULL,
  low            REAL NOT NULL,
  close          REAL NOT NULL,
  delta          REAL GENERATED ALWAYS AS (close - open) STORED,
  range          REAL GENERATED ALWAYS AS (high - low) STORED,
  total_pa       INTEGER DEFAULT 0,
  UNIQUE (player_id, game_date, talent_type, elo_type)
);
CREATE INDEX IF NOT EXISTS idx_talent_ohlc_player ON talent_daily_ohlc(player_id, game_date);
CREATE INDEX IF NOT EXISTS idx_talent_ohlc_type ON talent_daily_ohlc(talent_type, game_date);
CREATE INDEX IF NOT EXISTS idx_talent_ohlc_delta ON talent_daily_ohlc(game_date, talent_type, delta DESC);
```

### Step 2: Commit

```bash
git add scripts/migrations/004_talent_schema.sql
git commit -m "feat(db): add 9D talent schema migration (004)"
```

---

## Task 7: Pipeline Integration (run_elo.py)

**Files:**
- Modify: `scripts/run_elo.py`
- Test: `tests/test_talent_pipeline_260130.py`

### Step 1: Write integration test

```python
# tests/test_talent_pipeline_260130.py
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
        contact = batter_10.elo_dimensions[0]  # contact
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
```

### Step 2: Verify fails (will partially pass, but pipeline test should work since module exists)

```bash
pytest tests/test_talent_pipeline_260130.py -v
```

### Step 3: Update run_elo.py

Add talent batch processing alongside composite batch in `scripts/run_elo.py`.

Add these imports at the top:
```python
from src.engine.talent_batch import TalentBatch
```

Add after `batch.process(pa_df)` and before `print_summary(batch)`:
```python
    # 3b. Run talent ELO calculation
    print("\nRunning 9D Talent ELO calculation...")
    talent_batch = TalentBatch()
    talent_batch.process(pa_df)
    print(f"  Talent PA details: {len(talent_batch.talent_pa_details):,}")
    print(f"  Talent OHLC records: {len(talent_batch.talent_daily_ohlc):,}")
    talent_records = talent_batch.get_talent_player_records()
    print(f"  Talent player records: {len(talent_records):,}")
```

Add upload section after existing uploads:
```python
    # 5d. talent_player_current
    print("\n--- talent_player_current ---")
    n = upload_table(client, 'talent_player_current', talent_records, batch_size=1000)
    print(f"  Uploaded: {n:,}")

    # 5e. talent_pa_detail
    print("\n--- talent_pa_detail ---")
    talent_pa_records = [{
        'pa_id': d['pa_id'],
        'player_id': d['player_id'],
        'player_role': d['player_role'],
        'talent_type': d['talent_type'],
        'elo_before': round(d['elo_before'], 4),
        'elo_after': round(d['elo_after'], 4),
    } for d in talent_batch.talent_pa_details]
    n = upload_table(client, 'talent_pa_detail', talent_pa_records, batch_size=1000)
    print(f"  Uploaded: {n:,}")

    # 5f. talent_daily_ohlc
    print("\n--- talent_daily_ohlc ---")
    talent_ohlc_records = [{
        'player_id': o['player_id'],
        'game_date': o['game_date'],
        'talent_type': o['talent_type'],
        'elo_type': o['elo_type'],
        'open': round(o['open'], 4),
        'high': round(o['high'], 4),
        'low': round(o['low'], 4),
        'close': round(o['close'], 4),
        'total_pa': o['total_pa'],
    } for o in talent_batch.talent_daily_ohlc]
    n = upload_table(client, 'talent_daily_ohlc', talent_ohlc_records, batch_size=1000)
    print(f"  Uploaded: {n:,}")
```

### Step 4: Run all tests

```bash
pytest tests/ -v
```
Expected: ALL existing + new tests PASS

### Step 5: Commit

```bash
git add scripts/run_elo.py tests/test_talent_pipeline_260130.py
git commit -m "feat(pipeline): integrate 9D talent batch into run_elo.py"
```

---

## Verification Checklist

After all tasks complete:

1. **All tests pass**: `pytest tests/ -v` — ALL GREEN
2. **Config loads**: `python -c "from src.engine.multi_elo_config import MultiEloConfig; c = MultiEloConfig(); print(c.version)"`
3. **Engine works**: `python -c "from src.engine.multi_elo_engine import MultiEloEngine; print('OK')"`
4. **No import errors**: `python -c "from src.engine.talent_batch import TalentBatch; print('OK')"`
5. **Existing tests unbroken**: `pytest tests/test_elo_engine.py tests/test_elo_batch.py tests/test_engine_v53_upgrade.py tests/test_k_modulation_260130171427.py -v`

## Storage Estimate

Per 2025 season (183,092 PAs, 1,469 players):
- `talent_player_current`: 1,469 × 9 = ~13K rows (~1 MB)
- `talent_pa_detail`: 183K × ~7 dims avg = ~1.3M rows (~100 MB)
- `talent_daily_ohlc`: 69K × 9 = ~620K rows (~50 MB)
- **Total: ~151 MB** (vs 59 MB composite-only → 2.5× increase)

## Files Created/Modified Summary

| File | Action |
|------|--------|
| `config/multi_elo_config.yaml` | CREATE |
| `src/engine/multi_elo_config.py` | CREATE |
| `src/engine/multi_elo_types.py` | CREATE |
| `src/engine/talent_state_manager.py` | CREATE |
| `src/engine/multi_elo_engine.py` | CREATE |
| `src/engine/talent_batch.py` | CREATE |
| `scripts/migrations/004_talent_schema.sql` | CREATE |
| `scripts/run_elo.py` | MODIFY |
| `tests/test_talent_config_260130.py` | CREATE |
| `tests/test_talent_types_260130.py` | CREATE |
| `tests/test_talent_state_mgr_260130.py` | CREATE |
| `tests/test_talent_engine_260130.py` | CREATE |
| `tests/test_talent_batch_260130.py` | CREATE |
| `tests/test_talent_pipeline_260130.py` | CREATE |
