"use client";

import { ThemeProvider } from "next-themes";
import { SWRConfig } from "swr";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <SWRConfig value={{ shouldRetryOnError: false }}>
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      </SWRConfig>
    </ThemeProvider>
  );
}
