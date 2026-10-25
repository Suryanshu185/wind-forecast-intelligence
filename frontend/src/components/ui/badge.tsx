import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const tones = {
  neutral: "border-border bg-raised text-muted",
  good: "border-actual/40 bg-actual/10 text-actual",
  warn: "border-warn/50 bg-warn/10 text-warn",
  bad: "border-over/50 bg-over/10 text-over",
} as const;

export function Badge({ tone = "neutral", className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn("inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", tones[tone], className)}
      {...props}
    />
  );
}
