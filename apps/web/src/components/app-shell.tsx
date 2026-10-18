"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { FlaskConical, LayoutDashboard, ListChecks, Menu, Play, Plus } from "lucide-react";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { API_BASE_URL, IS_MOCK } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/runs", label: "Runs", icon: Play },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  if (href === "/runs") return pathname === "/runs" || (pathname.startsWith("/runs/") && pathname !== "/runs/new");
  return pathname.startsWith(href);
}

function ModeBadge() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant={IS_MOCK ? "secondary" : "outline"} className="gap-1 font-mono text-[11px]">
          {IS_MOCK ? <FlaskConical /> : <span className="size-1.5 rounded-full bg-emerald-500" />}
          {IS_MOCK ? "mock" : "live"}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{IS_MOCK ? "NEXT_PUBLIC_SIDE_MOCK=1 — serving local fixtures" : API_BASE_URL}</TooltipContent>
    </Tooltip>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-3 px-4 sm:px-6">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72">
              <SheetHeader>
                <SheetTitle>
                  <Logo />
                </SheetTitle>
              </SheetHeader>
              <nav className="flex flex-col gap-1 px-4">
                {NAV.map(({ href, label, icon: Icon }) => (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground",
                      isActive(pathname, href) && "bg-muted text-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    {label}
                  </Link>
                ))}
                <Link
                  href="/runs/new"
                  onClick={() => setOpen(false)}
                  className="mt-2 flex items-center gap-3 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
                >
                  <Plus className="size-4" /> New run
                </Link>
              </nav>
            </SheetContent>
          </Sheet>
          <Link href="/" aria-label="Side home">
            <Logo />
          </Link>
          <nav className="ml-4 hidden items-center gap-1 md:flex">
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
                  isActive(pathname, href) && "bg-muted text-foreground",
                )}
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ModeBadge />
            <ThemeToggle />
            <Button asChild size="sm" className="hidden sm:inline-flex">
              <Link href="/runs/new">
                <Plus /> New run
              </Link>
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      <footer className="border-t py-4 text-center text-xs text-muted-foreground">
        Side · built on <span className="font-medium">BrowserGym</span>
      </footer>
    </div>
  );
}
