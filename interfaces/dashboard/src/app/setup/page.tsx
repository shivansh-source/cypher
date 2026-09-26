"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type CSSProperties } from "react";
import { InfoTip } from "@/components/InfoTip";
import { CATEGORY_ORDER, TOOL_CATALOG, type ToolCategory } from "@/lib/tool-catalog";
import { saveToolSelection, useToolSelection } from "@/lib/tool-selection-state";

const AVAILABLE_IDS = TOOL_CATALOG.filter((t) => t.available).map((t) => t.id);

/** The catalog grouped by category, in display order — static, computed once. */
const GROUPS = CATEGORY_ORDER.map((category) => ({
  category,
  tools: TOOL_CATALOG.filter((t) => t.category === category),
}));

/** What a gap in each category means for the figures, in the engine's own terms. */
const GAP_MEANING: Record<ToolCategory, string> = {
  "Vulnerability scanning": "no host or network vulnerabilities",
  "Cloud security posture": "no cloud misconfigurations",
  "Endpoint detection & response": "no EDR credit on any asset",
  "Identity & access": "no MFA or privilege posture",
  "Network exposure": "no open-port exposure",
  "Asset inventory": "no canonical asset identity",
};

export default function SetupPage() {
  return (
    <Suspense fallback={null}>
      <SetupScreen />
    </Suspense>
  );
}

/**
 * The tool selector: which security tools this org uses. A standalone page
 * (no app frame) and the first thing a browser with no saved selection sees.
 * Saved to this browser only — see `tool-selection-state.ts` for exactly what
 * that does and doesn't control today, which the page states plainly too.
 */
function SetupScreen() {
  const router = useRouter();
  const params = useSearchParams();
  const isFirstRun = params.get("first") === "1";
  const saved = useToolSelection();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [touched, setTouched] = useState(false);
  // `saved` starts as `null` (storage not read yet) and resolves after hydration. Seed the
  // checkboxes from it once, on that transition — adjusting state during render rather than in
  // an effect, so a later edit is never overwritten.
  const [priorSaved, setPriorSaved] = useState<string[] | null | undefined>(null);
  if (saved !== priorSaved) {
    setPriorSaved(saved);
    if (saved !== null && !touched) setSelected(new Set(saved ?? []));
  }
  const synced = priorSaved !== null;
  const hasSaved = Array.isArray(saved);

  function toggle(id: string) {
    setTouched(true);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function useOurs() {
    setTouched(true);
    setSelected(new Set(AVAILABLE_IDS));
  }

  function save() {
    saveToolSelection(Array.from(selected));
    router.push("/");
  }

  const count = selected.size;
  const withConnector = Array.from(selected).filter((id) => AVAILABLE_IDS.includes(id)).length;
  const covered = GROUPS.map(({ category, tools }) => ({
    category,
    picked: tools.filter((t) => selected.has(t.id)).length,
  }));
  const gaps = covered.filter((c) => c.picked === 0);

  return (
    <div className="onb">
      <aside className="onb-rail">
        <div className="onb-top">
          <div className="brand" aria-label="Cypher">
            <div className="mark" aria-hidden="true">
              C
            </div>
            <div className="word">Cypher</div>
          </div>
          {hasSaved ? (
            <button type="button" className="btn ghost" onClick={() => router.push("/")}>
              Back to the dashboard
            </button>
          ) : null}
        </div>

        <section className="onb-hero">
          <h1>{isFirstRun || !hasSaved ? "Which tools does your org already run?" : "Your data sources"}</h1>
          <p className="onb-lead">
            Every rupee figure starts from findings a tool reported. Pick each scanner, endpoint
            agent, identity source and inventory you have in place — Cypher only sees what these
            tools see.
          </p>
          <p className="onb-scope">
            Saved in this browser only, not yet connected to the ingest pipeline.
            <InfoTip id="setup-scope" label="What this does and doesn't do">
              This selection isn&apos;t sent anywhere. It doesn&apos;t yet change which connector code
              runs: <code>riskctl ingest</code> always tries the same fixed set of connectors, and
              each one runs only if its own environment variables are configured. Treat this as the
              record of what your org has in place, not a switch, until that wiring exists.
            </InfoTip>
          </p>
        </section>

        <section className="onb-coverage" aria-label="Coverage of your picks">
          <h2>Coverage</h2>
          <ol>
            {covered.map((c) => (
              <li key={c.category} className={c.picked ? "on" : undefined}>
                <span className="lbl">{c.category}</span>
                <span className="cnt">{c.picked ? `${c.picked} picked` : "Not covered"}</span>
                <span className="cov-seg" aria-hidden="true" />
              </li>
            ))}
          </ol>
          <p className="onb-gaps">
            {count === 0
              ? "Pick at least one tool to continue."
              : gaps.length === 0
                ? "Every kind of telemetry the engine uses has a source."
                : `Without a source for ${gaps
                    .map((g) => g.category.toLowerCase())
                    .join(", ")}, the figures will have ${gaps
                    .map((g) => GAP_MEANING[g.category])
                    .join("; ")}.`}
          </p>
        </section>

        <div className="onb-cta">
          <div className="onb-summary">
            <span>
              <b>{count}</b> selected
              {withConnector > 0 ? (
                <span className="muted">, {withConnector} with a connector today</span>
              ) : null}
            </span>
            {!touched && synced && !hasSaved ? (
              <button type="button" className="linkbtn" onClick={useOurs}>
                Select the tools already configured
              </button>
            ) : null}
          </div>
          <button type="button" className="btn" disabled={count === 0} onClick={save}>
            {hasSaved ? "Save changes" : "Continue to the dashboard"}
          </button>
        </div>
      </aside>

      <div className="onb-main">
        {GROUPS.map(({ category, tools }) => (
          <section key={category} className="onb-group" aria-labelledby={`grp-${category}`}>
            <h2 id={`grp-${category}`}>{category}</h2>
            <div className="onb-cards">
              {tools.map((tool) => {
                const on = selected.has(tool.id);
                return (
                  <label
                    key={tool.id}
                    className={`tool${on ? " on" : ""}${tool.available ? "" : " soon"}`}
                    style={{ "--tone": `var(--s${tool.tone})` } as CSSProperties}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={on}
                      onChange={() => toggle(tool.id)}
                      aria-describedby={`${tool.id}-status`}
                    />
                    <span className="tool-check" aria-hidden="true">
                      <svg viewBox="0 0 16 16">
                        <path d="M3.5 8.5l3 3 6-7" />
                      </svg>
                    </span>
                    <span className={`tool-icon${tool.logo ? " has-logo" : ""}`} aria-hidden="true">
                      {tool.logo ? (
                        // Local, small, fixed-size logos: next/image's resizing buys nothing here.
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={tool.logo} alt="" width={52} height={52} loading="lazy" />
                      ) : (
                        tool.mark
                      )}
                    </span>
                    <b className="tool-name">{tool.name}</b>
                    <span className="tool-blurb">{tool.blurb}</span>
                    <span id={`${tool.id}-status`} className="tool-status">
                      {tool.available ? "Connector available" : "No connector yet"}
                    </span>
                  </label>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
