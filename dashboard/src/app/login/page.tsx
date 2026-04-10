"use client";

import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  setApiKey,
  validateApiKey,
  checkHasKeys,
  bootstrapKey,
} from "@/lib/api";

type PageState = "loading" | "setup" | "login";

export default function LoginPage() {
  const [pageState, setPageState] = useState<PageState>("loading");
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    checkHasKeys().then((hasKeys) => {
      setPageState(hasKeys ? "login" : "setup");
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    const trimmed = key.trim();
    if (!trimmed) {
      setError("Please enter an API key");
      setLoading(false);
      return;
    }

    const valid = await validateApiKey(trimmed);
    if (valid) {
      setApiKey(trimmed);
      window.location.href = "/";
      return;
    } else {
      setError("Invalid API key. Check your key and try again.");
    }
    setLoading(false);
  };

  const handleBootstrap = async () => {
    setError("");
    setLoading(true);
    try {
      const result = await bootstrapKey("default");
      setGeneratedKey(result.key);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to generate API key",
      );
    }
    setLoading(false);
  };

  const handleCopy = async () => {
    if (!generatedKey) return;
    await navigator.clipboard.writeText(generatedKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSignInWithGenerated = () => {
    if (!generatedKey) return;
    setApiKey(generatedKey);
    window.location.href = "/";
  };

  if (pageState === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (pageState === "setup") {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <img
              src="/kaizen.png"
              alt="Kaizen"
              className="mx-auto mb-2 h-12 w-auto"
            />
            <CardTitle className="text-2xl">Welcome to Kaizen</CardTitle>
            <CardDescription>
              Generate your first API key to get started.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!generatedKey ? (
              <>
                <Button
                  className="w-full"
                  onClick={handleBootstrap}
                  disabled={loading}
                >
                  {loading ? "Generating..." : "Generate API Key"}
                </Button>
                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}
              </>
            ) : (
              <>
                <div className="space-y-2">
                  <p className="text-sm font-medium">
                    Your API key (save it now -- it will not be shown again):
                  </p>
                  <div className="flex gap-2">
                    <Input
                      readOnly
                      value={generatedKey}
                      className="font-mono text-sm"
                    />
                    <Button variant="outline" size="sm" onClick={handleCopy}>
                      {copied ? "Copied" : "Copy"}
                    </Button>
                  </div>
                </div>
                <Button
                  className="w-full"
                  onClick={handleSignInWithGenerated}
                >
                  Sign in
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  // Login state
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <img
            src="/kaizen.png"
            alt="Kaizen"
            className="mx-auto mb-2 h-12 w-auto"
          />
          <CardTitle className="text-2xl">Kaizen</CardTitle>
          <CardDescription>
            Enter your API key to access the dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Input
                type="password"
                placeholder="kaizen_..."
                value={key}
                onChange={(e) => setKey(e.target.value)}
                autoFocus
              />
              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Validating..." : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
