import { useState } from 'react';
import { BookOpen, Code, ChevronDown, ChevronUp } from 'lucide-react';

type Tab = 'general' | 'developer';

function Accordion({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-4 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <span className="font-semibold text-gray-900">{title}</span>
        {isOpen ? (
          <ChevronUp className="w-5 h-5 text-gray-500" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-500" />
        )}
      </button>
      {isOpen && (
        <div className="px-5 py-4 space-y-3 text-gray-700 leading-relaxed">
          {children}
        </div>
      )}
    </div>
  );
}

function GeneralTab() {
  return (
    <div className="space-y-4">
      <Accordion title="What is ELO?" defaultOpen>
        <p>
          The <strong>ELO Rating System</strong> is a method originally designed to calculate
          the relative skill levels of chess players. We adapt this system to evaluate
          MLB players based on their <strong>plate appearance (PA) outcomes</strong>.
        </p>
        <p>
          Every player starts the season at <strong>1,500</strong> (league average).
          After each plate appearance, the batter and pitcher exchange ELO points
          based on the outcome — if the batter performs above expectation, they gain
          points while the pitcher loses the same amount, and vice versa.
        </p>
        <p>
          Over the course of a season, elite performers rise above 1,800 while
          struggling players may fall below 1,200. The system provides a single,
          intuitive number that captures a player's cumulative performance trajectory.
        </p>
      </Accordion>

      <Accordion title="Zero-Sum Principle">
        <p>
          Our ELO system follows a strict <strong>zero-sum</strong> design.
          For every plate appearance, the ELO points gained by one side are exactly
          equal to the points lost by the other:
        </p>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm space-y-1">
          <p>adjusted_rv  = delta_run_exp − park_adjustment</p>
          <p>rv_diff      = adjusted_rv − expected_rv[state]</p>
          <p>batter_delta = K × rv_diff</p>
          <p>pitcher_delta = −batter_delta</p>
        </div>
        <p>
          This means the league-wide average ELO always stays near 1,500.
          A player's rating only rises by outperforming opponents, not through
          inflation. Park factor and base-out state adjustments ensure fair
          comparison across stadiums and game situations.
        </p>
      </Accordion>

      <Accordion title="K-Factor & Run Value">
        <p>
          The <strong>K-Factor</strong> controls how much a single plate appearance
          can shift a player's ELO. We use <strong>K = 12</strong>.
        </p>
        <p>
          The key input is <strong>delta_run_exp</strong> (delta run expectancy),
          derived from MLB Statcast data. This measures how much a plate appearance
          outcome changed the expected runs scored. Before computing ELO, the raw
          value is adjusted for <strong>park factor</strong> (venue scoring environment)
          and <strong>state normalization</strong> (base-out situation average).
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>A home run might have delta_run_exp ≈ +1.4 → batter gains ~17 ELO</li>
          <li>A strikeout might have delta_run_exp ≈ −0.3 → batter loses ~4 ELO</li>
          <li>A walk might have delta_run_exp ≈ +0.3 → batter gains ~4 ELO</li>
          <li>At Coors Field (park factor 1.13), positive outcomes are adjusted down to account for the hitter-friendly park</li>
        </ul>
        <p>
          Higher-impact outcomes produce larger ELO swings, making the system
          responsive to both quality and frequency of plate appearances.
        </p>
      </Accordion>

      <Accordion title="ELO Tier Table">
        <p>
          Players are classified into tiers based on their current ELO rating:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="px-3 py-2 text-left font-semibold">Tier</th>
                <th className="px-3 py-2 text-left font-semibold">ELO Range</th>
                <th className="px-3 py-2 text-left font-semibold">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              <tr>
                <td className="px-3 py-2 font-bold text-elo-elite">Elite</td>
                <td className="px-3 py-2">1,800+</td>
                <td className="px-3 py-2">MVP-caliber performance</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-bold text-elo-high">High</td>
                <td className="px-3 py-2">1,650 – 1,799</td>
                <td className="px-3 py-2">All-Star level</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-bold text-elo-above">Above Avg</td>
                <td className="px-3 py-2">1,550 – 1,649</td>
                <td className="px-3 py-2">Above-average starter</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-bold text-elo-average">Average</td>
                <td className="px-3 py-2">1,450 – 1,549</td>
                <td className="px-3 py-2">League average</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-bold text-elo-below">Below Avg</td>
                <td className="px-3 py-2">1,350 – 1,449</td>
                <td className="px-3 py-2">Below-average performance</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-bold text-elo-low">Low</td>
                <td className="px-3 py-2">1,200 – 1,349</td>
                <td className="px-3 py-2">Struggling performance</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-bold text-elo-cold">Cold</td>
                <td className="px-3 py-2">&lt; 1,200</td>
                <td className="px-3 py-2">Significant slump</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Accordion>

      <Accordion title="Pitcher-Batter Balance">
        <p>
          The zero-sum design ensures a natural balance between pitchers and batters.
          When a batter gains ELO, the opposing pitcher loses the same amount.
        </p>
        <p>
          This creates an intuitive interpretation: a pitcher with high ELO has
          consistently limited batter production, while a batter with high ELO has
          consistently produced against pitchers. Both sides are measured on the
          same scale using the same Statcast-derived run values.
        </p>
        <p>
          The <strong>delta_run_exp</strong> metric from Statcast naturally captures
          this duality — it measures the run value change from the batter's perspective,
          and the pitcher's delta is simply the negative of that value.
        </p>
      </Accordion>

      <Accordion title="Reading the OHLC Chart">
        <p>
          Each player's profile includes an <strong>OHLC (Open-High-Low-Close)</strong> chart,
          similar to stock market candlestick charts:
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Open</strong>: ELO at the start of the day (first PA)</li>
          <li><strong>High</strong>: Highest ELO reached during the day</li>
          <li><strong>Low</strong>: Lowest ELO reached during the day</li>
          <li><strong>Close</strong>: ELO at the end of the day (last PA)</li>
        </ul>
        <p>
          <span className="text-green-600 font-semibold">Green candles</span> indicate
          the player's ELO rose that day (close &gt; open), while{' '}
          <span className="text-red-600 font-semibold">red candles</span> indicate
          a decline (close &lt; open). The "wick" shows the intraday range.
        </p>
        <p>
          Moving averages (MA5 and MA15) smooth out daily noise to reveal
          longer-term trends.
        </p>
      </Accordion>

      <Accordion title="Disclaimer">
        <p>
          This demo is based on <strong>2025 MLB Statcast data</strong> covering
          approximately <strong>183,000 plate appearances</strong> across the full season.
        </p>
        <p>
          The ELO ratings shown here are for demonstration and analytical purposes only.
          They represent one possible approach to player evaluation and should not be
          considered definitive assessments of player skill. Many factors (defense,
          baserunning, game context beyond run expectancy) are not captured by this model.
        </p>
        <p>
          Data sourced from MLB Statcast via Baseball Savant.
        </p>
      </Accordion>
    </div>
  );
}

function DeveloperTab() {
  return (
    <div className="space-y-4">
      <Accordion title="System Architecture" defaultOpen>
        <p>
          The MLB ELO system follows a simple pipeline architecture:
        </p>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm overflow-x-auto">
          <p>[Statcast Parquet] → ETL → [Supabase plate_appearances] → ELO Engine → [Supabase player_elo / daily_ohlc]</p>
        </div>
        <p>
          The system uses a <strong>V5.3 Zero-Sum</strong> ELO engine, ported from a KBO
          implementation with full feature parity:
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li>Single-dimension ELO (no separate talent/skill component)</li>
          <li>Single season (2025) — no year-over-year normalization</li>
          <li><strong>State normalization</strong> — adjusts for base-out situation (24 states)</li>
          <li><strong>Park factor</strong> — adjusts for venue scoring environment (30 stadiums)</li>
          <li><strong>Field error handling</strong> — prevents unearned ELO credit on errors</li>
          <li>Statcast delta_run_exp as the input metric</li>
        </ul>
      </Accordion>

      <Accordion title="ELO Calculation Formula (V5.3)">
        <p>
          For each plate appearance, the ELO update follows three steps:
        </p>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm space-y-2">
          <p className="text-gray-500"># Step 1: Park factor adjustment</p>
          <p><strong>adjusted_rv</strong> = delta_run_exp − (park_factor − 1.0) × 0.1</p>
          <p className="text-gray-500 mt-2"># Step 2: State normalization</p>
          <p><strong>rv_diff</strong> = adjusted_rv − mean_rv[base_out_state]</p>
          <p className="text-gray-500 mt-2"># Step 3: ELO update (zero-sum)</p>
          <p><strong>batter_delta</strong> = K × rv_diff</p>
          <p><strong>pitcher_delta</strong> = −batter_delta</p>
        </div>
        <p>Parameters:</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="px-3 py-2 text-left font-semibold">Parameter</th>
                <th className="px-3 py-2 text-left font-semibold">Value</th>
                <th className="px-3 py-2 text-left font-semibold">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              <tr>
                <td className="px-3 py-2 font-mono">K_FACTOR</td>
                <td className="px-3 py-2">12.0</td>
                <td className="px-3 py-2">Sensitivity — higher K means larger swings per PA</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">INITIAL_ELO</td>
                <td className="px-3 py-2">1500.0</td>
                <td className="px-3 py-2">Starting ELO for all players at season start</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">MIN_ELO</td>
                <td className="px-3 py-2">500.0</td>
                <td className="px-3 py-2">Floor — ELO cannot drop below this value</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">ADJUSTMENT_SCALE</td>
                <td className="px-3 py-2">0.1</td>
                <td className="px-3 py-2">Park factor RV adjustment scale</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2">
          <strong>State normalization</strong> removes systematic bias from base-out
          situations (24 states: 8 base configurations × 3 out states). For example,
          a hit with runners in scoring position carries a higher raw run value than
          with bases empty — the normalization ensures only above-average outcomes
          increase ELO.
        </p>
        <p>
          <strong>Field error handling</strong>: When the result is a fielding error,
          any favorable ELO gain for the batter is zeroed out to prevent unearned credit.
        </p>
      </Accordion>

      <Accordion title="Data Pipeline">
        <p>
          The data flows through three stages:
        </p>
        <h4 className="font-semibold mt-2">1. Raw Data (Statcast)</h4>
        <ul className="list-disc pl-5 space-y-1">
          <li>Source: MLB Statcast via Baseball Savant</li>
          <li>Format: Parquet file (~711K pitches, 118 columns)</li>
          <li>Coverage: 2025 season (2,428 games)</li>
        </ul>
        <h4 className="font-semibold mt-2">2. ETL (Pitch → PA)</h4>
        <ul className="list-disc pl-5 space-y-1">
          <li>Aggregate pitch-level data to plate appearance level</li>
          <li>Extract: batter_id, pitcher_id, game_date, delta_run_exp</li>
          <li>Result: ~183K plate appearances</li>
        </ul>
        <h4 className="font-semibold mt-2">3. ELO Engine (V5.3)</h4>
        <ul className="list-disc pl-5 space-y-1">
          <li>Load RE24 baseline (mean run value per base-out state) and park factors (30 venues)</li>
          <li>Process PAs chronologically (sorted by game_date, at_bat_number)</li>
          <li>Apply V5.3 formula: park adjustment → state normalization → zero-sum ELO</li>
          <li>Output: per-PA ELO detail + daily OHLC aggregation</li>
        </ul>
      </Accordion>

      <Accordion title="OHLC Tracking">
        <p>
          Daily OHLC (Open-High-Low-Close) values are computed for each player
          who had at least one plate appearance on a given day:
        </p>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm space-y-1">
          <p><strong>Open</strong>: ELO before the first PA of the day</p>
          <p><strong>High</strong>: Maximum ELO reached during the day</p>
          <p><strong>Low</strong>: Minimum ELO reached during the day</p>
          <p><strong>Close</strong>: ELO after the last PA of the day</p>
          <p><strong>Delta</strong>: Close − Open (daily change)</p>
        </div>
        <p>
          This allows visualization of daily ELO fluctuations using candlestick
          charts, making it easy to spot hot/cold streaks and turning points
          throughout the season.
        </p>
      </Accordion>

      <Accordion title="Database Schema">
        <p>
          The system uses Supabase (PostgreSQL) with the following key tables:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="px-3 py-2 text-left font-semibold">Table</th>
                <th className="px-3 py-2 text-left font-semibold">Rows</th>
                <th className="px-3 py-2 text-left font-semibold">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              <tr>
                <td className="px-3 py-2 font-mono">players</td>
                <td className="px-3 py-2">1,469</td>
                <td className="px-3 py-2">Player metadata (name, team, position)</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">plate_appearances</td>
                <td className="px-3 py-2">183,092</td>
                <td className="px-3 py-2">All PAs with delta_run_exp</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">player_elo</td>
                <td className="px-3 py-2">1,469</td>
                <td className="px-3 py-2">Current ELO + PA count per player</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">elo_pa_detail</td>
                <td className="px-3 py-2">183,092</td>
                <td className="px-3 py-2">Per-PA ELO change records</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-mono">daily_ohlc</td>
                <td className="px-3 py-2">69,125</td>
                <td className="px-3 py-2">Daily OHLC candlestick data per player</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Accordion>

      <Accordion title="Frontend Stack">
        <p>
          This demo frontend is a static SPA that reads directly from Supabase:
        </p>
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Vite + React + TypeScript</strong> — build toolchain</li>
          <li><strong>Tailwind CSS</strong> — utility-first styling</li>
          <li><strong>@supabase/supabase-js</strong> — direct DB queries (read-only)</li>
          <li><strong>TanStack React Query</strong> — data fetching and caching</li>
          <li><strong>Lightweight Charts</strong> — OHLC candlestick visualization</li>
          <li><strong>React Router</strong> — client-side routing</li>
          <li><strong>Lucide React</strong> — icons</li>
        </ul>
        <p>
          No backend server is required — the frontend connects directly to Supabase
          using a read-only anonymous key with Row Level Security (RLS).
        </p>
      </Accordion>
    </div>
  );
}

export default function Guide() {
  const [activeTab, setActiveTab] = useState<Tab>('general');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Guide</h2>
        <span className="text-xs font-medium px-2 py-0.5 rounded bg-primary/10 text-primary">
          2025 Season
        </span>
      </div>

      {/* Tab Selector */}
      <div className="flex gap-2">
        <button
          onClick={() => setActiveTab('general')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold transition-all ${
            activeTab === 'general'
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <BookOpen className="w-4 h-4" />
          General
        </button>
        <button
          onClick={() => setActiveTab('developer')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-semibold transition-all ${
            activeTab === 'developer'
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          <Code className="w-4 h-4" />
          Developer
        </button>
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        {activeTab === 'general' ? <GeneralTab /> : <DeveloperTab />}
      </div>
    </div>
  );
}
