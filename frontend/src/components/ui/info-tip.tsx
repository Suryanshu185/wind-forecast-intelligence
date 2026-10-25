import * as Tooltip from "@radix-ui/react-tooltip";
import { Info } from "lucide-react";
import type { ReactNode } from "react";

/** Keyboard-focusable explanatory tooltip. `label` is also the accessible name. */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip.Provider delayDuration={150}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            type="button"
            aria-label={label}
            className="inline-flex size-5 items-center justify-center rounded-full text-muted hover:text-ink"
          >
            <Info className="size-3.5" aria-hidden />
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="top"
            sideOffset={6}
            collisionPadding={12}
            className="z-50 max-w-xs rounded-md border border-border bg-raised px-3 py-2 text-xs leading-relaxed text-ink shadow-lg"
          >
            {children}
            <Tooltip.Arrow className="fill-raised" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
