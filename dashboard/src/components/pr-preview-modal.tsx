"use client";

import React, { useState } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { PromptDiff } from "@/components/prompt-diff";
import { createPrFromPreview, rejectOptimization } from "@/lib/api";
import type { JobResponse } from "@/lib/api";

interface FileChange {
  path: string;
  old_content: string;
  new_content: string;
}

interface PrPreviewData {
  pr_body: string;
  pr_title: string;
  old_prompt: string | null;
  new_prompt: string;
  file_path: string;
  file_changes?: FileChange[];
}

interface PrPreviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  job: JobResponse;
  hasGitConfig: boolean;
  onActionComplete: () => void;
}

type DiffTab = "file" | "prompt";

export function PrPreviewModal({
  open,
  onOpenChange,
  job,
  hasGitConfig,
  onActionComplete,
}: PrPreviewModalProps) {
  const [activeTab, setActiveTab] = useState<DiffTab>("file");
  const [creating, setCreating] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const preview = (job.job_metadata?.pr_preview as PrPreviewData) ?? null;
  if (!preview) return null;

  const handleCreatePr = async () => {
    setCreating(true);
    setError(null);
    try {
      await createPrFromPreview(job.id);
      onOpenChange(false);
      onActionComplete();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create PR");
    } finally {
      setCreating(false);
    }
  };

  const handleReject = async () => {
    setRejecting(true);
    setError(null);
    try {
      await rejectOptimization(job.id);
      onOpenChange(false);
      onActionComplete();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to reject");
    } finally {
      setRejecting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-none w-[95vw] h-[90vh] p-0 flex flex-col">
        {/* Header bar */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold">{preview.pr_title}</h2>
          <div className="flex items-center gap-2">
            {error && (
              <span className="text-sm text-destructive">{error}</span>
            )}
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={creating || rejecting}
            >
              Dismiss
            </Button>
            <Button
              variant="destructive"
              onClick={handleReject}
              disabled={creating || rejecting}
            >
              {rejecting ? "Rejecting..." : "Reject"}
            </Button>
            <Button
              onClick={handleCreatePr}
              disabled={creating || rejecting || !hasGitConfig}
              title={
                !hasGitConfig
                  ? "No git configuration on this task"
                  : undefined
              }
            >
              {creating ? "Creating PR..." : "Create PR"}
            </Button>
          </div>
        </div>

        {/* Split panel content */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left panel: PR body (D-04) */}
          <div className="w-1/2 overflow-auto border-r p-6">
            <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap font-mono text-sm">
              {preview.pr_body}
            </div>
          </div>

          {/* Right panel: tabbed diffs (D-05) */}
          <div className="w-1/2 flex flex-col overflow-hidden">
            {/* Tab bar */}
            <div className="flex gap-1 border-b px-4 pt-2">
              <button
                className={`px-3 py-1.5 text-sm rounded-t border-b-2 ${
                  activeTab === "file"
                    ? "border-primary font-medium"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => setActiveTab("file")}
              >
                File Diff
              </button>
              <button
                className={`px-3 py-1.5 text-sm rounded-t border-b-2 ${
                  activeTab === "prompt"
                    ? "border-primary font-medium"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => setActiveTab("prompt")}
              >
                Prompt Diff
              </button>
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-auto p-4">
              {activeTab === "file" && (
                <div className="space-y-4">
                  {preview.file_changes && preview.file_changes.length > 0 ? (
                    preview.file_changes.map((fc, i) => (
                      <div key={i}>
                        <p className="mb-2 text-xs font-medium text-muted-foreground">
                          {fc.path}
                        </p>
                        <PromptDiff
                          oldText={fc.old_content}
                          newText={fc.new_content}
                          oldLabel="Current"
                          newLabel="Modified"
                        />
                      </div>
                    ))
                  ) : (
                    <div>
                      <p className="mb-2 text-xs text-muted-foreground">
                        {preview.file_path}
                      </p>
                      <PromptDiff
                        oldText={preview.old_prompt ?? ""}
                        newText={preview.new_prompt}
                        oldLabel="Current"
                        newLabel="Optimized"
                      />
                    </div>
                  )}
                </div>
              )}
              {activeTab === "prompt" && (
                <div className="grid gap-4">
                  <div>
                    <h4 className="mb-1 text-xs font-medium text-muted-foreground">
                      Before
                    </h4>
                    <pre className="rounded border bg-muted/30 p-3 text-sm font-mono whitespace-pre-wrap max-h-[35vh] overflow-auto">
                      {preview.old_prompt ?? "(no previous prompt)"}
                    </pre>
                  </div>
                  <div>
                    <h4 className="mb-1 text-xs font-medium text-muted-foreground">
                      After
                    </h4>
                    <pre className="rounded border bg-muted/30 p-3 text-sm font-mono whitespace-pre-wrap max-h-[35vh] overflow-auto">
                      {preview.new_prompt}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
