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
import { PromptStatusBadge } from "./status-badge";
import { PromptDiff } from "./prompt-diff";
import type { PromptResponse } from "@/lib/api";

type ExpandMode = "prompt" | "diff";

export function PromptHistory({ prompts }: { prompts: PromptResponse[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandMode, setExpandMode] = useState<ExpandMode>("diff");

  if (prompts.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No prompt versions yet.
      </p>
    );
  }

  // Sort by version descending for display, ascending index for prev lookup
  const sorted = [...prompts].sort(
    (a, b) => b.version_number - a.version_number
  );
  const byVersion = new Map(prompts.map((p) => [p.version_number, p]));

  const toggle = (id: string, mode: ExpandMode) => {
    if (expandedId === id && expandMode === mode) {
      setExpandedId(null);
    } else {
      setExpandedId(id);
      setExpandMode(mode);
    }
  };

  return (
    <div className="space-y-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Version</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Dataset</TableHead>
            <TableHead>Judge</TableHead>
            <TableHead>Optimizer</TableHead>
            <TableHead>Created</TableHead>
            <TableHead></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((p) => {
            const prev = byVersion.get(p.version_number - 1);
            const hasDiff = p.prompt_text && prev?.prompt_text;
            const isExpanded = expandedId === p.id;

            return (
              <React.Fragment key={p.id}>
                <TableRow>
                  <TableCell className="font-medium">
                    v{p.version_number}
                  </TableCell>
                  <TableCell>
                    <PromptStatusBadge status={p.status} />
                  </TableCell>
                  <TableCell className="text-sm">
                    {p.eval_score !== null
                      ? `${(p.eval_score * 100).toFixed(1)}%`
                      : "-"}
                  </TableCell>
                  <TableCell className="text-sm">
                    {p.judge_score !== null
                      ? `${(p.judge_score * 100).toFixed(1)}%`
                      : "-"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {p.optimizer ?? "-"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {new Date(p.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {p.prompt_text && (
                        <Button
                          size="sm"
                          variant={
                            isExpanded && expandMode === "prompt"
                              ? "secondary"
                              : "ghost"
                          }
                          onClick={() => toggle(p.id, "prompt")}
                        >
                          Prompt
                        </Button>
                      )}
                      {hasDiff && (
                        <Button
                          size="sm"
                          variant={
                            isExpanded && expandMode === "diff"
                              ? "secondary"
                              : "ghost"
                          }
                          onClick={() => toggle(p.id, "diff")}
                        >
                          Diff
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
                {isExpanded && expandMode === "prompt" && p.prompt_text && (
                  <TableRow>
                    <TableCell colSpan={7} className="bg-muted/50 p-0">
                      <pre className="max-h-96 overflow-auto whitespace-pre-wrap p-4 text-sm font-mono">
                        {p.prompt_text}
                      </pre>
                    </TableCell>
                  </TableRow>
                )}
                {isExpanded &&
                  expandMode === "diff" &&
                  p.prompt_text &&
                  prev?.prompt_text && (
                    <TableRow>
                      <TableCell colSpan={7} className="p-4">
                        <PromptDiff
                          oldText={prev.prompt_text}
                          newText={p.prompt_text}
                          oldLabel={`v${prev.version_number}`}
                          newLabel={`v${p.version_number}`}
                        />
                      </TableCell>
                    </TableRow>
                  )}
              </React.Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
