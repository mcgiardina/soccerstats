import { mainVideo } from "../lib/types";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeasonData } from "../lib/api";
import { summarizeGame } from "../lib/stats";
import { fmtDateShort } from "../lib/time";

export interface TrendPoint {
  id: string; date: string; label: string;
  goalsFor: number; goalsAgainst: number;
  shotsFor: number; shotsAgainst: number;
  xgFor: number | null; xgAgainst: number | null;
  possession: number | null;
  savesFor: number; savesAgainst: number;
}

export function buildTrend(d: SeasonData): TrendPoint[] {
  return [...d.games]
    .sort((a, b) => a.played_on.localeCompare(b.played_on))
    .map((g) => {
      const s = summarizeGame(g, mainVideo(g.videos), d.tags.filter((t) => t.game_id === g.id), d.shots.filter((x) => x.game_id === g.id), d.teamStats.filter((x) => x.game_id === g.id));
      return {
        id: g.id, date: g.played_on, label: `${fmtDateShort(g.played_on)} ${g.opponent}`,
        goalsFor: s.us.goals, goalsAgainst: s.them.goals, shotsFor: s.us.shots, shotsAgainst: s.them.shots,
        xgFor: s.us.xg, xgAgainst: s.them.xg, possession: s.us.possession, savesFor: s.us.saves, savesAgainst: s.them.saves,
      };
    });
}

const US = "var(--us)", THEM = "var(--them)";

function Chart({ title, data, a, b, aName, bName, unit }: { title: string; data: TrendPoint[]; a: keyof TrendPoint; b?: keyof TrendPoint; aName: string; bName?: string; unit?: string }) {
  const has = data.some((p) => p[a] != null || (b && p[b] != null));
  return (
    <div className="chart-card">
      <h3>{title}</h3>
      {!has ? <p className="small muted">No data yet.</p> : (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" tickFormatter={(v: string) => v.split(" ").slice(0, 2).join(" ")} />
            <YAxis tick={{ fontSize: 10 }} unit={unit} allowDecimals={a.startsWith("xg")} />
            <Tooltip contentStyle={{ fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey={a} name={aName} stroke={US} strokeWidth={2} dot={{ r: 3 }} connectNulls />
            {b ? <Line type="monotone" dataKey={b} name={bName} stroke={THEM} strokeWidth={2} dot={{ r: 3 }} connectNulls /> : null}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default function TrendCharts({ data, usName = "us" }: { data: TrendPoint[]; usName?: string }) {
  if (data.length < 2) return null;
  return (
    <div className="charts">
      <Chart title="Goals" data={data} a="goalsFor" b="goalsAgainst" aName="for" bName="against" />
      <Chart title="Shots" data={data} a="shotsFor" b="shotsAgainst" aName="for" bName="against" />
      <Chart title="xG (pro-calibrated proxy)" data={data} a="xgFor" b="xgAgainst" aName="for" bName="against" />
      <Chart title="Possession (machine ≈)" data={data} a="possession" aName={`${usName} %`} unit="%" />
    </div>
  );
}
