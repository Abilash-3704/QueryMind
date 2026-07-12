import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartSpec } from "../../api/client";

const ACCENT = "#00e5ff";

export function ResultChart({
  chartSpec,
  data,
}: {
  chartSpec: ChartSpec;
  data: Record<string, unknown>[];
}) {
  const { type, x, y } = chartSpec;
  const axisStyle = { fontFamily: "JetBrains Mono, monospace", fontSize: 11, fill: "#ffffff80" };

  return (
    <div className="mt-3 h-64 w-full rounded-md border border-border bg-panel/60 p-2">
      <ResponsiveContainer>
        {type === "line" ? (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff1a" />
            <XAxis dataKey={x} tick={axisStyle} stroke="#ffffff30" />
            <YAxis tick={axisStyle} stroke="#ffffff30" />
            <Tooltip
              contentStyle={{ background: "#12121a", border: "1px solid #ffffff1a" }}
              labelStyle={{ color: "#e5e5e5" }}
            />
            <Line
              type="monotone"
              dataKey={y}
              stroke={ACCENT}
              strokeWidth={2}
              animationDuration={300}
              animationEasing="ease-out"
            />
          </LineChart>
        ) : (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff1a" />
            <XAxis dataKey={x} tick={axisStyle} stroke="#ffffff30" />
            <YAxis tick={axisStyle} stroke="#ffffff30" />
            <Tooltip
              contentStyle={{ background: "#12121a", border: "1px solid #ffffff1a" }}
              labelStyle={{ color: "#e5e5e5" }}
            />
            <Bar dataKey={y} fill={ACCENT} animationDuration={300} animationEasing="ease-out" />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
