"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useTasks } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";

export function Sidebar() {
  const pathname = usePathname();
  const { data: tasks } = useTasks();
  const { logout } = useAuth();

  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-card">
      <div className="border-b p-4">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold">
          <img src="/kaizen.png" alt="Kaizen" className="h-7 w-auto" />
          Kaizen
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto p-3">
        <div className="mb-2 px-2 text-xs font-medium uppercase text-muted-foreground">
          Overview
        </div>
        <Link
          href="/"
          className={cn(
            "mb-1 block rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent",
            pathname === "/" && "bg-accent font-medium"
          )}
        >
          Home
        </Link>

        <div className="mb-2 mt-4 px-2 text-xs font-medium uppercase text-muted-foreground">
          Tasks
        </div>
        {tasks?.map((task) => (
          <Link
            key={task.id}
            href={`/tasks/${task.id}`}
            className={cn(
              "mb-1 block truncate rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent",
              pathname?.startsWith(`/tasks/${task.id}`) && "bg-accent font-medium"
            )}
          >
            {task.name}
          </Link>
        ))}
        {tasks?.length === 0 && (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            No tasks yet
          </p>
        )}
      </nav>

      <div className="border-t p-3 space-y-1">
        <Link
          href="/settings"
          className={cn(
            "block rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent text-muted-foreground",
            pathname === "/settings" && "bg-accent font-medium"
          )}
        >
          Settings
        </Link>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-muted-foreground"
          onClick={logout}
        >
          Sign out
        </Button>
      </div>
    </aside>
  );
}
