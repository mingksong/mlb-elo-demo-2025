"""
V5.3 ELO Calculator (MLB 포팅)

KBO V5.3 Zero-Sum ELO Engine의 MLB 포팅.
delta_run_exp(Run Expectancy 변화량)를 사용한 단일 차원 ELO.

핵심 공식 (V5.3 Full):
  adjusted_rv  = delta_run_exp - park_adjustment
  rv_diff      = adjusted_rv - mean_rv[state]
  batter_delta = K × rv_diff
  pitcher_delta = -K × rv_diff  (Zero-Sum)

Key Features:
  - True Zero-Sum: batter_delta = -pitcher_delta
  - State normalization: base-out state별 기대 RV 보정
  - Park factor: 구장별 scoring environment 보정
  - Field error handling: 에러 시 타자 유리한 ELO 변동 차단
  - K=12.0 for stable daily volatility
  - MIN_ELO=500 (하한선)
"""

from dataclasses import dataclass
from typing import Optional

from src.engine.elo_config import INITIAL_ELO, MIN_ELO, K_FACTOR


@dataclass
class PlayerEloState:
    """선수 ELO 상태 (Two-Way Player 지원: batting/pitching 분리)."""
    player_id: int
    batting_elo: float = INITIAL_ELO
    pitching_elo: float = INITIAL_ELO
    batting_pa: int = 0
    pitching_pa: int = 0
    cumulative_rv: float = 0.0

    @property
    def elo(self) -> float:
        """하위 호환용 composite ELO (가중 평균)."""
        total = self.batting_pa + self.pitching_pa
        if total == 0:
            return INITIAL_ELO
        return (self.batting_elo * self.batting_pa +
                self.pitching_elo * self.pitching_pa) / total

    @property
    def pa_count(self) -> int:
        """하위 호환용 총 PA."""
        return self.batting_pa + self.pitching_pa

    def apply_batting_delta(self, delta: float) -> None:
        """타자 ELO 변화 적용 (하한선 보장)."""
        self.batting_elo = max(MIN_ELO, self.batting_elo + delta)

    def apply_pitching_delta(self, delta: float) -> None:
        """투수 ELO 변화 적용 (하한선 보장)."""
        self.pitching_elo = max(MIN_ELO, self.pitching_elo + delta)


@dataclass
class EloUpdateResult:
    """타석 ELO 업데이트 결과."""
    batter_delta: float
    pitcher_delta: float
    batter_elo_before: float
    batter_elo_after: float
    pitcher_elo_before: float
    pitcher_elo_after: float


class EloCalculator:
    """V5.3 ELO 계산기."""

    def __init__(self, k_factor: float = K_FACTOR,
                 re24_baseline=None, park_factor_obj=None):
        self.k_factor = k_factor
        self.re24_baseline = re24_baseline      # RE24Baseline or None
        self.park_factor = park_factor_obj      # ParkFactor or None

    def process_plate_appearance(
        self,
        batter: PlayerEloState,
        pitcher: PlayerEloState,
        delta_run_exp: Optional[float],
        state: int = 0,
        home_team: Optional[str] = None,
        result_type: Optional[str] = None,
    ) -> EloUpdateResult:
        """
        타석 결과 처리.

        Args:
            batter: 타자 ELO 상태
            pitcher: 투수 ELO 상태
            delta_run_exp: Run Expectancy 변화량 (None이면 ELO 변화 없음)
            state: base-out state (0~23)
            home_team: 홈팀 약칭 (park factor용)
            result_type: 결과 타입 ('E' 등 field error 감지용)

        Returns:
            EloUpdateResult
        """
        batter_elo_before = batter.batting_elo
        pitcher_elo_before = pitcher.pitching_elo

        if delta_run_exp is not None:
            # Step 1: Park factor adjustment
            if self.park_factor and home_team:
                adjusted_rv = self.park_factor.adjust_rv(delta_run_exp, home_team)
            else:
                adjusted_rv = delta_run_exp

            # Step 2: State normalization
            if self.re24_baseline:
                expected_rv = self.re24_baseline.get_expected_rv(state)
                rv_diff = adjusted_rv - expected_rv
            else:
                rv_diff = adjusted_rv

            # Step 3: ELO delta
            batter_delta = self.k_factor * rv_diff
            pitcher_delta = -batter_delta

            # Step 4: Field error handling
            if result_type and result_type.upper() in ('E', 'FIELD_ERROR'):
                if batter_delta > 0:
                    batter_delta = 0.0
                if pitcher_delta < 0:
                    pitcher_delta = 0.0

            batter.apply_batting_delta(batter_delta)
            pitcher.apply_pitching_delta(pitcher_delta)

            batter.cumulative_rv += delta_run_exp
            pitcher.cumulative_rv -= delta_run_exp
        else:
            batter_delta = 0.0
            pitcher_delta = 0.0

        batter.batting_pa += 1
        pitcher.pitching_pa += 1

        return EloUpdateResult(
            batter_delta=batter_delta,
            pitcher_delta=pitcher_delta,
            batter_elo_before=batter_elo_before,
            batter_elo_after=batter.batting_elo,
            pitcher_elo_before=pitcher_elo_before,
            pitcher_elo_after=pitcher.pitching_elo,
        )
