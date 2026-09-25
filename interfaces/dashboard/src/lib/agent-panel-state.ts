"use client";

import { useSyncExternalStore } from "react";

/*
 * Ask Suraksha's docked-panel state: open/closed and width, each persisted
 * per browser (a per-viewer convenience only — see AppShell's sidebar
 * collapse state, which this mirrors). Lives outside the component tree so
 * the trigger button in Topbar and the panel itself in AppShell can both
 * read and drive it without a shared parent re-render.
 */

const OPEN_KEY = "suraksha.agentpanel.open";
const WIDTH_KEY = "suraksha.agentpanel.width";

export const AGENT_PANEL_MIN_WIDTH = 320;
export const AGENT_PANEL_MAX_WIDTH = 640;
export const AGENT_PANEL_DEFAULT_WIDTH = 400;

let openMemo: boolean | null = null;
let widthMemo: number | null = null;
const openListeners = new Set<() => void>();
const widthListeners = new Set<() => void>();

function clampWidth(width: number): number {
  return Math.min(AGENT_PANEL_MAX_WIDTH, Math.max(AGENT_PANEL_MIN_WIDTH, width));
}

function readOpen(): boolean {
  if (openMemo === null) {
    try {
      openMemo = window.localStorage.getItem(OPEN_KEY) === "open";
    } catch {
      openMemo = false;
    }
  }
  return openMemo;
}

function writeOpen(open: boolean): void {
  openMemo = open;
  try {
    window.localStorage.setItem(OPEN_KEY, open ? "open" : "closed");
  } catch {
    // Remembered for this page view only.
  }
  openListeners.forEach((listener) => listener());
}

function readWidth(): number {
  if (widthMemo === null) {
    try {
      const stored = Number(window.localStorage.getItem(WIDTH_KEY));
      widthMemo = Number.isFinite(stored) && stored > 0 ? clampWidth(stored) : AGENT_PANEL_DEFAULT_WIDTH;
    } catch {
      widthMemo = AGENT_PANEL_DEFAULT_WIDTH;
    }
  }
  return widthMemo;
}

function writeWidth(width: number): void {
  widthMemo = clampWidth(width);
  try {
    window.localStorage.setItem(WIDTH_KEY, String(widthMemo));
  } catch {
    // Remembered for this page view only.
  }
  widthListeners.forEach((listener) => listener());
}

function subscribe(listeners: Set<() => void>, key: string, invalidate: () => void) {
  return (listener: () => void): (() => void) => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== key) return;
      invalidate();
      listener();
    };
    listeners.add(listener);
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  };
}

const subscribeOpen = subscribe(openListeners, OPEN_KEY, () => {
  openMemo = null;
});
const subscribeWidth = subscribe(widthListeners, WIDTH_KEY, () => {
  widthMemo = null;
});

export function useAgentPanelOpen(): boolean {
  return useSyncExternalStore(subscribeOpen, readOpen, () => false);
}

export function useAgentPanelWidth(): number {
  return useSyncExternalStore(subscribeWidth, readWidth, () => AGENT_PANEL_DEFAULT_WIDTH);
}

export function openAgentPanel(): void {
  writeOpen(true);
}

export function closeAgentPanel(): void {
  writeOpen(false);
}

export function toggleAgentPanel(): void {
  writeOpen(!readOpen());
}

export function setAgentPanelWidth(width: number): void {
  writeWidth(width);
}
