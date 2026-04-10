"use client";

import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { PromptResponse } from "@/lib/api";

interface ScoreChartProps {
  prompts: PromptResponse[];
}

export function ScoreChart({ prompts }: ScoreChartProps) {
  // Sort by version ascending and filter to those with scores
  const data = [...prompts]
    .filter((p) => p.eval_score !== null || p.judge_score !== null)
    .sort((a, b) => a.version_number - b.version_number)
    .map((p) => ({
      version: `v${p.version_number}`,
      dataset: p.eval_score !== null ? Number(((p.eval_score) * 100).toFixed(1)) : null,
      judge: p.judge_score !== null ? Number(((p.judge_score) * 100).toFixed(1)) : null,
    }));

  if (data.length < 2) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Need at least 2 prompt versions with scores to show a trend chart.
      </p>
    );
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="version"
            tick={{ fontSize: 12 }}
            className="text-muted-foreground"
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 12 }}
            tickFormatter={(v: number) => `${v}%`}
            className="text-muted-foreground"
          />
          <Tooltip
            formatter={(value: number, name: string) => [
              `${value}%`,
              name === "dataset" ? "Dataset" : "Judge",
            ]}
            contentStyle={{
              borderRadius: "0.5rem",
              border: "1px solid hsl(var(--border))",
              background: "hsl(var(--card))",
            }}
          />
          <Line
            type="monotone"
            dataKey="dataset"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
            name="dataset"
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="judge"
            stroke="#f59e0b"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ r: 4 }}
            activeDot={{ r: 6 }}
            name="judge"
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
