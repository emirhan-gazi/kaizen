"use client";

import React from "react";
import Link from "next/link";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { ThresholdBar } from "./threshold-bar";
import type { TaskSummary } from "@/lib/api";

export function TaskCard({ task }: { task: TaskSummary }) {
  const score = task.active_prompt_score;

  return (
    <Link href={`/tasks/${task.id}`}>
      <Card className="cursor-pointer transition-shadow hover:shadow-md">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{task.name}</CardTitle>
          {task.description && (
            <CardDescription className="line-clamp-1">
              {task.description}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Feedback</span>
            <span className="font-medium">{task.feedback_count}</span>
          </div>
          {score !== null && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Score</span>
              <span className="font-medium">{(score * 100).toFixed(1)}%</span>
            </div>
          )}
          {task.last_optimization && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Last optimized</span>
              <span className="font-medium text-xs">
                {new Date(task.last_optimization).toLocaleDateString()}
              </span>
            </div>
          )}
          <ThresholdBar progress={task.threshold_progress} />
        </CardContent>
      </Card>
    </Link>
  );
}
