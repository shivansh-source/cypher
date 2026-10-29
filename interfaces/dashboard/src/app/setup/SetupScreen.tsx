"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { CypherMark } from "@/components/CypherMark";
import { Spinner } from "@/components/Loader";
import { InfoTip } from "@/components/InfoTip";
import { OrgProfile } from "@/components/onboarding/OrgProfile";
import { TelemetryMap } from "@/components/onboarding/TelemetryMap";
import { groupId, ToolGroup } from "@/components/onboarding/ToolGroup";
import { coverageByCategory } from "@/lib/coverage";
import type { EntityType } from "@/lib/frameworks";
import { saveSetup } from "@/app/(auth)/actions";
import { CATEGORY_INFO, CATEGORY_ORDER, TOOL_CATALOG, type ToolCategory } from "@/lib/tool-catalog";
import { CUSTOM_TOOL_PREFIX, type CustomTool } from "@/lib/tool-selection-state";
import type { OrgState } from "@/lib/org-repo";

const AVAILABLE_IDS = TOOL_CATALOG.filter((t) => t.available).map((t) => t.id);

/** The catalog grouped by category, in display order — static, computed once. */
const GROUPS = CATEGORY_ORDER.map((category) => ({
  category,
  tools: TOOL_CATALOG.filter((t) => t.category === category),
}));

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Onboarding: who the org is and which security tools it runs. A standalone
 * page (no app frame) and the first thing a browser with no saved selection
 * sees. Saved to this browser only — see `tool-selection-state.ts` for
 * exactly what that does and doesn't control today, which the page states
 * plainly too.
 */
export function SetupScreen({ initial }: { initial: OrgState }) {
  const router = useRouter();
  const params = useSearchParams();
  const isFirstRun = params.get("first") === "1";
  const hasSaved = initial.onboarded;

  const [selected, setSelected] = useState<Set<string>>(() => new Set(initial.toolIds));
  const [custom, setCustom] = useState<CustomTool[]>(initial.customTools);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [entityType, setEntityType] = useState<EntityType | null>(initial.entityType);
  const [touched, setTouched] = useState(false);
  const [pulse, setPulse] = useState<{ category: ToolCategory; n: number } | null>(null);
  const [freshId, setFreshId] = useState<string | null>(null);
  const seeded = true; // the form starts from the server's data; nothing to wait for

  function categoryOf(id: string): ToolCategory | undefined {
    return (TOOL_CATALOG.find((t) => t.id === id) ?? custom.find((t) => t.id === id))?.category;
  }

  function signal(category: ToolCategory | undefined) {
    if (category) setPulse((current) => ({ category, n: (current?.n ?? 0) + 1 }));
  }

  function toggle(id: string) {
    setTouched(true);
    const adding = !selected.has(id);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    if (adding) signal(categoryOf(id));
  }

  function addTool(category: ToolCategory, toolName: string) {
    setTouched(true);
    const key = toolName.toLowerCase();
    const existing =
      TOOL_CATALOG.find((t) => t.category === category && t.name.toLowerCase() === key) ??
      custom.find((t) => t.category === category && t.name.toLowerCase() === key);
    const id = existing?.id ?? `${CUSTOM_TOOL_PREFIX}${crypto.randomUUID()}`;
    if (!existing) {
      setCustom((current) => [...current, { id, name: toolName, category }]);
      setFreshId(id);
    }
    setSelected((current) => new Set(current).add(id));
    signal(category);
  }

  function removeTool(id: string) {
    setTouched(true);
    setCustom((current) => current.filter((t) => t.id !== id));
    setSelected((current) => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  }

  function useOurs() {
    setTouched(true);
    setSelected(new Set(AVAILABLE_IDS));
  }

  function jump(category: ToolCategory) {
    const section = document.getElementById(groupId(category));
    section?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    section?.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    const customIds = new Set(custom.map((t) => t.id));
    const ids = Array.from(selected).filter((id) => !id.startsWith(CUSTOM_TOOL_PREFIX) || customIds.has(id));
    const result = await saveSetup({
      entityType,
      tools: ids.map((id) => {
        const c = custom.find((t) => t.id === id);
        return c ? { id, name: c.name, category: c.category } : { id };
      }),
    });
    if (!result.ok) {
      setSaving(false);
      setSaveError(result.error ?? "We couldn't save your selection.");
      return;
    }
    router.push("/");
    router.refresh();
  }

  const coverage = coverageByCategory(selected, custom);
  const count = selected.size;
  const withConnector = Array.from(selected).filter((id) => AVAILABLE_IDS.includes(id)).length;
  const gaps = coverage.filter((c) => c.state === "off");
  const welcome = isFirstRun || !hasSaved;

  return (
    <div className={`ob${seeded ? " ready" : ""}${touched ? " touched" : ""}`}>
      <aside className="ob-rail">
        <div className="ob-top">
          <div className="brand" aria-label="Cypher">
            <div className="mark" aria-hidden="true">
              <CypherMark />
            </div>
            <div className="word">Cypher</div>
          </div>
          <div className="ob-top-actions">
            {hasSaved ? (
              <button type="button" className="btn ghost" onClick={() => router.push("/")}>
                Back to the dashboard
              </button>
            ) : null}
            <LogoutButton />
          </div>
        </div>

        <section className="ob-hero">
          <h1>{welcome ? "Set up Cypher for your organisation" : "Your data sources"}</h1>
          <p className="ob-lead">
            Cypher turns what your security tools report into risk in rupees. Tell it which tools
            you run: it can only price what they see.
          </p>
        </section>

        <TelemetryMap
          coverage={coverage}
          pulse={pulse}
          intro={seeded && !hasSaved}
          animate={touched}
          onJump={jump}
        />

        <p className="ob-gaps" aria-live="polite">
          {count === 0
            ? "Pick at least one tool to continue."
            : gaps.length === 0
              ? "Every kind of telemetry the engine uses has a source."
              : `Without ${gaps.map((g) => CATEGORY_INFO[g.category].short.toLowerCase()).join(", ")}, the figures will have ${gaps
                  .map((g) => CATEGORY_INFO[g.category].gap)
                  .join("; ")}.`}
        </p>

        <div className="ob-cta">
          <div className="ob-summary">
            <span>
              <b>{count}</b> picked
              {withConnector > 0 ? <span className="muted">, {withConnector} connect today</span> : null}
            </span>
            {!touched && seeded && !hasSaved ? (
              <button type="button" className="linkbtn" onClick={useOurs}>
                Pick the tools Cypher connects to today
              </button>
            ) : null}
          </div>
          <button type="button" className="btn ob-go" disabled={count === 0 || saving} onClick={save}>
            {saving ? (
              <>
                <Spinner /> Saving…
              </>
            ) : hasSaved && !isFirstRun ? "Save changes" : "Continue to the dashboard"}
          </button>
          {saveError ? (
            <p className="auth-err" role="alert">
              {saveError}
            </p>
          ) : null}
          <p className="ob-scope">
            Saved to your organisation.
            <InfoTip id="setup-scope" label="What this does and doesn't do">
              This records which tools your org has in place. It doesn&apos;t yet change which
              connector code runs: <code>cypher ingest</code> always tries the same fixed set of
              connectors, and each one runs only if its own environment variables are configured.
              Treat it as the record of your estate, not a switch, until that wiring exists.
            </InfoTip>
          </p>
        </div>
      </aside>

      <div className="ob-main">
        <OrgProfile
          entityType={entityType}
          onEntityType={(value) => {
            setTouched(true);
            setEntityType(value);
          }}
        />
        {GROUPS.map(({ category, tools }) => (
          <ToolGroup
            key={category}
            category={category}
            tools={tools}
            customTools={custom.filter((t) => t.category === category)}
            state={coverage.find((c) => c.category === category)?.state ?? "off"}
            selected={selected}
            onToggle={toggle}
            onAdd={addTool}
            onRemove={removeTool}
            freshId={freshId}
          />
        ))}
      </div>
    </div>
  );
}
