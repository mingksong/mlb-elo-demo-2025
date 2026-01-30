# Talent ELO Frontend Design

**Date:** 2026-01-30
**Phase:** Phase 9 — Talent ELO Frontend

## Goal

Add 9-dimensional talent ELO UI to the MLB ELO frontend: TalentCard on PlayerProfile + dedicated Talent Leaderboard page with 9 dimension tabs.

## Decisions

| Decision | Choice |
|----------|--------|
| Scope | TalentCard on PlayerProfile + Talent Leaderboard |
| Leaderboard structure | 9 tabs (one per dimension) |
| Route | `/talent-leaderboard` with "Talent" nav link |
| Rank/percentile | Supabase RPC function |
| Labels | English (US MLB fans target) |

## Architecture

```
talent_player_current (Supabase)
  ├─ RPC: get_player_talent_radar(player_id)
  │   → returns dimensions with season_elo, rank, percentile
  │   → React Query → TalentCardSection → TalentCard
  │
  └─ Direct query: filtered by talent_type, ordered by season_elo
      → paginated leaderboard
      → React Query → TalentLeaderboardTable
```

## New Files

| File | Purpose |
|------|---------|
| `scripts/migrations/005_talent_rpc.sql` | RPC function for rank/percentile |
| `frontend/src/types/talent.ts` | TalentType, TalentDimension, TalentMeta |
| `frontend/src/api/talent.ts` | Supabase queries for talent data |
| `frontend/src/hooks/useTalent.ts` | React Query wrappers |
| `frontend/src/components/player/TalentCard.tsx` | Single dimension card |
| `frontend/src/components/player/TalentCardSection.tsx` | Cards container for PlayerProfile |
| `frontend/src/components/talent/TalentLeaderboardTable.tsx` | Paginated leaderboard table |
| `frontend/src/pages/TalentLeaderboard.tsx` | New page with 9 dimension tabs |

## Modified Files

| File | Change |
|------|--------|
| `frontend/src/pages/PlayerProfile.tsx` | Add TalentCardSection between ELO card and chart |
| `frontend/src/components/common/Header.tsx` | Add "Talent" nav link |
| `frontend/src/App.tsx` | Add `/talent-leaderboard` route |

## Supabase RPC Function

```sql
CREATE OR REPLACE FUNCTION get_player_talent_radar(p_player_id INTEGER)
RETURNS TABLE (
  talent_type VARCHAR, player_role VARCHAR,
  season_elo REAL, career_elo REAL,
  season_rank BIGINT, career_rank BIGINT,
  total_in_role BIGINT
)
```

- Ranks computed via `RANK() OVER (PARTITION BY talent_type, player_role ORDER BY season_elo DESC)`
- Percentile computed in frontend: `Math.round((1 - rank/total) * 100)`

## TypeScript Types

```typescript
type TalentType = 'contact' | 'power' | 'discipline' | 'speed' | 'clutch'
               | 'stuff' | 'bip_suppression' | 'command' | 'pitcher_clutch';

interface TalentDimension {
  talentType: TalentType;
  playerRole: 'batter' | 'pitcher';
  seasonElo: number;
  careerElo: number;
  seasonRank: number | null;
  careerRank: number | null;
  totalPlayers: number;
}
```

## Components

### TalentCard

```
┌─────────────┐
│  ⚡ POWER    │  ← icon + label
│    1,587     │  ← ELO (tier color)
│  #12/284     │  ← rank
│   Top 4%     │  ← percentile
└─────────────┘
```

- Reuses `getEloTier()` / `getEloTierColor()` from `types/elo.ts`
- English labels: Contact, Power, Discipline, Speed, Clutch, Stuff, BIP Supp., Command, Clutch

### TalentCardSection

- Inserted between ELO card and OHLC chart on PlayerProfile
- Shows batter 5D or pitcher 4D based on active role tab
- Skeleton loading UI
- Horizontal scroll on mobile

### TalentLeaderboardTable

- Paginated table (20/page), same pattern as existing LeaderboardTable
- Columns: Rank, Player, Team, ELO, PA, Top %
- Queries talent_player_current with players join

### TalentLeaderboard Page

```
Header tabs: [ Contact | Power | Discipline | Speed | Clutch | Stuff | BIP Supp. | Command | P.Clutch ]
```

- Mobile: horizontal scroll tabs
- Default: Contact tab
- URL query param: `/talent-leaderboard?type=power`
- Visual separator between batter (5) and pitcher (4) dimensions

### Header Navigation

```
Daily | Leaderboard | Talent | Guide
```
