"use client";

import React from "react";

interface DiffLine {
  type: "added" | "removed" | "unchanged";
  text: string;
}

function computeDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");
  const lines: DiffLine[] = [];

  // Simple LCS-based diff
  const m = oldLines.length;
  const n = newLines.length;

  // Build LCS table
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    Array(n + 1).fill(0)
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (oldLines[i - 1] === newLines[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack to produce diff
  let i = m;
  let j = n;
  const result: DiffLine[] = [];
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      result.push({ type: "unchanged", text: oldLines[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.push({ type: "added", text: newLines[j - 1] });
      j--;
    } else {
      result.push({ type: "removed", text: oldLines[i - 1] });
      i--;
    }
  }
  result.reverse();

  return result;
}

const lineStyles: Record<DiffLine["type"], string> = {
  added: "bg-green-500/15 text-green-700 dark:text-green-400",
  removed: "bg-red-500/15 text-red-700 dark:text-red-400 line-through",
  unchanged: "text-muted-foreground",
};

const linePrefix: Record<DiffLine["type"], string> = {
  added: "+ ",
  removed: "- ",
  unchanged: "  ",
};

export function PromptDiff({
  oldText,
  newText,
  oldLabel,
  newLabel,
}: {
  oldText: string;
  newText: string;
  oldLabel?: string;
  newLabel?: string;
}) {
  const lines = computeDiff(oldText, newText);
  const added = lines.filter((l) => l.type === "added").length;
  const removed = lines.filter((l) => l.type === "removed").length;

  return (
    <div className="rounded border text-sm font-mono">
      <div className="flex items-center justify-between border-b bg-muted/30 px-4 py-2 text-xs">
        <span>
          {oldLabel && <span className="text-muted-foreground">{oldLabel}</span>}
          {oldLabel && newLabel && <span className="text-muted-foreground"> → </span>}
          {newLabel && <span>{newLabel}</span>}
        </span>
        <span>
          {added > 0 && (
            <span className="text-green-600 dark:text-green-400">+{added}</span>
          )}
          {added > 0 && removed > 0 && " "}
          {removed > 0 && (
            <span className="text-red-600 dark:text-red-400">-{removed}</span>
          )}
        </span>
      </div>
      <pre className="max-h-96 overflow-auto p-0 m-0">
        {lines.map((line, idx) => (
          <div key={idx} className={`px-4 py-0.5 ${lineStyles[line.type]}`}>
            <span className="select-none opacity-50">{linePrefix[line.type]}</span>
            {line.text || "\u00A0"}
          </div>
        ))}
      </pre>
    </div>
  );
}
