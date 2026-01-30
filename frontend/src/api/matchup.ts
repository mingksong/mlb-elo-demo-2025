import { supabase } from '../lib/supabase';
import type { BatterTalentElo, PitcherTalentElo } from '../types/matchup';

export async function getBatterTalentElo(playerId: number): Promise<BatterTalentElo> {
  const { data, error } = await supabase
    .from('talent_player_current')
    .select('player_id, talent_type, season_elo, players!inner(full_name, team)')
    .eq('player_id', playerId)
    .eq('player_role', 'batter')
    .in('talent_type', ['contact', 'power', 'discipline']);

  if (error) throw error;

  const rows = (data ?? []) as Record<string, unknown>[];
  const player = rows[0]?.players as Record<string, unknown> | undefined;

  const eloMap: Record<string, number> = {};
  for (const row of rows) {
    eloMap[row.talent_type as string] = row.season_elo as number;
  }

  return {
    playerId,
    fullName: (player?.full_name as string) ?? '',
    team: (player?.team as string) ?? '',
    contact: eloMap['contact'] ?? 1500,
    power: eloMap['power'] ?? 1500,
    discipline: eloMap['discipline'] ?? 1500,
  };
}

export async function getPitcherTalentElo(playerId: number): Promise<PitcherTalentElo> {
  const { data, error } = await supabase
    .from('talent_player_current')
    .select('player_id, talent_type, season_elo, players!inner(full_name, team)')
    .eq('player_id', playerId)
    .eq('player_role', 'pitcher')
    .in('talent_type', ['stuff', 'bip_suppression', 'command']);

  if (error) throw error;

  const rows = (data ?? []) as Record<string, unknown>[];
  const player = rows[0]?.players as Record<string, unknown> | undefined;

  const eloMap: Record<string, number> = {};
  for (const row of rows) {
    eloMap[row.talent_type as string] = row.season_elo as number;
  }

  return {
    playerId,
    fullName: (player?.full_name as string) ?? '',
    team: (player?.team as string) ?? '',
    stuff: eloMap['stuff'] ?? 1500,
    bipSuppression: eloMap['bip_suppression'] ?? 1500,
    command: eloMap['command'] ?? 1500,
  };
}
