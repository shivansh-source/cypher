"use client";

import { createLocalStore } from "./local-store";
import { CATEGORY_ORDER, type ToolCategory } from "./tool-catalog";

/**
 * Which tools an org says it uses, and any tools it added that are not in
 * the catalog, persisted in this browser only.
 *
 * IMPORTANT — what this does and doesn't do: this selection is read only by
 * the dashboard itself (to show it back, and to decide whether to show the
 * first-run setup screen). Nothing on the backend reads it. Today,
 * `interfaces/cli/cypher.py::ingest_command` runs a fixed, hardcoded list
 * of connectors (Wazuh, Greenbone, Prowler, ScoutSuite, the AWS IAM
 * connector, and the CMDB connector); which of those actually run is
 * decided by whether each one's own environment variables are configured,
 * not by anything a person picks in a UI. Making this selection actually
 * gate which connector code runs would mean either teaching
 * `ingest_command` to read a config list instead of a hardcoded one, or a
 * server-side settings endpoint this screen could write to — neither
 * exists yet. A tool the org adds itself ("custom") never has a connector:
 * it records that the org has that source, nothing more.
 *
 * Storage is per-browser (`localStorage`), not per-organization: it can
 * come back empty in a private window, on another device, or if site data
 * is cleared. That's an accepted limit of "for now, local storage."
 */

/** A tool the org named itself, under one of the catalog's categories. */
export interface CustomTool {
  /** `custom:<uuid>`; also its entry in the selection list when picked. */
  id: string;
  name: string;
  category: ToolCategory;
}

/** Prefix that marks a selection id as a custom tool rather than a catalog one. */
export const CUSTOM_TOOL_PREFIX = "custom:";

const selection = createLocalStore<string[]>("suraksha.tools.selected", (raw) =>
  Array.isArray(raw) && raw.every((v) => typeof v === "string") ? raw : undefined,
);

const customTools = createLocalStore<CustomTool[]>("suraksha.tools.custom", (raw) =>
  Array.isArray(raw) &&
  raw.every(
    (t) =>
      typeof t === "object" &&
      t !== null &&
      typeof t.id === "string" &&
      t.id.startsWith(CUSTOM_TOOL_PREFIX) &&
      typeof t.name === "string" &&
      CATEGORY_ORDER.includes(t.category),
  )
    ? (raw as CustomTool[])
    : undefined,
);

/** Save the selected tool ids, or clear it (`null`) to make setup run again. */
export function saveToolSelection(toolIds: string[] | null): void {
  selection.save(toolIds);
}

/**
 * The saved tool ids, or `undefined` if setup has never been completed.
 * `null` during server render / before the browser value is known — every
 * caller must treat that the same as "don't know yet", never as "empty".
 */
export function useToolSelection(): string[] | undefined | null {
  return selection.use();
}

/** Save the org's own tools (the full list, replacing what was saved). */
export function saveCustomTools(tools: CustomTool[]): void {
  customTools.save(tools);
}

/** The org's own tools; `null` / `undefined` as for {@link useToolSelection}. */
export function useCustomTools(): CustomTool[] | undefined | null {
  return customTools.use();
}
