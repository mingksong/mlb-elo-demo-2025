import { supabase } from '../lib/supabase';
import type { HotColdPlayer, PlayerElo, Player, DailyOhlc, PlayerStats, LeagueSummary, PlayerSearchResult, SeasonMeta } from '../types/elo';

export async function getHotPlayers(date: string): Promise<HotColdPlayer[]> {
  const { data, error } = await supabase
    .from('daily_ohlc')
    .select('player_id, game_date, open, high, low, close, delta, total_pa, players!inner(full_name, team, position)')
    .eq('game_date', date)
    .eq('elo_type', 'SEASON')
    .order('delta', { ascending: false })
    .limit(10);

  if (error) throw error;

  return (data ?? []).map((row: Record<string, unknown>) => {
    const p = row.players as Record<string, unknown>;
    return {
      player_id: row.player_id as number,
      game_date: row.game_date as string,
      open: row.open as number,
      high: row.high as number,
      low: row.low as number,
      close: row.close as number,
      delta: row.delta as number,
      total_pa: row.total_pa as number,
      full_name: p.full_name as string,
      team: p.team as string,
      position: p.position as string,
    };
  });
}

export async function getColdPlayers(date: string): Promise<HotColdPlayer[]> {
  const { data, error } = await supabase
    .from('daily_ohlc')
    .select('player_id, game_date, open, high, low, close, delta, total_pa, players!inner(full_name, team, position)')
    .eq('game_date', date)
    .eq('elo_type', 'SEASON')
    .order('delta', { ascending: true })
    .limit(10);

  if (error) throw error;

  return (data ?? []).map((row: Record<string, unknown>) => {
    const p = row.players as Record<string, unknown>;
    return {
      player_id: row.player_id as number,
      game_date: row.game_date as string,
      open: row.open as number,
      high: row.high as number,
      low: row.low as number,
      close: row.close as number,
      delta: row.delta as number,
      total_pa: row.total_pa as number,
      full_name: p.full_name as string,
      team: p.team as string,
      position: p.position as string,
    };
  });
}

export interface LeaderboardParams {
  position?: string;
  page?: number;
  limit?: number;
}

export interface LeaderboardPlayer {
  player_id: number;
  composite_elo: number;
  batting_elo: number;
  pitching_elo: number;
  pa_count: number;
  batting_pa: number;
  pitching_pa: number;
  last_game_date: string;
  full_name: string;
  team: string;
  position: string;
}

export async function getLeaderboard(params: LeaderboardParams): Promise<LeaderboardPlayer[]> {
  const { position, page = 1, limit = 20 } = params;
  const offset = (page - 1) * limit;

  // Sort by role-appropriate ELO
  const sortColumn = position === 'pitcher' ? 'pitching_elo' : 'batting_elo';
  // Filter by role-specific PA > 0 (TWP appear in both tabs)
  const paColumn = position === 'pitcher' ? 'pitching_pa' : 'batting_pa';

  let query = supabase
    .from('player_elo')
    .select('player_id, composite_elo, batting_elo, pitching_elo, pa_count, batting_pa, pitching_pa, last_game_date, players!inner(full_name, team, position)')
    .gt(paColumn, 0)
    .order(sortColumn, { ascending: false })
    .range(offset, offset + limit - 1);

  const { data, error } = await query;

  if (error) throw error;

  return (data ?? []).map((row: Record<string, unknown>) => {
    const p = row.players as Record<string, unknown>;
    return {
      player_id: row.player_id as number,
      composite_elo: row.composite_elo as number,
      batting_elo: (row.batting_elo as number) ?? 1500,
      pitching_elo: (row.pitching_elo as number) ?? 1500,
      pa_count: row.pa_count as number,
      batting_pa: (row.batting_pa as number) ?? 0,
      pitching_pa: (row.pitching_pa as number) ?? 0,
      last_game_date: row.last_game_date as string,
      full_name: p.full_name as string,
      team: p.team as string,
      position: p.position as string,
    };
  });
}

export async function getPlayerElo(playerId: string): Promise<PlayerElo & { player: Player }> {
  const { data, error } = await supabase
    .from('player_elo')
    .select('player_id, composite_elo, batting_elo, pitching_elo, pa_count, batting_pa, pitching_pa, last_game_date, players!inner(player_id, full_name, team, position)')
    .eq('player_id', playerId)
    .single();

  if (error) throw error;

  const p = data.players as unknown as Record<string, unknown>;
  return {
    player_id: data.player_id,
    composite_elo: data.composite_elo,
    batting_elo: data.batting_elo ?? 1500,
    pitching_elo: data.pitching_elo ?? 1500,
    pa_count: data.pa_count,
    batting_pa: data.batting_pa ?? 0,
    pitching_pa: data.pitching_pa ?? 0,
    last_game_date: data.last_game_date,
    player: {
      player_id: p.player_id as number,
      full_name: p.full_name as string,
      team: p.team as string,
      position: p.position as string,
    },
  };
}

export async function getPlayerOhlc(playerId: string, role?: string): Promise<DailyOhlc[]> {
  let query = supabase
    .from('daily_ohlc')
    .select('game_date, open, high, low, close, delta, total_pa, role')
    .eq('player_id', playerId)
    .eq('elo_type', 'SEASON')
    .order('game_date');

  if (role) {
    query = query.eq('role', role);
  }

  const { data, error } = await query;

  if (error) throw error;
  return (data ?? []) as DailyOhlc[];
}

export async function getPlayerStats(playerId: string, role?: string): Promise<PlayerStats> {
  const ohlcData = await getPlayerOhlc(playerId, role);

  if (ohlcData.length === 0) {
    return {
      totalPa: 0,
      avgDelta: 0,
      highestElo: { value: 1500, date: '' },
      lowestElo: { value: 1500, date: '' },
      avgRange: 0,
    };
  }

  const totalPa = ohlcData.reduce((sum, d) => sum + d.total_pa, 0);
  const avgDelta = ohlcData.reduce((sum, d) => sum + d.delta, 0) / ohlcData.length;

  let highest = { value: -Infinity, date: '' };
  let lowest = { value: Infinity, date: '' };
  let rangeSum = 0;

  for (const d of ohlcData) {
    if (d.high > highest.value) {
      highest = { value: d.high, date: d.game_date };
    }
    if (d.low < lowest.value) {
      lowest = { value: d.low, date: d.game_date };
    }
    rangeSum += d.high - d.low;
  }

  return {
    totalPa,
    avgDelta,
    highestElo: highest,
    lowestElo: lowest,
    avgRange: rangeSum / ohlcData.length,
  };
}

export async function searchPlayers(query: string): Promise<PlayerSearchResult[]> {
  if (query.length < 2) return [];

  const { data, error } = await supabase
    .from('players')
    .select('player_id, full_name, team, position, player_elo(batting_pa, pitching_pa)')
    .ilike('full_name', `%${query}%`)
    .limit(10);

  if (error) throw error;
  return (data ?? []).map((row: Record<string, unknown>) => {
    const elo = row.player_elo as Record<string, unknown> | null;
    return {
      player_id: row.player_id as number,
      full_name: row.full_name as string,
      team: row.team as string,
      position: row.position as string,
      is_two_way: elo ? ((elo.batting_pa as number) > 0 && (elo.pitching_pa as number) > 0) : false,
    };
  });
}

export async function getLeagueSummary(): Promise<LeagueSummary> {
  const { data, error } = await supabase
    .from('player_elo')
    .select('composite_elo');

  if (error) throw error;

  const players = data ?? [];
  const count = players.length;
  const avgElo = count > 0
    ? Math.round(players.reduce((sum, p) => sum + (p.composite_elo as number), 0) / count)
    : 1500;
  const eliteCount = players.filter(p => (p.composite_elo as number) >= 1800).length;

  return {
    activePlayersCount: count,
    averageElo: avgElo,
    eliteCount,
  };
}

export async function getLatestDate(): Promise<string> {
  const { data, error } = await supabase
    .from('daily_ohlc')
    .select('game_date')
    .order('game_date', { ascending: false })
    .limit(1);

  if (error) throw error;
  return data?.[0]?.game_date ?? new Date().toISOString().slice(0, 10);
}

export async function getSeasonMeta(): Promise<SeasonMeta> {
  const [earliest, latest] = await Promise.all([
    supabase
      .from('daily_ohlc')
      .select('game_date')
      .order('game_date', { ascending: true })
      .limit(1),
    supabase
      .from('daily_ohlc')
      .select('game_date')
      .order('game_date', { ascending: false })
      .limit(1),
  ]);

  if (earliest.error) throw earliest.error;
  if (latest.error) throw latest.error;

  const startDate = earliest.data?.[0]?.game_date ?? '';
  const endDate = latest.data?.[0]?.game_date ?? '';
  const year = startDate ? new Date(startDate).getFullYear() : new Date().getFullYear();

  return { year, startDate, endDate };
}
