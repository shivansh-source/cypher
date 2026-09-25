"use client";

import Link from "next/link";
import { useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import { useAgentPanelOpen, useAgentPanelWidth } from "@/lib/agent-panel-state";
import { AskSurakshaPanel } from "./AskSuraksha";
import { Nav } from "./Nav";
import { SnapCard } from "./SnapCard";

/*
 * Sidebar collapse state, persisted per browser. A per-viewer convenience
 * only: if storage is unavailable (private mode, blocked site data) the
 * toggle still works for the session, it just isn't remembered.
 */
const STORAGE_KEY = "suraksha.sidebar";
const listeners = new Set<() => void>();
let collapsedMemo: boolean | null = null;

function readCollapsed(): boolean {
  if (collapsedMemo === null) {
    try {
      collapsedMemo = window.localStorage.getItem(STORAGE_KEY) === "collapsed";
    } catch {
      collapsedMemo = false;
    }
  }
  return collapsedMemo;
}

function writeCollapsed(collapsed: boolean): void {
  collapsedMemo = collapsed;
  try {
    window.localStorage.setItem(STORAGE_KEY, collapsed ? "collapsed" : "open");
  } catch {
    // Remembered for this page view only.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    collapsedMemo = null;
    listener();
  };
  listeners.add(listener);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** The app frame: collapsible sidebar (brand, nav, current snapshot) beside the page. */
export function AppShell({ children }: { children: ReactNode }) {
  const collapsed = useSyncExternalStore(subscribe, readCollapsed, () => false);
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  const agentOpen = useAgentPanelOpen();
  const agentWidth = useAgentPanelWidth();

  return (
    <div
      className={`app${collapsed ? " collapsed" : ""}${agentOpen ? " agent-open" : ""}`}
      style={{ "--panel-w": `${agentOpen ? agentWidth : 0}px` } as CSSProperties}
    >
      <aside className="side">
        <div className="brand-wrap">
          <Link href="/" className="brand" aria-label="Su₹aksha — exposure overview">
            <div className="mark" aria-hidden="true">
              ₹
            </div>
            <div className="brand-text">
              <div className="word">
                Su<b>₹</b>aksha
              </div>
              <div className="tag">CYBER RISK, IN RUPEES</div>
            </div>
          </Link>
          <button
            className="collapse-btn"
            type="button"
            aria-expanded={!collapsed}
            aria-controls="sideNav"
            title={label}
            onClick={() => writeCollapsed(!collapsed)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M14.5 6.5L9 12l5.5 5.5" />
            </svg>
            <span className="t">{label}</span>
          </button>
        </div>
        <Nav />
        <div className="side-foot">
          <SnapCard />
        </div>
      </aside>
      {children}
      <AskSurakshaPanel />
    </div>
  );
}
