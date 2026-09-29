import type { CustomTool } from "./tool-selection-state";
import { CATEGORY_ORDER, TOOL_CATALOG, type ToolCategory } from "./tool-catalog";

/**
 * How well each kind of telemetry is covered by what the org picked.
 *
 * - `off`: nothing picked in the category.
 * - `declared`: something picked, but no picked tool has a connector today
 *   (a catalog tool still without one, or a tool the org added itself).
 * - `connected`: at least one picked tool has a connector `cypher ingest` runs.
 *
 * Pure: derived only from ids and the catalog, so the setup screen's map and
 * its text alternative can never disagree.
 */
export type ChannelState = "off" | "declared" | "connected";

export interface CategoryCoverage {
  category: ToolCategory;
  state: ChannelState;
  picked: number;
}

export function coverageByCategory(
  selected: ReadonlySet<string>,
  customTools: readonly CustomTool[],
): CategoryCoverage[] {
  return CATEGORY_ORDER.map((category) => {
    const catalog = TOOL_CATALOG.filter((t) => t.category === category && selected.has(t.id));
    const custom = customTools.filter((t) => t.category === category && selected.has(t.id));
    const picked = catalog.length + custom.length;
    const state: ChannelState =
      picked === 0 ? "off" : catalog.some((t) => t.available) ? "connected" : "declared";
    return { category, state, picked };
  });
}
