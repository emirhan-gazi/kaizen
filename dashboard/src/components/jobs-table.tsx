"use client";

import React, { useState } from "react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "./status-badge";
import { retryPr } from "@/lib/api";
import type { JobResponse } from "@/lib/api";
import { PrPreviewModal } from "./pr-preview-modal";

function formatDate(d: string | null): string {
  if (!d) return "-";
  return new Date(d).toLocaleString();
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return "-";
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const secs = Math.round((e - s) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

interface JobsTableProps {
  jobs: JobResponse[];
  taskMode?: string;
  hasGitConfig?: boolean;
  onJobsChange?: () => void;
}

export function JobsTable({ jobs, taskMode, hasGitConfig = false, onJobsChange }: JobsTableProps) {
  const [retrying, setRetrying] = useState<string | null>(null);
  const [previewJob, setPreviewJob] = useState<JobResponse | null>(null);

  if (jobs.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No optimization jobs yet.
      </p>
    );
  }

  const handleRetryPr = async (jobId: string) => {
    setRetrying(jobId);
    try {
      await retryPr(jobId);
    } catch {
      // error handled by apiFetch
    } finally {
      setRetrying(null);
    }
  };

  return (
    <>
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Status</TableHead>
          <TableHead>Trigger</TableHead>
          <TableHead>Feedback</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>PR</TableHead>
          <TableHead>Error</TableHead>
          <TableHead>Created</TableHead>
          <TableHead></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <TableRow key={job.id}>
            <TableCell>
              <StatusBadge status={job.status} />
            </TableCell>
            <TableCell className="text-sm">
              {job.triggered_by === "auto" ? "Auto" : "Manual"}
            </TableCell>
            <TableCell className="text-sm">
              {job.feedback_count ?? "-"}
            </TableCell>
            <TableCell className="text-sm">
              {formatDuration(job.started_at, job.completed_at)}
            </TableCell>
            <TableCell>
              {job.pr_url ? (
                <a
                  href={job.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-blue-600 hover:underline"
                >
                  View PR
                </a>
              ) : (
                <span className="text-sm text-muted-foreground">-</span>
              )}
            </TableCell>
            <TableCell className="max-w-[200px] truncate text-sm text-destructive" title={job.error_message ?? ""}>
              {job.error_message ?? "-"}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {formatDate(job.created_at)}
            </TableCell>
            <TableCell className="flex items-center gap-1">
              {taskMode === "pr_preview" &&
                job.status === "SUCCESS" &&
                !!job.job_metadata?.pr_preview &&
                !job.pr_url && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setPreviewJob(job)}
                  >
                    Preview PR
                  </Button>
                )}
              {job.status === "PR_FAILED" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={retrying === job.id}
                  onClick={() => handleRetryPr(job.id)}
                >
                  {retrying === job.id ? "Retrying..." : "Retry PR"}
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
    {previewJob && (
      <PrPreviewModal
        open={!!previewJob}
        onOpenChange={(open) => { if (!open) setPreviewJob(null); }}
        job={previewJob}
        hasGitConfig={hasGitConfig}
        onActionComplete={() => {
          setPreviewJob(null);
          onJobsChange?.();
        }}
      />
    )}
    </>
  );
}
