"use client";

import React from "react";
import { AppShell } from "@/components/app-shell";
import { TaskCard } from "@/components/task-card";
import { ActivityFeed } from "@/components/activity-feed";
import { useTasks, useRecentJobs } from "@/lib/hooks";

export default function HomePage() {
  const { data: tasks, isLoading: tasksLoading } = useTasks();
  const { data: recentJobs, isLoading: jobsLoading } = useRecentJobs(10);

  return (
    <AppShell>
      <div className="space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Overview of optimization tasks and recent activity.
          </p>
        </div>

        {/* Task grid */}
        <section>
          <h2 className="mb-4 text-lg font-semibold">Tasks</h2>
          {tasksLoading ? (
            <p className="text-sm text-muted-foreground">Loading tasks...</p>
          ) : tasks && tasks.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <p className="text-sm text-muted-foreground">
                No tasks yet. Create one via the API or SDK.
              </p>
            </div>
          )}
        </section>

        {/* Activity feed */}
        <section>
          <h2 className="mb-4 text-lg font-semibold">Recent Activity</h2>
          {jobsLoading ? (
            <p className="text-sm text-muted-foreground">Loading activity...</p>
          ) : (
            <ActivityFeed jobs={recentJobs ?? []} />
          )}
        </section>
      </div>
    </AppShell>
  );
}
