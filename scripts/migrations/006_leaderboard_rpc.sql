-- Phase 10: Leaderboard RPC functions with season-specific PA
-- Fixes: PA column showed lifetime cumulative instead of season-specific counts

-- 1. Main ELO Leaderboard
CREATE OR REPLACE FUNCTION get_leaderboard(
  p_role TEXT,
  p_season INTEGER,
  p_limit INTEGER DEFAULT 20,
  p_offset INTEGER DEFAULT 0
) RETURNS TABLE (
  player_id INTEGER,
  composite_elo REAL,
  batting_elo REAL,
  pitching_elo REAL,
  season_pa BIGINT,
  batting_pa INTEGER,
  pitching_pa INTEGER,
  last_game_date DATE,
  full_name VARCHAR,
  team VARCHAR,
  "position" VARCHAR
) AS $$
  SELECT
    pe.player_id,
    pe.composite_elo,
    pe.batting_elo,
    pe.pitching_elo,
    COALESCE(SUM(d.total_pa), 0)::BIGINT AS season_pa,
    pe.batting_pa,
    pe.pitching_pa,
    pe.last_game_date,
    p.full_name,
    p.team,
    p.position
  FROM player_elo pe
  JOIN players p ON pe.player_id = p.player_id
  LEFT JOIN daily_ohlc d ON d.player_id = pe.player_id
    AND d.elo_type = 'SEASON'
    AND d.role = CASE WHEN p_role = 'pitcher' THEN 'PITCHING' ELSE 'BATTING' END
    AND d.game_date >= make_date(p_season, 1, 1)
    AND d.game_date <= make_date(p_season, 12, 31)
  WHERE
    CASE WHEN p_role = 'pitcher' THEN pe.pitching_pa ELSE pe.batting_pa END > 0
    AND pe.last_game_date >= make_date(p_season, 1, 1)
    AND pe.last_game_date <= make_date(p_season, 12, 31)
  GROUP BY pe.player_id, pe.composite_elo, pe.batting_elo, pe.pitching_elo,
           pe.batting_pa, pe.pitching_pa, pe.last_game_date,
           p.full_name, p.team, p.position
  ORDER BY CASE WHEN p_role = 'pitcher' THEN pe.pitching_elo ELSE pe.batting_elo END DESC
  LIMIT p_limit
  OFFSET p_offset;
$$ LANGUAGE sql STABLE;

-- 2. Talent ELO Leaderboard
CREATE OR REPLACE FUNCTION get_talent_leaderboard(
  p_talent_type TEXT,
  p_player_role TEXT,
  p_season INTEGER,
  p_limit INTEGER DEFAULT 20,
  p_offset INTEGER DEFAULT 0
) RETURNS TABLE (
  player_id INTEGER,
  season_elo REAL,
  career_elo REAL,
  season_pa BIGINT,
  full_name VARCHAR,
  team VARCHAR,
  "position" VARCHAR
) AS $$
  SELECT
    tc.player_id,
    tc.season_elo,
    tc.career_elo,
    COALESCE(SUM(td.total_pa), 0)::BIGINT AS season_pa,
    p.full_name,
    p.team,
    p.position
  FROM talent_player_current tc
  JOIN players p ON tc.player_id = p.player_id
  JOIN player_elo pe ON tc.player_id = pe.player_id
  LEFT JOIN talent_daily_ohlc td ON td.player_id = tc.player_id
    AND td.talent_type = tc.talent_type
    AND td.elo_type = 'SEASON'
    AND td.game_date >= make_date(p_season, 1, 1)
    AND td.game_date <= make_date(p_season, 12, 31)
  WHERE
    tc.talent_type = p_talent_type
    AND tc.player_role = p_player_role
    AND pe.last_game_date >= make_date(p_season, 1, 1)
    AND pe.last_game_date <= make_date(p_season, 12, 31)
  GROUP BY tc.player_id, tc.season_elo, tc.career_elo,
           p.full_name, p.team, p.position
  ORDER BY tc.season_elo DESC
  LIMIT p_limit
  OFFSET p_offset;
$$ LANGUAGE sql STABLE;
