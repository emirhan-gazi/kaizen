"use client";

import React from "react";
import { StatusBadge } from "./status-badge";
import type { JobResponse } from "@/lib/api";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ActivityFeed({ jobs }: { jobs: JobResponse[] }) {
  if (jobs.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No optimization activity yet. Submit feedback to get started.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {jobs.map((job) => (
        <div
          key={job.id}
          className="flex items-center justify-between rounded-lg border p-3"
        >
          <div className="flex items-center gap-3">
            <StatusBadge status={job.status} />
            <div className="text-sm">
              <span className="font-medium">
                {job.triggered_by === "auto" ? "Auto-trigger" : "Manual"} job
              </span>
              {job.pr_url && (
                <a
                  href={job.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-2 text-xs text-blue-600 hover:underline"
                >
                  PR
                </a>
              )}
            </div>
          </div>
          <span className="text-xs text-muted-foreground">
            {timeAgo(job.created_at)}
          </span>
        </div>
      ))}
    </div>
  );
}
