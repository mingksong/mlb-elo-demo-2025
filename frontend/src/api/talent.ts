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
  season?: number;
}

export async function getTalentLeaderboard(params: TalentLeaderboardParams): Promise<TalentLeaderboardPlayer[]> {
  const { talentType, playerRole, page = 1, limit = 20, season } = params;
  const offset = (page - 1) * limit;
  const currentYear = season ?? new Date().getFullYear();

  const { data, error } = await supabase.rpc('get_talent_leaderboard', {
    p_talent_type: talentType,
    p_player_role: playerRole,
    p_season: currentYear,
    p_limit: limit,
    p_offset: offset,
  });

  if (error) throw error;

  return (data ?? []).map((row: Record<string, unknown>) => ({
    player_id: row.player_id as number,
    season_elo: row.season_elo as number,
    career_elo: row.career_elo as number,
    season_pa: (row.season_pa as number) ?? 0,
    full_name: row.full_name as string,
    team: row.team as string,
    position: row.position as string,
  }));
}
