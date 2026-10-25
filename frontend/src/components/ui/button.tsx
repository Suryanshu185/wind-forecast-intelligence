import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "ghost" | "outline";

const styles: Record<Variant, string> = {
  primary: "bg-actual text-bg font-semibold hover:brightness-110",
  outline: "border border-border bg-raised/60 text-ink hover:bg-raised",
  ghost: "text-muted hover:text-ink hover:bg-raised/60",
};

export function Button({
  variant = "outline",
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex min-h-9 items-center justify-center gap-2 rounded-md px-3 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}
