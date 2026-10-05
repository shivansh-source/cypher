"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";
import { useAgentPanelOpen, useAgentPanelWidth } from "@/lib/agent-panel-state";
import { ENTITY_TYPES } from "@/lib/frameworks";
import { isStandaloneRoute } from "@/lib/route-gate";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { logout } from "@/app/(auth)/actions";
import { AskSurakshaPanel } from "./AskSuraksha";
import { CypherMark } from "./CypherMark";
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

/**
 * Routes whose page is a full-bleed canvas: the sidebar starts collapsed there
 * on every visit, and toggling it only lasts for that visit — the viewer's
 * saved preference for every other page is left alone.
 */
const CANVAS_ROUTES = ["/attack-paths"];


/** The app frame: collapsible sidebar (brand, nav, current snapshot) beside the page. */
export function AppShell({
  children,
  org,
}: {
  children: ReactNode;
  /** From the session token (verified on the server); `null` when signed out. */
  org: { name: string; entityType: string | null } | null;
}) {
  const pathname = usePathname();
  const canvas = CANVAS_ROUTES.some((route) => pathname.startsWith(route));
  const stored = useSyncExternalStore(subscribe, readCollapsed, () => false);
  const [expandedOnCanvas, setExpandedOnCanvas] = useState(false);
  // Leaving a canvas route forgets the temporary expansion, so the next visit
  // starts collapsed again (state adjusted during render, not in an effect).
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    setLastPath(pathname);
    if (expandedOnCanvas) setExpandedOnCanvas(false);
  }
  const collapsed = canvas ? !expandedOnCanvas : stored;
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  const agentOpen = useAgentPanelOpen();
  const agentWidth = useAgentPanelWidth();
  const orgKind = ENTITY_TYPES.find((t) => t.id === org?.entityType)?.label;

  if (isStandaloneRoute(pathname)) {
    return <div className="standalone">{children}</div>;
  }
  return (
    <div
      className={`app${collapsed ? " collapsed" : ""}${agentOpen ? " agent-open" : ""}${canvas ? " canvas-route" : ""}`}
      style={{ "--panel-w": `${agentOpen ? agentWidth : 0}px` } as CSSProperties}
    >
      <aside className="side">
        <div className="brand-wrap">
          <Link href="/" className="brand" aria-label="Cypher — exposure overview">
            <div className="mark" aria-hidden="true">
              <CypherMark />
            </div>
            <div className="brand-text">
              <div className="word">
                Cypher
              </div>
              {org?.name ? (
                <div className="tag org" title={orgKind ? `${org.name} (${orgKind})` : org.name}>
                  {org.name}
                  {orgKind ? <span className="org-kind">{orgKind}</span> : null}
                </div>
              ) : (
                <div className="tag">CYBER RISK, IN RUPEES</div>
              )}
            </div>
          </Link>
          <button
            className="collapse-btn"
            type="button"
            aria-expanded={!collapsed}
            aria-controls="sideNav"
            title={label}
            onClick={() => (canvas ? setExpandedOnCanvas(collapsed) : writeCollapsed(!collapsed))}
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
          <form action={logout}>
            <LogoutButton />
          </form>
        </div>
      </aside>
      {children}
      <AskSurakshaPanel />
    </div>
  );
}
