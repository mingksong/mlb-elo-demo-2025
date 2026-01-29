"""
V5.3 ELO Calculator (MLB 포팅)

KBO V5.3 Zero-Sum ELO Engine의 MLB 포팅.
delta_run_exp(Run Expectancy 변화량)를 사용한 단일 차원 ELO.

핵심 공식:
  batter_delta = K × delta_run_exp
  pitcher_delta = -K × delta_run_exp  (Zero-Sum)

Key Features:
  - True Zero-Sum: batter_delta = -pitcher_delta
  - K=12.0 for stable daily volatility
  - MIN_ELO=500 (하한선)
  - delta_run_exp는 Statcast RE24 기반 (상태 정규화 내장)
"""

from dataclasses import dataclass
from typing import Optional

from src.engine.elo_config import INITIAL_ELO, MIN_ELO, K_FACTOR


@dataclass
class PlayerEloState:
    """선수 ELO 상태."""
    player_id: int
    elo: float = INITIAL_ELO
    pa_count: int = 0
    cumulative_rv: float = 0.0

    def apply_delta(self, delta: float) -> None:
        """ELO 변화 적용 (하한선 보장)."""
        self.elo = max(MIN_ELO, self.elo + delta)


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

    def __init__(self, k_factor: float = K_FACTOR):
        self.k_factor = k_factor

    def process_plate_appearance(
        self,
        batter: PlayerEloState,
        pitcher: PlayerEloState,
        delta_run_exp: Optional[float],
    ) -> EloUpdateResult:
        """
        타석 결과 처리.

        Args:
            batter: 타자 ELO 상태
            pitcher: 투수 ELO 상태
            delta_run_exp: Run Expectancy 변화량 (None이면 ELO 변화 없음)

        Returns:
            EloUpdateResult
        """
        batter_elo_before = batter.elo
        pitcher_elo_before = pitcher.elo

        if delta_run_exp is not None:
            batter_delta = self.k_factor * delta_run_exp
            pitcher_delta = -batter_delta  # Zero-Sum

            batter.apply_delta(batter_delta)
            pitcher.apply_delta(pitcher_delta)

            batter.cumulative_rv += delta_run_exp
            pitcher.cumulative_rv -= delta_run_exp
        else:
            batter_delta = 0.0
            pitcher_delta = 0.0

        batter.pa_count += 1
        pitcher.pa_count += 1

        return EloUpdateResult(
            batter_delta=batter_delta,
            pitcher_delta=pitcher_delta,
            batter_elo_before=batter_elo_before,
            batter_elo_after=batter.elo,
            pitcher_elo_before=pitcher_elo_before,
            pitcher_elo_after=pitcher.elo,
        )
