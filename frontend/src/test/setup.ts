import "@testing-library/jest-dom/vitest";
import { cloneElement, createElement, isValidElement, type ReactElement } from "react";
import { vi } from "vitest";

// jsdom has no layout engine: give Recharts' ResponsiveContainer a fixed size so charts render.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children, height }: { children: ReactElement; height?: number | string }) =>
      isValidElement(children)
        ? createElement("div", { style: { width: 800, height: typeof height === "number" ? height : 300 } },
            cloneElement(children as ReactElement<{ width?: number; height?: number }>, { width: 800, height: typeof height === "number" ? height : 300 }))
        : null,
  };
});

class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver;
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.scrollIntoView ??= () => {};
