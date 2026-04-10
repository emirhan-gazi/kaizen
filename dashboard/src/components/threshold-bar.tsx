"use client";

import React from "react";

interface ThresholdBarProps {
  progress: string; // e.g. "12/50"
}

export function ThresholdBar({ progress }: ThresholdBarProps) {
  const [current, total] = progress.split("/").map(Number);
  const pct = total > 0 ? Math.min((current / total) * 100, 100) : 0;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Threshold</span>
        <span>{progress}</span>
      </div>
      <div className="h-2 w-full rounded-full bg-secondary">
        <div
          className="h-2 rounded-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
