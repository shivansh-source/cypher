"use client";

import { usePathname } from "next/navigation";
import { AskSurakshaTrigger } from "./AskSuraksha";

const VIEWS: { prefix: string; eyebrow: string; title: string }[] = [
  { prefix: "/assets", eyebrow: "Technical view", title: "Assets & findings" },
  { prefix: "/attack-paths", eyebrow: "Threat view", title: "Attack paths" },
  { prefix: "/investment", eyebrow: "Budget decision", title: "Investment optimization" },
  { prefix: "/compliance", eyebrow: "Governance view", title: "Compliance & frameworks" },
  { prefix: "/data-quality", eyebrow: "Provenance view", title: "Data quality & coverage" },
];

const OVERVIEW = { eyebrow: "Executive view", title: "Exposure overview" };

/** Page eyebrow and title for the current route, and the Ask Cypher entry point. */
export function Topbar() {
  const pathname = usePathname();
  // The tool selector is a standalone page with its own header (see AppShell's STANDALONE_ROUTES).
  if (pathname.startsWith("/setup")) return null;
  const view = VIEWS.find((v) => pathname.startsWith(v.prefix)) ?? OVERVIEW;
  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">{view.eyebrow}</div>
        <h1>{view.title}</h1>
      </div>
      <AskSurakshaTrigger />
    </header>
  );
}
