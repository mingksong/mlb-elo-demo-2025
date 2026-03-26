"""pybaseball Statcast wrapper for daily ELO pipeline.

Regular Season (game_type == 'R') 데이터만 수집.
"""

import logging
import time
from datetime import date, timedelta

import pandas as pd
from pybaseball import statcast

logger = logging.getLogger(__name__)

FETCH_MAX_RETRIES = 3
FETCH_RETRY_DELAY = 10  # seconds


def get_yesterday() -> date:
    """어제 날짜 반환."""
    return date.today() - timedelta(days=1)


def _fetch_with_retry(date_str: str, max_retries: int = FETCH_MAX_RETRIES) -> pd.DataFrame:
    """pybaseball statcast 호출 + 재시도. 일시적 API 실패 방지."""
    for attempt in range(1, max_retries + 1):
        try:
            df = statcast(start_dt=date_str, end_dt=date_str)
            if df is not None and not df.empty:
                return df
            if attempt < max_retries:
                logger.info(f"  Attempt {attempt}/{max_retries}: empty response, retrying in {FETCH_RETRY_DELAY}s...")
                time.sleep(FETCH_RETRY_DELAY)
            else:
                logger.info(f"  All {max_retries} attempts returned empty data")
                return pd.DataFrame()
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"  Attempt {attempt}/{max_retries} failed: {e}, retrying in {FETCH_RETRY_DELAY}s...")
                time.sleep(FETCH_RETRY_DELAY)
            else:
                logger.error(f"  All {max_retries} attempts failed. Last error: {e}")
                raise
    return pd.DataFrame()


def fetch_statcast_date(target_date: date) -> pd.DataFrame:
    """특정 날짜의 Statcast 데이터를 가져와 Regular Season만 필터링.

    Args:
        target_date: 수집할 날짜

    Returns:
        Regular Season 투구 데이터 DataFrame. 데이터 없으면 empty DataFrame.
    """
    date_str = target_date.strftime('%Y-%m-%d')
    logger.info(f"Fetching Statcast data for {date_str}...")

    df = _fetch_with_retry(date_str)

    if df.empty:
        logger.info(f"  No Statcast data for {date_str} (no games or data not yet available)")
        return pd.DataFrame()

    # Regular Season 필터 (game_type == 'R')
    if 'game_type' in df.columns:
        total = len(df)
        game_types = df['game_type'].value_counts().to_dict()
        logger.info(f"  Total pitches: {total:,}, game types: {game_types}")
        df = df[df['game_type'] == 'R']
        logger.info(f"  Regular season filter: {len(df):,} / {total:,} pitches")
    else:
        logger.warning(f"  No game_type column — returning all {len(df):,} pitches")

    if df.empty:
        logger.info(f"  No regular season data for {date_str}")
        return pd.DataFrame()

    return df.reset_index(drop=True)


def fetch_statcast_range(start_date: date, end_date: date) -> pd.DataFrame:
    """날짜 범위의 Statcast 데이터를 가져와 Regular Season만 필터링.

    Args:
        start_date: 시작 날짜 (inclusive)
        end_date: 종료 날짜 (inclusive)

    Returns:
        Regular Season 투구 데이터 DataFrame. 데이터 없으면 empty DataFrame.
    """
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    logger.info(f"Fetching Statcast data for {start_str} ~ {end_str}...")

    df = statcast(start_dt=start_str, end_dt=end_str)

    if df is None or df.empty:
        logger.info(f"  No data for {start_str} ~ {end_str}")
        return pd.DataFrame()

    # Regular Season 필터
    if 'game_type' in df.columns:
        before = len(df)
        df = df[df['game_type'] == 'R']
        logger.info(f"  Regular season filter: {len(df):,} / {before:,} pitches")
    else:
        logger.warning(f"  No game_type column — returning all {len(df):,} pitches")

    if df.empty:
        logger.info(f"  No regular season data for range")
        return pd.DataFrame()

    return df.reset_index(drop=True)
