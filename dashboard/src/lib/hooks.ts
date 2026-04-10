"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchTasks,
  fetchTask,
  fetchJobs,
  fetchPromptVersions,
  type TaskSummary,
  type JobResponse,
  type PromptResponse,
} from "./api";

export function useTasks() {
  return useQuery<TaskSummary[]>({
    queryKey: ["tasks"],
    queryFn: () => fetchTasks(),
  });
}

export function useTask(taskId: string) {
  return useQuery<TaskSummary>({
    queryKey: ["task", taskId],
    queryFn: () => fetchTask(taskId),
    enabled: !!taskId,
  });
}

export function useJobs(taskId?: string, options?: { refetchInterval?: number }) {
  return useQuery<JobResponse[]>({
    queryKey: ["jobs", taskId ?? "all"],
    queryFn: () => fetchJobs(taskId),
    refetchInterval: options?.refetchInterval,
  });
}

export function useRecentJobs(limit = 20) {
  return useQuery<JobResponse[]>({
    queryKey: ["jobs", "recent", limit],
    queryFn: () => fetchJobs(undefined, limit),
  });
}

export function usePromptVersions(taskId: string) {
  return useQuery<PromptResponse[]>({
    queryKey: ["prompts", taskId],
    queryFn: () => fetchPromptVersions(taskId),
    enabled: !!taskId,
  });
}
