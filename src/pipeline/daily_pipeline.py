"""Daily ELO Pipeline — 일일 증분 ELO 계산 오케스트레이터.

매일 자동으로 전일 Statcast 데이터를 가져와 증분 ELO를 계산하고 Supabase에 업로드.

Flow:
    1. Idempotency check (이미 처리된 날짜면 skip, force=True면 삭제 후 재처리)
    2. pybaseball fetch (Regular Season only)
    3. ETL: statcast_to_pa (기존 모듈 재사용)
    4. 신규 선수 감지 + 등록
    5. plate_appearances upsert
    6. 기존 ELO 상태 로드
    7. EloBatch(initial_states=...) → 증분 계산
    8. 결과 업로드: player_elo (active_only), elo_pa_detail, daily_ohlc
"""

import logging
from datetime import date

import pandas as pd

from src.engine.elo_batch import EloBatch
from src.engine.elo_calculator import PlayerEloState
from src.engine.elo_config import INITIAL_ELO
from src.engine.re24_baseline import RE24Baseline
from src.engine.park_factor import ParkFactor
from src.etl.fetch_statcast import fetch_statcast_date
from src.etl.statcast_to_pa import convert_statcast_to_pa
from src.etl.player_registry import detect_new_player_ids_batch, register_new_players
from src.etl.upload_to_supabase import get_supabase_client, upload_table, prepare_pa_records

logger = logging.getLogger(__name__)


def load_current_elo_states(client) -> dict[int, PlayerEloState]:
    """Supabase player_elo → PlayerEloState 복원.

    cumulative_rv는 0.0으로 리셋 (DB에 미저장, ELO 계산에 영향 없음).
    """
    logger.info("Loading current ELO states from Supabase...")
    all_rows = []
    page_size = 1000
    offset = 0

    while True:
        response = (
            client.table('player_elo')
            .select('player_id, composite_elo, pa_count, batting_elo, pitching_elo, batting_pa, pitching_pa')
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = response.data
        if not rows:
            break
        all_rows.extend(rows)
        offset += page_size
        if len(rows) < page_size:
            break

    states = {}
    for row in all_rows:
        pid = row['player_id']
        states[pid] = PlayerEloState(
            player_id=pid,
            batting_elo=row.get('batting_elo', INITIAL_ELO) or INITIAL_ELO,
            pitching_elo=row.get('pitching_elo', INITIAL_ELO) or INITIAL_ELO,
            batting_pa=row.get('batting_pa', 0) or 0,
            pitching_pa=row.get('pitching_pa', 0) or 0,
            cumulative_rv=0.0,
        )

    logger.info(f"  Loaded {len(states):,} player ELO states")
    return states


def delete_date_data(client, target_date: date):
    """날짜별 기존 데이터 삭제 (idempotent 재처리용).

    삭제 순서: elo_pa_detail → daily_ohlc → plate_appearances (FK 의존성).
    """
    date_str = target_date.isoformat()
    logger.info(f"Deleting existing data for {date_str}...")

    # 1. 해당 날짜 PA ID 목록 조회
    pa_ids = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            client.table('plate_appearances')
            .select('pa_id')
            .eq('game_date', date_str)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = response.data
        if not rows:
            break
        pa_ids.extend(r['pa_id'] for r in rows)
        offset += page_size
        if len(rows) < page_size:
            break

    if pa_ids:
        # 2. elo_pa_detail 삭제 (pa_id 기준)
        batch_size = 100
        for i in range(0, len(pa_ids), batch_size):
            batch = pa_ids[i:i + batch_size]
            client.table('elo_pa_detail').delete().in_('pa_id', batch).execute()
        logger.info(f"  Deleted {len(pa_ids)} elo_pa_detail records")

    # 3. daily_ohlc 삭제 (game_date 기준)
    client.table('daily_ohlc').delete().eq('game_date', date_str).execute()
    logger.info(f"  Deleted daily_ohlc for {date_str}")

    # 4. plate_appearances 삭제
    client.table('plate_appearances').delete().eq('game_date', date_str).execute()
    logger.info(f"  Deleted plate_appearances for {date_str}")


def _prepare_pa_detail_records(pa_details: list[dict]) -> list[dict]:
    """elo_pa_detail 레코드 변환 (run_elo.py 로직 재사용)."""
    records = []
    for d in pa_details:
        records.append({
            'pa_id': int(d['pa_id']),
            'batter_id': int(d['batter_id']),
            'pitcher_id': int(d['pitcher_id']),
            'result_type': d['result_type'],
            'batter_elo_before': round(d['batter_elo_before'], 4),
            'batter_elo_after': round(d['batter_elo_after'], 4),
            'pitcher_elo_before': round(d['pitcher_elo_before'], 4),
            'pitcher_elo_after': round(d['pitcher_elo_after'], 4),
            'on_base_delta': round(d['elo_delta'], 4),
            'power_delta': 0.0,
        })
    return records


def _prepare_ohlc_records(daily_ohlc) -> list[dict]:
    """daily_ohlc 레코드 변환 (run_elo.py 로직 재사용)."""
    records = []
    for ohlc in daily_ohlc:
        records.append({
            'player_id': int(ohlc.player_id),
            'game_date': ohlc.game_date.isoformat(),
            'elo_type': ohlc.elo_type,
            'open': round(ohlc.open_elo, 4),
            'high': round(ohlc.high_elo, 4),
            'low': round(ohlc.low_elo, 4),
            'close': round(ohlc.close_elo, 4),
            'games_played': ohlc.games_played,
            'total_pa': ohlc.total_pa,
            'role': ohlc.role,
        })
    return records


def run_daily_pipeline(target_date: date = None, force: bool = False) -> dict:
    """메인 파이프라인.

    Args:
        target_date: 처리할 날짜 (None이면 어제)
        force: True면 이미 처리된 날짜도 삭제 후 재처리

    Returns:
        dict with status and stats
    """
    from src.etl.fetch_statcast import get_yesterday

    if target_date is None:
        target_date = get_yesterday()

    date_str = target_date.isoformat()
    logger.info(f"=== Daily ELO Pipeline: {date_str} ===")

    client = get_supabase_client()

    # 1. Idempotency check
    existing = (
        client.table('plate_appearances')
        .select('pa_id', count='exact')
        .eq('game_date', date_str)
        .limit(1)
        .execute()
    )
    if existing.count and existing.count > 0:
        if force:
            logger.info(f"  Force mode: deleting existing {existing.count} PAs for {date_str}")
            delete_date_data(client, target_date)
        else:
            logger.info(f"  Already processed: {existing.count} PAs for {date_str}. Use --force to reprocess.")
            return {'status': 'already_processed', 'date': date_str, 'existing_pa_count': existing.count}

    # 2. Fetch Statcast
    statcast_df = fetch_statcast_date(target_date)
    if statcast_df.empty:
        logger.info(f"  No data for {date_str} (off-day or off-season)")
        return {'status': 'no_data', 'date': date_str}

    # 3. ETL: pitch → PA
    logger.info("  Converting pitches to plate appearances...")
    pa_df = convert_statcast_to_pa(statcast_df)
    logger.info(f"  {len(pa_df):,} plate appearances")

    if pa_df.empty:
        logger.info(f"  No PAs extracted for {date_str}")
        return {'status': 'no_pa', 'date': date_str}

    # 4. 신규 선수 감지 + 등록
    new_ids = detect_new_player_ids_batch(pa_df, client)
    new_player_count = 0
    if new_ids:
        new_player_count = register_new_players(new_ids, pa_df, client)

    # 5. plate_appearances upsert
    logger.info("  Uploading plate appearances...")
    pa_records = prepare_pa_records(pa_df)
    pa_uploaded = upload_table(client, 'plate_appearances', pa_records)

    # 6. 기존 ELO 상태 로드
    initial_states = load_current_elo_states(client)

    # 7. 증분 ELO 계산
    logger.info("  Running incremental ELO calculation...")
    baseline = RE24Baseline()
    park_factor = ParkFactor()
    batch = EloBatch(
        re24_baseline=baseline,
        park_factor=park_factor,
        initial_states=initial_states,
    )
    batch.process(pa_df)

    # 8. 결과 업로드
    # 8a. player_elo (active_only=True → 당일 활동 선수만)
    logger.info("  Uploading player_elo (active only)...")
    player_records = batch.get_player_elo_records(active_only=True)
    elo_uploaded = upload_table(client, 'player_elo', player_records)

    # 8b. elo_pa_detail
    logger.info("  Uploading elo_pa_detail...")
    pa_detail_records = _prepare_pa_detail_records(batch.pa_details)
    detail_uploaded = upload_table(client, 'elo_pa_detail', pa_detail_records)

    # 8c. daily_ohlc
    logger.info("  Uploading daily_ohlc...")
    ohlc_records = _prepare_ohlc_records(batch.daily_ohlc)
    ohlc_uploaded = upload_table(client, 'daily_ohlc', ohlc_records)

    result = {
        'status': 'success',
        'date': date_str,
        'pitches_fetched': len(statcast_df),
        'pa_count': len(pa_df),
        'new_players': new_player_count,
        'active_players': len(batch._active_player_ids),
        'pa_uploaded': pa_uploaded,
        'elo_uploaded': elo_uploaded,
        'detail_uploaded': detail_uploaded,
        'ohlc_uploaded': ohlc_uploaded,
    }
    logger.info(f"  === Done: {result} ===")
    return result
