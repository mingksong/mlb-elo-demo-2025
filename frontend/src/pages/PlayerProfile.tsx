import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, TrendingUp, TrendingDown } from 'lucide-react';
import EloCandlestickChart from '../components/player/EloCandlestickChart';
import { getEloTier, getEloTierColor } from '../types/elo';
import { getTeamBorderColor } from '../utils/teamColors';
import { usePlayerElo, usePlayerOhlc, usePlayerStats } from '../hooks/useElo';

export default function PlayerProfile() {
  const { playerId } = useParams<{ playerId: string }>();

  const { data: playerElo, isLoading: eloLoading } = usePlayerElo(playerId ?? '');
  const { data: ohlcData, isLoading: ohlcLoading } = usePlayerOhlc(playerId ?? '');
  const { data: playerStats, isLoading: statsLoading } = usePlayerStats(playerId ?? '');

  const isLoading = eloLoading || ohlcLoading || statsLoading;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Link to="/" className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900">
          <ArrowLeft className="w-5 h-5" />
          Back
        </Link>
        <div className="bg-white rounded-lg shadow-sm p-6 animate-pulse">
          <div className="flex items-start gap-6">
            <div className="w-20 h-20 bg-gray-200 rounded-full"></div>
            <div className="flex-1">
              <div className="h-8 bg-gray-200 rounded w-48 mb-2"></div>
              <div className="h-4 bg-gray-200 rounded w-32"></div>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg shadow-sm p-6 h-[400px] animate-pulse">
          <div className="h-full bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (!playerElo) {
    return (
      <div className="space-y-6">
        <Link to="/" className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900">
          <ArrowLeft className="w-5 h-5" />
          Back
        </Link>
        <div className="bg-white rounded-lg shadow-sm p-6 text-center text-gray-500">
          Player not found
        </div>
      </div>
    );
  }

  const { player, composite_elo, pa_count } = playerElo;
  const tier = getEloTier(composite_elo);
  const tierColor = getEloTierColor(tier);
  const teamColor = getTeamBorderColor(player.team);

  // Compute daily delta from latest OHLC
  const latestOhlc = ohlcData && ohlcData.length > 0 ? ohlcData[ohlcData.length - 1] : null;
  const delta = latestOhlc?.delta ?? 0;
  const DeltaIcon = delta > 0 ? TrendingUp : TrendingDown;
  const deltaColor = delta > 0 ? 'text-delta-up' : delta < 0 ? 'text-delta-down' : 'text-gray-500';
  const deltaSign = delta > 0 ? '+' : '';

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Link to="/" className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900">
        <ArrowLeft className="w-5 h-5" />
        Back
      </Link>

      {/* Player Header */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-start gap-6">
          {/* Team Badge */}
          <div
            className="w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold text-white"
            style={{ backgroundColor: teamColor }}
          >
            {player.team}
          </div>

          {/* Player Info */}
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-gray-900">{player.full_name}</h1>
            <p className="text-gray-600">
              {player.team} | {player.position === 'pitcher' ? 'Pitcher' : 'Batter'}
            </p>
          </div>

          {/* ELO Stats */}
          <div className="text-center p-4 rounded-lg bg-primary/10 ring-2 ring-primary">
            <div className="text-sm text-gray-500 mb-1">Season ELO</div>
            <div className={`text-3xl font-bold ${tierColor}`}>
              {Math.round(composite_elo)}
            </div>
            <div className={`flex items-center justify-center gap-1 ${deltaColor} mt-1`}>
              <DeltaIcon className="w-4 h-4" />
              <span>{deltaSign}{Math.round(delta)}</span>
            </div>
            <div className="text-xs text-gray-400 mt-1">{pa_count} PA</div>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <h3 className="text-lg font-semibold mb-4">Season ELO History</h3>
        <EloCandlestickChart data={ohlcData ?? []} height={400} />
      </div>

      {/* Season Stats */}
      {playerStats && (
        <div className="bg-white rounded-lg shadow-sm p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Season Statistics</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div>
              <div className="text-sm text-gray-500">Total PA</div>
              <div className="text-xl font-bold text-gray-900">{playerStats.totalPa}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Avg Delta/Day</div>
              <div className={`text-xl font-bold ${playerStats.avgDelta >= 0 ? 'text-delta-up' : 'text-delta-down'}`}>
                {playerStats.avgDelta >= 0 ? '+' : ''}{playerStats.avgDelta.toFixed(1)}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Highest ELO</div>
              <div className="text-xl font-bold text-elo-elite">{Math.round(playerStats.highestElo.value)}</div>
              <div className="text-xs text-gray-400">{playerStats.highestElo.date}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Lowest ELO</div>
              <div className="text-xl font-bold text-elo-cold">{Math.round(playerStats.lowestElo.value)}</div>
              <div className="text-xs text-gray-400">{playerStats.lowestElo.date}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Avg Range</div>
              <div className="text-xl font-bold text-gray-900">{playerStats.avgRange.toFixed(1)}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
