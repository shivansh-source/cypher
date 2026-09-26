"use client";

import { useSyncExternalStore } from "react";

/**
 * Which tools an org says it uses, persisted in this browser only.
 *
 * IMPORTANT — what this does and doesn't do: this selection is read only by
 * the dashboard itself (to show it back, and to decide whether to show the
 * first-run setup screen). Nothing on the backend reads it. Today,
 * `interfaces/cli/riskctl.py::ingest_command` runs a fixed, hardcoded list
 * of connectors (Wazuh, Greenbone, Prowler, ScoutSuite, the AWS IAM
 * connector, and the CMDB connector); which of those actually run is
 * decided by whether each one's own environment variables are configured,
 * not by anything a person picks in a UI. Making this selection actually
 * gate which connector code runs would mean either teaching
 * `ingest_command` to read a config list instead of a hardcoded one, or a
 * server-side settings endpoint this screen could write to — neither
 * exists yet.
 *
 * Storage is per-browser (`localStorage`), not per-organization: it can
 * come back empty in a private window, on another device, or if site data
 * is cleared. That's an accepted limit of "for now, local storage."
 */

const STORAGE_KEY = "suraksha.tools.selected";

const listeners = new Set<() => void>();
/** `null` = not yet read from storage; `undefined` after that means "nothing saved". */
let memo: string[] | null | undefined = null;

function readRaw(): string[] | undefined {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return undefined;
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.every((v) => typeof v === "string") ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function read(): string[] | undefined {
  if (memo === null) memo = readRaw() ?? undefined;
  return memo;
}

function subscribe(listener: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY && event.key !== null) return;
    memo = null;
    listener();
  };
  listeners.add(listener);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Save the selected tool ids, or clear it (`null`) to make setup run again. */
export function saveToolSelection(toolIds: string[] | null): void {
  memo = toolIds ?? undefined;
  try {
    if (toolIds === null) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, JSON.stringify(toolIds));
  } catch {
    // Remembered for this page view only.
  }
  listeners.forEach((listener) => listener());
}

/**
 * The saved tool ids, or `undefined` if setup has never been completed.
 * `null` during server render / before the browser value is known — every
 * caller must treat that the same as "don't know yet", never as "empty".
 */
export function useToolSelection(): string[] | undefined | null {
  return useSyncExternalStore(subscribe, read, () => null);
}
