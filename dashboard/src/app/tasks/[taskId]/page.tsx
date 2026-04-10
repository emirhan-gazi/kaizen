"use client";

import React, { useState } from "react";
import { useParams } from "next/navigation";
import { useTask, useJobs, usePromptVersions } from "@/lib/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ThresholdBar } from "@/components/threshold-bar";
import { JobsTable } from "@/components/jobs-table";
import { PromptHistory } from "@/components/prompt-history";
import { ScoreChart } from "@/components/score-chart";
import { triggerOptimization, deleteTask } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

type Tab = "overview" | "jobs" | "prompts";

const TABS: { value: Tab; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "jobs", label: "Jobs" },
  { value: "prompts", label: "Prompts" },
];

export default function TaskDetailPage() {
  const params = useParams();
  const taskId = params.taskId as string;
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [optimizing, setOptimizing] = useState(false);
  const [optimizeError, setOptimizeError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const queryClient = useQueryClient();

  const { data: task, isLoading: taskLoading } = useTask(taskId);

  // Poll every 5s when there might be active jobs (D-10)
  const { data: jobs } = useJobs(taskId, { refetchInterval: 5000 });
  const { data: prompts } = usePromptVersions(taskId);

  if (taskLoading) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Loading task...
      </p>
    );
  }

  if (!task) {
    return (
      <p className="py-8 text-center text-sm text-destructive">
        Task not found.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{task.name}</h1>
          {task.description && (
            <p className="text-muted-foreground">{task.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {optimizeError && (
            <p className="text-sm text-destructive">{optimizeError}</p>
          )}
          <Button
            disabled={optimizing}
            onClick={async () => {
              setOptimizing(true);
              setOptimizeError(null);
              try {
                await triggerOptimization(taskId);
                setActiveTab("jobs");
              } catch (e: unknown) {
                setOptimizeError(
                  e instanceof Error ? e.message : "Optimization failed"
                );
              } finally {
                setOptimizing(false);
              }
            }}
          >
            {optimizing ? "Starting..." : "Trigger Optimization"}
          </Button>
          <Button
            variant="destructive"
            disabled={deleting}
            onClick={async () => {
              if (!confirm(`Delete task "${task.name}" and all its data?`)) return;
              setDeleting(true);
              try {
                await deleteTask(taskId);
                window.location.href = "/";
              } catch {
                setDeleting(false);
              }
            }}
          >
            {deleting ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b">
        {TABS.map((tab) => (
          <Button
            key={tab.value}
            variant="ghost"
            size="sm"
            className={cn(
              "rounded-b-none border-b-2 border-transparent",
              activeTab === tab.value && "border-primary font-medium"
            )}
            onClick={() => setActiveTab(tab.value)}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "overview" && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Stats cards */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Threshold Progress</CardTitle>
            </CardHeader>
            <CardContent>
              <ThresholdBar progress={task.threshold_progress} />
              <p className="mt-2 text-xs text-muted-foreground">
                {task.feedback_count} feedback entries collected
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Active Prompt</CardTitle>
            </CardHeader>
            <CardContent>
              {task.active_prompt_score !== null ? (
                <div>
                  <p className="text-3xl font-bold">
                    {(task.active_prompt_score * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground">eval score</p>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No active prompt yet
                </p>
              )}
            </CardContent>
          </Card>

          {/* Score trend chart */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Score Trend</CardTitle>
              </CardHeader>
              <CardContent>
                <ScoreChart prompts={prompts ?? []} />
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {activeTab === "jobs" && (
        <JobsTable
          jobs={jobs ?? []}
          taskMode={task.mode}
          hasGitConfig={!!(task.git_repo || task.git_provider)}
          onJobsChange={() => {
            queryClient.invalidateQueries({ queryKey: ["jobs"] });
          }}
        />
      )}

      {activeTab === "prompts" && <PromptHistory prompts={prompts ?? []} />}
    </div>
  );
}
