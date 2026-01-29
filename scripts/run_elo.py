"""
V5.3 ELO 전체 시즌 실행 파이프라인

1. Supabase에서 PA 데이터 로드
2. ELO 배치 계산
3. 결과 업로드 (player_elo, elo_pa_detail, daily_ohlc)
4. 검증

Usage:
    python -m scripts.run_elo
"""

import logging
import math
import os
import sys

import pandas as pd
from dotenv import load_dotenv

# Setup
logging.basicConfig(level=logging.INFO, format='%(message)s')
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.engine.elo_batch import EloBatch
from src.engine.elo_config import INITIAL_ELO
from src.etl.upload_to_supabase import get_supabase_client, upload_table


def load_pa_from_supabase(client) -> pd.DataFrame:
    """Supabase에서 전체 PA 데이터 로드 (정렬: game_date, pa_id)."""
    print("Loading PA data from Supabase...")

    all_rows = []
    page_size = 1000
    offset = 0

    while True:
        response = (
            client.table('plate_appearances')
            .select('pa_id, game_pk, game_date, batter_id, pitcher_id, result_type, delta_run_exp')
            .order('game_date')
            .order('pa_id')
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

    df = pd.DataFrame(all_rows)
    print(f"  Loaded {len(df):,} PAs")
    return df


def prepare_pa_detail_records(pa_details: list[dict]) -> list[dict]:
    """elo_pa_detail 레코드 변환."""
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


def prepare_ohlc_records(daily_ohlc) -> list[dict]:
    """daily_ohlc 레코드 변환."""
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
        })
    return records


def print_summary(batch: EloBatch):
    """결과 요약."""
    print("\n" + "=" * 60)
    print("V5.3 ELO CALCULATION SUMMARY")
    print("=" * 60)

    players = batch.players
    elos = [p.elo for p in players.values()]

    print(f"\nPlayers: {len(players):,}")
    print(f"PA Details: {len(batch.pa_details):,}")
    print(f"OHLC Records: {len(batch.daily_ohlc):,}")

    # ELO distribution
    print(f"\nELO Distribution:")
    print(f"  Mean: {sum(elos) / len(elos):.1f}")
    print(f"  Min: {min(elos):.1f}")
    print(f"  Max: {max(elos):.1f}")

    # Standard deviation
    mean_elo = sum(elos) / len(elos)
    var = sum((e - mean_elo) ** 2 for e in elos) / len(elos)
    std = var ** 0.5
    print(f"  Std: {std:.1f}")

    # Zero-sum check
    total_delta = sum(p.elo - INITIAL_ELO for p in players.values())
    print(f"\nZero-Sum Check:")
    print(f"  Net ELO change: {total_delta:+.2f}")

    # Top 10 batters (by ELO, PA >= 100)
    batter_ids = set()
    pitcher_ids = set()
    for d in batch.pa_details:
        batter_ids.add(d['batter_id'])
        pitcher_ids.add(d['pitcher_id'])

    # Batters with PA >= 100
    top_batters = sorted(
        [(pid, p) for pid, p in players.items()
         if pid in batter_ids and p.pa_count >= 100],
        key=lambda x: -x[1].elo
    )[:10]

    print(f"\nTop 10 Batters (PA ≥ 100):")
    for pid, p in top_batters:
        print(f"  {pid}: ELO={p.elo:.1f} (PA={p.pa_count}, RV={p.cumulative_rv:+.1f})")

    # Top 10 pitchers (by ELO, PA >= 100)
    top_pitchers = sorted(
        [(pid, p) for pid, p in players.items()
         if pid in pitcher_ids and pid not in batter_ids and p.pa_count >= 100],
        key=lambda x: -x[1].elo
    )[:10]

    print(f"\nTop 10 Pitchers (BFP ≥ 100):")
    for pid, p in top_pitchers:
        print(f"  {pid}: ELO={p.elo:.1f} (BFP={p.pa_count}, RV={p.cumulative_rv:+.1f})")


def main():
    print("=" * 60)
    print("V5.3 ELO Full Season Pipeline")
    print("=" * 60)

    # 1. Load PA data
    client = get_supabase_client()
    pa_df = load_pa_from_supabase(client)

    # 2. Run ELO calculation
    print("\nRunning ELO calculation...")
    batch = EloBatch()
    batch.process(pa_df)

    # 3. Summary
    print_summary(batch)

    # 4. Upload results
    print("\n" + "=" * 60)
    print("UPLOADING RESULTS TO SUPABASE")
    print("=" * 60)

    # 4a. player_elo
    print("\n--- player_elo ---")
    player_records = batch.get_player_elo_records()
    n = upload_table(client, 'player_elo', player_records, batch_size=500)
    print(f"  Uploaded: {n:,}")

    # 4b. elo_pa_detail
    print("\n--- elo_pa_detail ---")
    pa_detail_records = prepare_pa_detail_records(batch.pa_details)
    n = upload_table(client, 'elo_pa_detail', pa_detail_records, batch_size=1000)
    print(f"  Uploaded: {n:,}")

    # 4c. daily_ohlc
    print("\n--- daily_ohlc ---")
    ohlc_records = prepare_ohlc_records(batch.daily_ohlc)
    n = upload_table(client, 'daily_ohlc', ohlc_records, batch_size=1000)
    print(f"  Uploaded: {n:,}")

    # 5. Verify
    print("\n--- Verification ---")
    r = client.table('player_elo').select('player_id', count='exact').execute()
    print(f"  player_elo: {r.count} rows")
    r = client.table('elo_pa_detail').select('pa_id', count='exact').execute()
    print(f"  elo_pa_detail: {r.count} rows")
    r = client.table('daily_ohlc').select('id', count='exact').execute()
    print(f"  daily_ohlc: {r.count} rows")

    print("\nDone!")


if __name__ == '__main__':
    main()
