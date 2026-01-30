# Talent ELO Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 9-dimensional talent ELO display to PlayerProfile and a dedicated Talent Leaderboard page with 9 dimension tabs.

**Architecture:** Supabase RPC function computes per-player talent rank/percentile server-side. Frontend queries via React Query hooks, renders TalentCard components on PlayerProfile and a paginated TalentLeaderboard page. Direct Supabase queries for leaderboard (no RPC needed — simple ORDER BY).

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, TanStack React Query 5, Supabase JS SDK, Lucide React icons, React Router 7

---

## Context

### DB Schema (already exists)

```sql
-- talent_player_current (6,857 rows)
-- PK: (player_id, talent_type, player_role)
-- Columns: player_id, player_role, talent_type, season_elo, career_elo, event_count, pa_count
```

**talent_type values in DB:**
- Batter (673 players each): `contact`, `power`, `discipline`, `speed`, `clutch`
- Pitcher (873 players each): `stuff`, `bip_suppression`, `command`, `clutch`

Note: `clutch` appears for both roles — differentiated by `player_role` (`batter` or `pitcher`).

### Existing Patterns

- **API pattern**: `frontend/src/api/elo.ts` — async functions querying `supabase` client, returning typed objects
- **Hook pattern**: `frontend/src/hooks/useElo.ts` — `useQuery` wrappers with `queryKey`, `queryFn`, `enabled`, `staleTime`
- **Leaderboard pattern**: `frontend/src/pages/Leaderboard.tsx` — tabs + paginated table + pagination controls
- **Tier colors**: `getEloTier(elo)` / `getEloTierColor(tier)` in `frontend/src/types/elo.ts`

---

## Task 1: Supabase RPC Function

**Files:**
- Create: `scripts/migrations/005_talent_rpc.sql`

**Step 1: Write the SQL migration**

Create `scripts/migrations/005_talent_rpc.sql`:

```sql
-- Phase 9: Talent ELO RPC function for rank/percentile
CREATE OR REPLACE FUNCTION get_player_talent_radar(p_player_id INTEGER)
RETURNS TABLE (
  talent_type VARCHAR,
  player_role VARCHAR,
  season_elo REAL,
  career_elo REAL,
  season_rank BIGINT,
  career_rank BIGINT,
  total_in_role BIGINT
) AS $$
BEGIN
  RETURN QUERY
  WITH ranked AS (
    SELECT
      t.talent_type,
      t.player_role,
      t.season_elo,
      t.career_elo,
      RANK() OVER (
        PARTITION BY t.talent_type, t.player_role
        ORDER BY t.season_elo DESC
      ) AS season_rank,
      RANK() OVER (
        PARTITION BY t.talent_type, t.player_role
        ORDER BY t.career_elo DESC
      ) AS career_rank,
      COUNT(*) OVER (
        PARTITION BY t.talent_type, t.player_role
      ) AS total_in_role
    FROM talent_player_current t
  )
  SELECT
    ranked.talent_type,
    ranked.player_role,
    ranked.season_elo,
    ranked.career_elo,
    ranked.season_rank,
    ranked.career_rank,
    ranked.total_in_role
  FROM ranked
  WHERE ranked.talent_type IN (
    SELECT tc.talent_type FROM talent_player_current tc WHERE tc.player_id = p_player_id
  )
  AND ranked.player_role IN (
    SELECT tc.player_role FROM talent_player_current tc WHERE tc.player_id = p_player_id
  )
  AND ranked.talent_type || ranked.player_role IN (
    SELECT tc.talent_type || tc.player_role FROM talent_player_current tc WHERE tc.player_id = p_player_id
  )
  -- Only return this player's rows
  AND EXISTS (
    SELECT 1 FROM talent_player_current tc
    WHERE tc.player_id = p_player_id
      AND tc.talent_type = ranked.talent_type
      AND tc.player_role = ranked.player_role
  );
END;
$$ LANGUAGE plpgsql STABLE;
```

Wait — that's overly complex. Simpler approach: compute rank for ALL players in the window function, then filter to the requested player_id.

Actually the simplest correct version:

```sql
CREATE OR REPLACE FUNCTION get_player_talent_radar(p_player_id INTEGER)
RETURNS TABLE (
  talent_type VARCHAR,
  player_role VARCHAR,
  season_elo REAL,
  career_elo REAL,
  season_rank BIGINT,
  career_rank BIGINT,
  total_in_role BIGINT
) AS $$
  SELECT
    sub.talent_type,
    sub.player_role,
    sub.season_elo,
    sub.career_elo,
    sub.season_rank,
    sub.career_rank,
    sub.total_in_role
  FROM (
    SELECT
      t.player_id,
      t.talent_type,
      t.player_role,
      t.season_elo,
      t.career_elo,
      RANK() OVER (PARTITION BY t.talent_type, t.player_role ORDER BY t.season_elo DESC) AS season_rank,
      RANK() OVER (PARTITION BY t.talent_type, t.player_role ORDER BY t.career_elo DESC) AS career_rank,
      COUNT(*) OVER (PARTITION BY t.talent_type, t.player_role) AS total_in_role
    FROM talent_player_current t
  ) sub
  WHERE sub.player_id = p_player_id;
$$ LANGUAGE sql STABLE;
```

**Step 2: User runs migration on Supabase**

Tell user to run this SQL in Supabase SQL Editor.

**Step 3: Verify RPC works**

Run from Python:
```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
from src.etl.upload_to_supabase import get_supabase_client
client = get_supabase_client()
r = client.rpc('get_player_talent_radar', {'p_player_id': 660271}).execute()
for row in r.data:
    print(row)
"
```

Expected: 5 rows (if batter) or 4 rows (if pitcher) or 9 rows (if TWP) with season_rank, career_rank, total_in_role populated.

**Step 4: Commit**

```bash
git add scripts/migrations/005_talent_rpc.sql
git commit -m "feat(db): add get_player_talent_radar RPC function (005)"
```

---

## Task 2: TypeScript Types

**Files:**
- Create: `frontend/src/types/talent.ts`

**Step 1: Create types file**

Create `frontend/src/types/talent.ts`:

```typescript
export type TalentType =
  | 'contact'
  | 'power'
  | 'discipline'
  | 'speed'
  | 'clutch'
  | 'stuff'
  | 'bip_suppression'
  | 'command'
  | 'pitcher_clutch'; // UI-only alias for pitcher's clutch

// DB talent_type values (clutch is shared, differentiated by player_role)
export type DbTalentType =
  | 'contact'
  | 'power'
  | 'discipline'
  | 'speed'
  | 'clutch'
  | 'stuff'
  | 'bip_suppression'
  | 'command';

export interface TalentDimension {
  talentType: TalentType;
  playerRole: 'batter' | 'pitcher';
  seasonElo: number;
  careerElo: number;
  seasonRank: number | null;
  careerRank: number | null;
  totalPlayers: number;
}

export interface PlayerTalentRadar {
  playerId: number;
  dimensions: TalentDimension[];
}

export interface TalentMeta {
  type: TalentType;
  dbType: DbTalentType;
  label: string;
  icon: string;
  role: 'batter' | 'pitcher';
}

export const BATTER_TALENTS: TalentMeta[] = [
  { type: 'contact', dbType: 'contact', label: 'Contact', icon: 'Hand', role: 'batter' },
  { type: 'power', dbType: 'power', label: 'Power', icon: 'Zap', role: 'batter' },
  { type: 'discipline', dbType: 'discipline', label: 'Discipline', icon: 'Eye', role: 'batter' },
  { type: 'speed', dbType: 'speed', label: 'Speed', icon: 'Gauge', role: 'batter' },
  { type: 'clutch', dbType: 'clutch', label: 'Clutch', icon: 'Trophy', role: 'batter' },
];

export const PITCHER_TALENTS: TalentMeta[] = [
  { type: 'stuff', dbType: 'stuff', label: 'Stuff', icon: 'Sparkles', role: 'pitcher' },
  { type: 'bip_suppression', dbType: 'bip_suppression', label: 'BIP Supp.', icon: 'Shield', role: 'pitcher' },
  { type: 'command', dbType: 'command', label: 'Command', icon: 'Crosshair', role: 'pitcher' },
  { type: 'pitcher_clutch', dbType: 'clutch', label: 'Clutch', icon: 'Trophy', role: 'pitcher' },
];

export const ALL_TALENTS: TalentMeta[] = [...BATTER_TALENTS, ...PITCHER_TALENTS];

export function getTalentMeta(talentType: TalentType): TalentMeta | undefined {
  return ALL_TALENTS.find(t => t.type === talentType);
}

/** Convert DB row (talent_type + player_role) to UI TalentType */
export function toUiTalentType(dbType: string, playerRole: string): TalentType {
  if (dbType === 'clutch' && playerRole === 'pitcher') return 'pitcher_clutch';
  return dbType as TalentType;
}

/** Leaderboard entry from talent_player_current */
export interface TalentLeaderboardPlayer {
  player_id: number;
  season_elo: number;
  career_elo: number;
  pa_count: number;
  full_name: string;
  team: string;
  position: string;
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors related to `types/talent.ts`.

**Step 3: Commit**

```bash
git add frontend/src/types/talent.ts
git commit -m "feat(frontend): add talent ELO TypeScript types"
```

---

## Task 3: API + Hooks

**Files:**
- Create: `frontend/src/api/talent.ts`
- Create: `frontend/src/hooks/useTalent.ts`

**Step 1: Create talent API**

Create `frontend/src/api/talent.ts`:

```typescript
import { supabase } from '../lib/supabase';
import type { PlayerTalentRadar, TalentDimension, TalentLeaderboardPlayer, TalentMeta } from '../types/talent';
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
  talentType: string;     // DB talent_type value (e.g., 'contact', 'clutch')
  playerRole: string;     // 'batter' or 'pitcher'
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
```

**Step 2: Create talent hooks**

Create `frontend/src/hooks/useTalent.ts`:

```typescript
import { useQuery } from '@tanstack/react-query';
import * as talentApi from '../api/talent';
import type { TalentLeaderboardParams } from '../api/talent';

export function usePlayerTalentRadar(playerId: string) {
  return useQuery({
    queryKey: ['playerTalentRadar', playerId],
    queryFn: () => talentApi.getPlayerTalentRadar(playerId),
    enabled: !!playerId,
    staleTime: 60_000,
  });
}

export function useTalentLeaderboard(params: TalentLeaderboardParams) {
  return useQuery({
    queryKey: ['talentLeaderboard', params],
    queryFn: () => talentApi.getTalentLeaderboard(params),
    staleTime: 60_000,
  });
}
```

**Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

**Step 4: Commit**

```bash
git add frontend/src/api/talent.ts frontend/src/hooks/useTalent.ts
git commit -m "feat(frontend): add talent API + React Query hooks"
```

---

## Task 4: TalentCard Component

**Files:**
- Create: `frontend/src/components/player/TalentCard.tsx`

**Step 1: Create TalentCard**

Create `frontend/src/components/player/TalentCard.tsx`:

```tsx
import { Hand, Zap, Eye, Gauge, Trophy, Sparkles, Shield, Crosshair } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { getEloTier, getEloTierColor } from '../../types/elo';

const ICON_MAP: Record<string, LucideIcon> = {
  Hand, Zap, Eye, Gauge, Trophy, Sparkles, Shield, Crosshair,
};

interface TalentCardProps {
  label: string;
  iconName: string;
  elo: number;
  rank: number | null;
  totalPlayers: number;
  percentile: number | null;
}

export default function TalentCard({ label, iconName, elo, rank, totalPlayers, percentile }: TalentCardProps) {
  const Icon = ICON_MAP[iconName] || Hand;
  const tier = getEloTier(elo);
  const tierColor = getEloTierColor(tier);
  const topPercent = percentile !== null ? Math.round(100 - percentile) : null;

  return (
    <div className="bg-white rounded-lg shadow-sm p-3 text-center min-w-[100px] flex-1">
      <div className="flex items-center justify-center gap-1 mb-1">
        <Icon className="w-4 h-4 text-gray-400" />
        <span className="text-xs text-gray-500 uppercase tracking-wide font-medium">
          {label}
        </span>
      </div>
      <div className={`text-2xl font-bold ${tierColor}`}>
        {Math.round(elo).toLocaleString()}
      </div>
      <div className="text-xs text-gray-500 mt-1">
        {rank !== null && totalPlayers > 0 && (
          <span>#{rank}/{totalPlayers}</span>
        )}
        {topPercent !== null && topPercent > 0 && (
          <span className="ml-1">Top {topPercent}%</span>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

**Step 3: Commit**

```bash
git add frontend/src/components/player/TalentCard.tsx
git commit -m "feat(frontend): add TalentCard component"
```

---

## Task 5: TalentCardSection + PlayerProfile Integration

**Files:**
- Create: `frontend/src/components/player/TalentCardSection.tsx`
- Modify: `frontend/src/pages/PlayerProfile.tsx`

**Step 1: Create TalentCardSection**

Create `frontend/src/components/player/TalentCardSection.tsx`:

```tsx
import { usePlayerTalentRadar } from '../../hooks/useTalent';
import TalentCard from './TalentCard';
import { BATTER_TALENTS, PITCHER_TALENTS, getTalentMeta } from '../../types/talent';
import type { TalentDimension } from '../../types/talent';

interface TalentCardSectionProps {
  playerId: string;
  position: 'batter' | 'pitcher';
}

export default function TalentCardSection({ playerId, position }: TalentCardSectionProps) {
  const { data: talentData, isLoading } = usePlayerTalentRadar(playerId);

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow-sm p-4">
        <div className="flex gap-3 overflow-x-auto">
          {Array.from({ length: position === 'pitcher' ? 4 : 5 }).map((_, i) => (
            <div key={i} className="bg-gray-100 rounded-lg p-3 min-w-[100px] flex-1 animate-pulse">
              <div className="h-4 bg-gray-200 rounded mb-2" />
              <div className="h-8 bg-gray-200 rounded mb-1" />
              <div className="h-3 bg-gray-200 rounded w-2/3 mx-auto" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!talentData || talentData.dimensions.length === 0) {
    return null;
  }

  const relevantTalents = position === 'pitcher' ? PITCHER_TALENTS : BATTER_TALENTS;

  const sortedDimensions = relevantTalents
    .map(talent => talentData.dimensions.find(d => d.talentType === talent.type))
    .filter((d): d is TalentDimension => d !== undefined);

  if (sortedDimensions.length === 0) return null;

  return (
    <div className="bg-white rounded-lg shadow-sm p-4">
      <h3 className="text-sm font-medium text-gray-500 mb-3">
        {position === 'pitcher' ? 'Pitching' : 'Batting'} Talent
      </h3>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {sortedDimensions.map((dim) => {
          const meta = getTalentMeta(dim.talentType);
          if (!meta) return null;

          const percentile = dim.totalPlayers > 0 && dim.seasonRank !== null
            ? ((1 - dim.seasonRank / dim.totalPlayers) * 100)
            : null;

          return (
            <TalentCard
              key={dim.talentType}
              label={meta.label}
              iconName={meta.icon}
              elo={dim.seasonElo}
              rank={dim.seasonRank}
              totalPlayers={dim.totalPlayers}
              percentile={percentile}
            />
          );
        })}
      </div>
    </div>
  );
}
```

**Step 2: Modify PlayerProfile.tsx**

In `frontend/src/pages/PlayerProfile.tsx`:

Add import at top (after existing imports):
```typescript
import TalentCardSection from '../components/player/TalentCardSection';
```

Insert TalentCardSection between the TWP Role Tabs section and the Chart+Stats section.

Find line (approximately line 233):
```tsx
      {/* Chart + Stats (role-filtered) */}
      <RoleSection playerId={playerId ?? ''} role={currentRole} />
```

Insert BEFORE it:
```tsx
      {/* Talent Cards */}
      <TalentCardSection
        playerId={playerId ?? ''}
        position={currentRole === 'PITCHING' ? 'pitcher' : 'batter'}
      />
```

**Step 3: Verify TypeScript compiles and build succeeds**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

**Step 4: Commit**

```bash
git add frontend/src/components/player/TalentCardSection.tsx frontend/src/pages/PlayerProfile.tsx
git commit -m "feat(frontend): add TalentCardSection to PlayerProfile"
```

---

## Task 6: TalentLeaderboardTable Component

**Files:**
- Create: `frontend/src/components/talent/TalentLeaderboardTable.tsx`

**Step 1: Create the component**

Create directory `frontend/src/components/talent/` if needed.

Create `frontend/src/components/talent/TalentLeaderboardTable.tsx`:

```tsx
import { useNavigate } from 'react-router-dom';
import type { TalentLeaderboardPlayer } from '../../types/talent';
import { getEloTier, getEloTierColor } from '../../types/elo';
import TeamLogo from '../common/TeamLogo';

interface TalentLeaderboardTableProps {
  players: TalentLeaderboardPlayer[];
  isLoading?: boolean;
  startRank?: number;
  totalInDimension?: number;
}

export default function TalentLeaderboardTable({
  players,
  isLoading = false,
  startRank = 1,
  totalInDimension = 0,
}: TalentLeaderboardTableProps) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50">
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">#</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Player</th>
            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Team</th>
            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">ELO</th>
            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">PA</th>
            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">Top %</th>
          </tr>
        </thead>
        <tbody>
          {isLoading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="animate-pulse border-b border-gray-50">
                <td colSpan={6} className="px-4 py-4">
                  <div className="h-5 bg-gray-200 rounded w-full"></div>
                </td>
              </tr>
            ))
          ) : players.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                No players found
              </td>
            </tr>
          ) : (
            players.map((player, index) => (
              <TalentLeaderboardRow
                key={player.player_id}
                player={player}
                rank={startRank + index}
                totalInDimension={totalInDimension}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function TalentLeaderboardRow({
  player,
  rank,
  totalInDimension,
}: {
  player: TalentLeaderboardPlayer;
  rank: number;
  totalInDimension: number;
}) {
  const navigate = useNavigate();
  const tier = getEloTier(player.season_elo);
  const tierColor = getEloTierColor(tier);
  const topPercent = totalInDimension > 0 ? Math.round((rank / totalInDimension) * 100) : null;

  return (
    <tr
      onClick={() => navigate(`/player/${player.player_id}`)}
      className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
    >
      <td className="px-4 py-3 text-sm font-bold text-gray-400">{rank}</td>
      <td className="px-4 py-3 text-sm font-semibold text-gray-900">
        {player.full_name}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        <div className="flex items-center gap-1.5">
          <TeamLogo size={20} />
          {player.team}
        </div>
      </td>
      <td className={`px-4 py-3 text-sm font-bold text-right ${tierColor}`}>
        {Math.round(player.season_elo)}
      </td>
      <td className="px-4 py-3 text-sm text-right text-gray-500">{player.pa_count}</td>
      <td className="px-4 py-3 text-sm text-right text-gray-500">
        {topPercent !== null ? `${topPercent}%` : '—'}
      </td>
    </tr>
  );
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

**Step 3: Commit**

```bash
git add frontend/src/components/talent/TalentLeaderboardTable.tsx
git commit -m "feat(frontend): add TalentLeaderboardTable component"
```

---

## Task 7: TalentLeaderboard Page + Routing + Header

**Files:**
- Create: `frontend/src/pages/TalentLeaderboard.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/common/Header.tsx`

**Step 1: Create TalentLeaderboard page**

Create `frontend/src/pages/TalentLeaderboard.tsx`:

```tsx
import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTalentLeaderboard } from '../hooks/useTalent';
import { useSeasonMeta } from '../hooks/useElo';
import TalentLeaderboardTable from '../components/talent/TalentLeaderboardTable';
import { ALL_TALENTS } from '../types/talent';
import type { TalentMeta } from '../types/talent';

const ESTIMATED_TOTAL: Record<string, number> = {
  batter: 673,
  pitcher: 873,
};

export default function TalentLeaderboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialType = searchParams.get('type') || 'contact';
  const initialTab = ALL_TALENTS.find(t => t.type === initialType) || ALL_TALENTS[0];

  const [activeTab, setActiveTab] = useState<TalentMeta>(initialTab);
  const [page, setPage] = useState(1);
  const limit = 20;

  const { data: players = [], isLoading } = useTalentLeaderboard({
    talentType: activeTab.dbType,
    playerRole: activeTab.role,
    page,
    limit,
  });

  const { data: seasonMeta } = useSeasonMeta();

  useEffect(() => {
    setPage(1);
    setSearchParams({ type: activeTab.type }, { replace: true });
  }, [activeTab, setSearchParams]);

  const isLastPage = players.length < limit;
  const estimatedTotalPages = Math.ceil((ESTIMATED_TOTAL[activeTab.role] || 500) / limit);
  const totalPages = isLastPage ? page : Math.max(page + 1, estimatedTotalPages);

  const visiblePages = useMemo(() => {
    const pages: number[] = [];
    let start = Math.max(1, page - 2);
    const end = Math.min(totalPages, start + 4);
    start = Math.max(1, end - 4);
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }, [page, totalPages]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Talent Leaderboard</h2>
        <span className="text-xs font-medium px-2 py-0.5 rounded bg-primary/10 text-primary">
          {seasonMeta?.year ?? ''} Season
        </span>
      </div>

      {/* Dimension Tabs */}
      <div className="flex gap-1 overflow-x-auto pb-2">
        {ALL_TALENTS.map((talent, index) => (
          <div key={talent.type} className="flex items-center">
            {/* Separator between batter and pitcher groups */}
            {index === 5 && (
              <div className="w-px h-6 bg-gray-300 mx-2 flex-shrink-0" />
            )}
            <button
              onClick={() => setActiveTab(talent)}
              className={`px-3 py-2 rounded-lg text-sm font-semibold transition-all whitespace-nowrap flex-shrink-0 ${
                activeTab.type === talent.type
                  ? 'bg-primary text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {talent.label}
            </button>
          </div>
        ))}
      </div>

      {/* Role indicator */}
      <div className="text-sm text-gray-500">
        {activeTab.role === 'batter' ? 'Batter' : 'Pitcher'} dimension
        {' · '}
        {ESTIMATED_TOTAL[activeTab.role] || '—'} players
      </div>

      {/* Table */}
      <TalentLeaderboardTable
        players={players}
        isLoading={isLoading}
        startRank={(page - 1) * limit + 1}
        totalInDimension={ESTIMATED_TOTAL[activeTab.role] || 0}
      />

      {/* Pagination (same pattern as Leaderboard.tsx) */}
      <div className="flex items-center justify-center gap-1 py-4">
        <button
          onClick={() => setPage(1)}
          disabled={page === 1}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          title="First page"
        >
          <ChevronFirst className="w-5 h-5" />
        </button>
        <button
          onClick={() => setPage(p => Math.max(1, p - 1))}
          disabled={page === 1}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          title="Previous page"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-1 mx-2">
          {visiblePages[0] > 1 && (
            <span className="px-2 text-gray-400">...</span>
          )}
          {visiblePages.map((p) => (
            <button
              key={p}
              onClick={() => setPage(p)}
              className={`min-w-[40px] h-10 rounded-lg font-semibold transition-all ${
                p === page
                  ? 'bg-primary text-white'
                  : 'hover:bg-gray-100 text-gray-700'
              }`}
            >
              {p}
            </button>
          ))}
          {visiblePages[visiblePages.length - 1] < totalPages && (
            <span className="px-2 text-gray-400">...</span>
          )}
        </div>
        <button
          onClick={() => setPage(p => p + 1)}
          disabled={isLastPage}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          title="Next page"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
        <button
          onClick={() => setPage(totalPages)}
          disabled={isLastPage || page === totalPages}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
          title="Last page"
        >
          <ChevronLast className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
```

**Step 2: Add route to App.tsx**

In `frontend/src/App.tsx`:

Add import:
```typescript
import TalentLeaderboard from './pages/TalentLeaderboard';
```

Add route after the `/leaderboard` route:
```tsx
<Route path="/talent-leaderboard" element={<TalentLeaderboard />} />
```

**Step 3: Add "Talent" nav link to Header.tsx**

In `frontend/src/components/common/Header.tsx`:

Add after the Leaderboard link (between Leaderboard and Guide):
```tsx
          <Link
            to="/talent-leaderboard"
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              location.pathname === '/talent-leaderboard'
                ? 'bg-primary text-white'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            Talent
          </Link>
```

**Step 4: Verify build succeeds**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

**Step 5: Commit**

```bash
git add frontend/src/pages/TalentLeaderboard.tsx frontend/src/App.tsx frontend/src/components/common/Header.tsx
git commit -m "feat(frontend): add TalentLeaderboard page with 9 dimension tabs"
```

---

## Verification Checklist

After all tasks are complete:

1. `cd frontend && npm run build` succeeds
2. Run Supabase migration `005_talent_rpc.sql`
3. Open app → Navigate to player profile (e.g., Ohtani: player_id 660271)
   - Verify 5 batter talent cards displayed (Contact, Power, Discipline, Speed, Clutch)
   - Switch to Pitching tab → verify 4 pitcher talent cards (Stuff, BIP Supp., Command, Clutch)
   - Each card shows ELO, rank, Top %
4. Navigate to `/talent-leaderboard`
   - 9 tabs visible with separator between batter/pitcher groups
   - Table shows 20 players per page, paginated
   - Click player row → navigates to profile
   - URL updates with `?type=...` on tab switch
5. Header shows: Daily | Leaderboard | Talent | Guide
