"use client";

import React from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-gray-100 text-gray-700 border-gray-200",
  RUNNING: "bg-blue-100 text-blue-700 border-blue-200",
  EVALUATING: "bg-yellow-100 text-yellow-700 border-yellow-200",
  COMPILING: "bg-purple-100 text-purple-700 border-purple-200",
  SUCCESS: "bg-green-100 text-green-700 border-green-200",
  FAILURE: "bg-red-100 text-red-700 border-red-200",
  PR_FAILED: "bg-orange-100 text-orange-700 border-orange-200",
};

const PROMPT_STATUS_STYLES: Record<string, string> = {
  draft: "bg-yellow-50 text-yellow-700 border-yellow-200",
  active: "bg-green-100 text-green-700 border-green-200",
  archived: "bg-gray-100 text-gray-500 border-gray-200",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600";
  return (
    <Badge variant="outline" className={cn(style)}>
      {status}
    </Badge>
  );
}

export function PromptStatusBadge({ status }: { status: string }) {
  const style = PROMPT_STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600";
  return (
    <Badge variant="outline" className={cn(style)}>
      {status}
    </Badge>
  );
}
