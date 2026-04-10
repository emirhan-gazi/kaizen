"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  fetchKeys,
  createKey,
  revokeKey,
  type ApiKeyInfo,
} from "@/lib/api";

export default function SettingsPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [newLabel, setNewLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const loadKeys = useCallback(async () => {
    try {
      const data = await fetchKeys();
      setKeys(data);
    } catch {
      setError("Failed to load API keys.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  const handleCreate = async () => {
    setCreating(true);
    setError("");
    setNewKey(null);
    try {
      const result = await createKey(newLabel || undefined);
      setNewKey(result.key);
      setNewLabel("");
      await loadKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create key",
      );
    }
    setCreating(false);
  };

  const handleRevoke = async (keyId: string) => {
    setError("");
    try {
      await revokeKey(keyId);
      await loadKeys();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to revoke key",
      );
    }
  };

  const handleCopy = async () => {
    if (!newKey) return;
    await navigator.clipboard.writeText(newKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <AppShell>
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">
            Manage API keys for your Kaizen instance.
          </p>
        </div>

        {/* Create new key */}
        <Card>
          <CardHeader>
            <CardTitle>Create New Key</CardTitle>
            <CardDescription>
              Generate a new API key. The key is shown only once after
              creation.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Label (optional)"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                className="max-w-xs"
              />
              <Button onClick={handleCreate} disabled={creating}>
                {creating ? "Creating..." : "Create Key"}
              </Button>
            </div>

            {newKey && (
              <div className="space-y-2 rounded-md border bg-muted/50 p-4">
                <p className="text-sm font-medium">
                  Save this key now -- it will not be shown again:
                </p>
                <div className="flex gap-2">
                  <Input
                    readOnly
                    value={newKey}
                    className="font-mono text-sm"
                  />
                  <Button variant="outline" size="sm" onClick={handleCopy}>
                    {copied ? "Copied" : "Copy"}
                  </Button>
                </div>
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>

        {/* Key list */}
        <Card>
          <CardHeader>
            <CardTitle>API Keys</CardTitle>
            <CardDescription>
              All keys for this instance. Revoked keys can no longer
              authenticate.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : keys.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No API keys found.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Label</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {keys.map((k) => (
                    <TableRow key={k.id}>
                      <TableCell className="font-medium">
                        {k.label || "--"}
                      </TableCell>
                      <TableCell>
                        {new Date(k.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        {k.revoked_at ? (
                          <Badge variant="destructive">Revoked</Badge>
                        ) : (
                          <Badge variant="secondary">Active</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {!k.revoked_at && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRevoke(k.id)}
                          >
                            Revoke
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
