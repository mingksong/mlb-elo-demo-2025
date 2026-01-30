import { supabase } from '../lib/supabase';
import type { PlayerTalentRadar, TalentDimension, TalentLeaderboardPlayer } from '../types/talent';
import { toUiTalentType } from '../types/talent';

export async function getPlayerTalentRadar(playerId: string): Promise<PlayerTalentRadar> {
  const { data, error } = await supabase.rpc('get_player_talent_radar', {
    p_player_id: parseInt(playerId, 10),
  });

  if (error) throw error;

  const dimensions: TalentDimension[] = (data ?? []).map((row: Record<string, unknown>) => ({
    talentType: toUiTalentType(row.talent_type as string, row.player_role as string),
    playerRole: row.player_role as 'batter' | 'pitcher',
    seasonElo: row.season_elo as number,
    careerElo: row.career_elo as number,
    seasonRank: row.season_rank as number | null,
    careerRank: row.career_rank as number | null,
    totalPlayers: row.total_in_role as number,
  }));

  return {
    playerId: parseInt(playerId, 10),
    dimensions,
  };
}

export interface TalentLeaderboardParams {
  talentType: string;
  playerRole: string;
  page?: number;
  limit?: number;
}

export async function getTalentLeaderboard(params: TalentLeaderboardParams): Promise<TalentLeaderboardPlayer[]> {
  const { talentType, playerRole, page = 1, limit = 20 } = params;
  const offset = (page - 1) * limit;

  const { data, error } = await supabase
    .from('talent_player_current')
    .select('player_id, season_elo, career_elo, pa_count, players!inner(full_name, team, position)')
    .eq('talent_type', talentType)
    .eq('player_role', playerRole)
    .order('season_elo', { ascending: false })
    .range(offset, offset + limit - 1);

  if (error) throw error;

  return (data ?? []).map((row: Record<string, unknown>) => {
    const p = row.players as Record<string, unknown>;
    return {
      player_id: row.player_id as number,
      season_elo: row.season_elo as number,
      career_elo: row.career_elo as number,
      pa_count: row.pa_count as number,
      full_name: p.full_name as string,
      team: p.team as string,
      position: p.position as string,
    };
  });
}
