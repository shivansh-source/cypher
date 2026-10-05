import type { ToolCategory } from "./tool-catalog";

/**
 * A tool the org named itself, under one of the catalog's categories.
 *
 * The selection itself (which tools an org runs) is stored per organisation in
 * the database and loaded by the setup page; nothing is kept in the browser.
 * It records what the org has in place and does not yet decide which connector
 * code runs: `cypher ingest` always tries the same fixed set of connectors,
 * each gated by its own environment variables. A custom tool never has a
 * connector: it records that the org has that source, nothing more.
 */
export interface CustomTool {
  /** `custom:<uuid>`; also its entry in the selection list when picked. */
  id: string;
  name: string;
  category: ToolCategory;
}

/** Prefix that marks a selection id as a custom tool rather than a catalog one. */
export const CUSTOM_TOOL_PREFIX = "custom:";
