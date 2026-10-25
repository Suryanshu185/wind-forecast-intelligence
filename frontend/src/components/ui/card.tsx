import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={cn("rounded-xl border border-border bg-surface/80 shadow-sm", className)} {...props} />;
}

export function CardHeader({
  title,
  subtitle,
  actions,
  id,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  id?: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 px-4 py-3 sm:px-5">
      <div className="min-w-0">
        <h2 id={id} className="text-[15px] font-semibold tracking-tight text-ink">
          {title}
        </h2>
        {subtitle ? <p className="mt-0.5 text-[13px] leading-snug text-muted">{subtitle}</p> : null}
      </div>
      {actions}
    </header>
  );
}

export const CardBody = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-4 py-4 sm:px-5", className)} {...props} />
);
