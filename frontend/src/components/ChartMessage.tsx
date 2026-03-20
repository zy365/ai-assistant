import React from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { ChartSpec } from "../hooks/useSSE";

const COLORS = ["#00d4ff", "#0066ff", "#00ff88", "#ffaa00", "#ff3b5c", "#cc44ff"];

const tooltipStyle = {
  contentStyle: { background: "#0d1f3c", border: "1px solid #1a3a5c", borderRadius: 4, fontSize: 12, fontFamily: "Space Mono" },
  labelStyle: { color: "#00d4ff" },
  itemStyle: { color: "#c8dff0" },
};

const axisStyle = { tick: { fill: "#2a5a7a", fontSize: 10, fontFamily: "Space Mono" }, axisLine: { stroke: "#1a3a5c" }, tickLine: false };

export default function ChartMessage({ data }: { data: ChartSpec }) {
  return (
    <div style={{
      margin: "12px 0", background: "#060f1e",
      border: "1px solid #1a3a5c", borderRadius: 6,
      padding: 16, position: "relative", overflow: "hidden",
    }}>
      {/* corner accents */}
      {[["0,0","top,left"],["0,auto","top,right"],["auto,0","bottom,left"],["auto","bottom,right"]].map(([,pos], i) => {
        const [v, h] = pos.split(",");
        return <div key={i} style={{ position:"absolute", [v]:0, [h]:0, width:10, height:10,
          borderTop: v==="top" ? "1px solid var(--accent)" : "none",
          borderBottom: v==="bottom" ? "1px solid var(--accent)" : "none",
          borderLeft: h==="left" ? "1px solid var(--accent)" : "none",
          borderRight: h==="right" ? "1px solid var(--accent)" : "none", opacity:0.6 }} />;
      })}

      {data.title && (
        <div style={{ fontSize: 11, fontFamily: "Space Mono", color: "var(--accent)", letterSpacing: "0.12em", marginBottom: 14, textTransform: "uppercase" }}>
          // {data.title}
        </div>
      )}

      {data.type === "line" && (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data.data}>
            <CartesianGrid strokeDasharray="2 4" stroke="#0f2a45" />
            <XAxis dataKey={data.x_field} {...axisStyle} />
            <YAxis {...axisStyle} />
            <Tooltip {...tooltipStyle} />
            <Line type="monotone" dataKey={data.y_field} stroke="#00d4ff" strokeWidth={2} dot={false}
              style={{ filter: "drop-shadow(0 0 4px #00d4ff)" }} />
          </LineChart>
        </ResponsiveContainer>
      )}

      {data.type === "bar" && (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.data}>
            <CartesianGrid strokeDasharray="2 4" stroke="#0f2a45" />
            <XAxis dataKey={data.x_field} {...axisStyle} />
            <YAxis {...axisStyle} />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey={data.y_field} radius={[2,2,0,0]}>
              {data.data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} fillOpacity={0.85} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      {data.type === "pie" && (
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={data.data} dataKey={data.value_field ?? "value"} nameKey={data.name_field ?? "name"}
              cx="50%" cy="50%" outerRadius={80} innerRadius={40} paddingAngle={3} label>
              {data.data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip {...tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 11, fontFamily: "Space Mono", color: "var(--text2)" }} />
          </PieChart>
        </ResponsiveContainer>
      )}

      {data.type === "table" && data.columns && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: "Space Mono" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--accent)", opacity: 0.8 }}>
                {data.columns.map(c => (
                  <th key={c.field} style={{ padding: "8px 12px", textAlign: "left", color: "var(--accent)", fontWeight: 700, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.map((row, ri) => (
                <tr key={ri} style={{ borderBottom: "1px solid var(--border2)" }}
                  onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = "rgba(0,212,255,0.04)"}
                  onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = "transparent"}
                >
                  {data.columns!.map(c => (
                    <td key={c.field} style={{ padding: "8px 12px", color: "var(--text)", fontSize: 12 }}>
                      {String(row[c.field] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
