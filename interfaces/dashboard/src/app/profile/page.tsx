import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Card } from "@/components/Card";
import { Kpi, KpiStrip } from "@/components/Kpi";
import { Lede } from "@/components/Lede";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { fetchDemoCredentials } from "@/lib/demo-account";
import { formatDate } from "@/lib/format";
import { ENTITY_TYPES, frameworkLabel, frameworksForEntity } from "@/lib/frameworks";
import { loadOrgState, type OrgState } from "@/lib/org-repo";
import { CATEGORY_INFO, CATEGORY_ORDER, TOOL_CATALOG, type ToolCategory } from "@/lib/tool-catalog";

export const metadata: Metadata = { title: "Profile · Cypher" };

/** One selected tool as the profile lists it: a catalog entry or one the org named itself. */
interface ProfileTool {
  id: string;
  name: string;
  blurb: string;
  available: boolean;
  logo?: string;
  mark: string;
  tone: string;
}

function selectedTools(org: OrgState): Map<ToolCategory, ProfileTool[]> {
  const byCategory = new Map<ToolCategory, ProfileTool[]>(CATEGORY_ORDER.map((c) => [c, []]));
  for (const id of org.toolIds) {
    const known = TOOL_CATALOG.find((t) => t.id === id);
    if (known) {
      byCategory.get(known.category)?.push({
        id,
        name: known.name,
        blurb: known.blurb,
        available: known.available,
        logo: known.logo,
        mark: known.mark,
        tone: `var(--s${known.tone})`,
      });
      continue;
    }
    const custom = org.customTools.find((t) => t.id === id);
    if (custom) {
      byCategory.get(custom.category)?.push({
        id,
        name: custom.name,
        blurb: "Added by your organisation",
        available: false,
        mark: custom.name.trim().slice(0, 2).toUpperCase() || "?",
        tone: "var(--other)",
      });
    }
  }
  return byCategory;
}

/**
 * The signed-in user's account, their organisation's declared setup (entity type
 * and tools, as stored in the database), the frameworks that setup implies, and
 * sign-out. Everything here is declared context: it never changes a figure.
 */
export default async function ProfilePage() {
  const [org, demo] = await Promise.all([loadOrgState(), fetchDemoCredentials()]);
  if (!org) redirect("/login");

  const isDemo = demo !== null && demo.email === org.email;
  const entity = ENTITY_TYPES.find((t) => t.id === org.entityType) ?? null;
  const frameworks = org.entityType ? frameworksForEntity(org.entityType) : null;
  const tools = selectedTools(org);
  const all = [...tools.values()].flat();
  const connected = all.filter((t) => t.available).length;
  const covered = CATEGORY_ORDER.filter((c) => (tools.get(c) ?? []).length > 0);
  const gaps = CATEGORY_ORDER.filter((c) => !covered.includes(c));

  return (
    <div className="grid">
      {isDemo ? (
        <Lede tone="info" icon="i" title="You're signed in to the shared demo account">
          Anyone can use it, so the tool selection goes back to the demo organisation&apos;s own
          setup at the next demo sign-in. Register to keep your own.
        </Lede>
      ) : null}

      <KpiStrip>
        <Kpi label="Organisation" value={org.name} note={entity ? entity.label : "Entity type not set"} />
        <Kpi
          label="Tools declared"
          value={String(all.length)}
          note={`${connected} connect today · ${all.length - connected} declare only`}
        />
        <Kpi
          label="Telemetry covered"
          value={`${covered.length} / ${CATEGORY_ORDER.length}`}
          note={gaps.length === 0 ? "Every category has a source" : `Missing: ${gaps.map((c) => CATEGORY_INFO[c].short).join(", ")}`}
        />
        <Kpi
          label="Frameworks that apply"
          value={frameworks ? String(frameworks.mandatory.length) : "—"}
          note={frameworks ? `plus ${frameworks.voluntary.length} voluntary baseline${frameworks.voluntary.length === 1 ? "" : "s"}` : "Set an entity type to see them"}
        />
      </KpiStrip>

      <div className="grid g-2" style={{ alignItems: "start" }}>
        <Card
          title="Security tools"
          subtitle="What your organisation told Cypher it runs, by the kind of telemetry each one feeds."
          actions={
            <Link className="btn ghost" href="/setup">
              Edit tools
            </Link>
          }
        >
          <div className="pf-cats">
            {CATEGORY_ORDER.map((category) => {
              const list = tools.get(category) ?? [];
              return (
                <section className="pf-cat" key={category} aria-label={category}>
                  <div className="pf-cat-h">
                    <b>{category}</b>
                    <span className="small muted">{CATEGORY_INFO[category].feeds}</span>
                  </div>
                  {list.length === 0 ? (
                    <p className="pf-gap small">
                      No source declared, so the figures have {CATEGORY_INFO[category].gap}.
                    </p>
                  ) : (
                    <ul className="pf-tools">
                      {list.map((tool) => (
                        <li key={tool.id} className="pf-tool" style={{ "--tone": tool.tone } as CSSProperties}>
                          <span className={`ob-icon${tool.logo ? " has-logo" : ""}`} aria-hidden="true">
                            {tool.logo ? (
                              // Local, small, fixed-size logos: next/image's resizing buys nothing here.
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={tool.logo} alt="" width={26} height={26} loading="lazy" />
                            ) : (
                              tool.mark
                            )}
                          </span>
                          <span className="pf-tool-text">
                            <b>{tool.name}</b>
                            <span className="small muted">{tool.blurb}</span>
                          </span>
                          <span className={`pf-badge${tool.available ? " live" : ""}`}>
                            {tool.available ? "Connects today" : "Declare only"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              );
            })}
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>
            This records what you run. It doesn&apos;t yet decide which connectors{" "}
            <code>cypher ingest</code> executes, and a declared tool with no connector adds no
            findings.
          </p>
        </Card>

        <div className="grid">
          <Card title="Account">
            <dl className="pf-dl">
              <dt>Email</dt>
              <dd>{org.email}</dd>
              <dt>Organisation</dt>
              <dd>{org.name}</dd>
              <dt>Entity type</dt>
              <dd>
                {entity ? (
                  <>
                    {entity.label} <span className="small muted">· {entity.hint}</span>
                  </>
                ) : (
                  <span className="muted">Not set</span>
                )}
              </dd>
              {org.memberSince ? (
                <>
                  <dt>Member since</dt>
                  <dd>{formatDate(org.memberSince)}</dd>
                </>
              ) : null}
            </dl>
          </Card>

          <Card
            title="Regulatory frameworks"
            subtitle="Which of the control libraries apply to your entity type. Compliance still evaluates every library."
          >
            {frameworks ? (
              <div className="pf-fw">
                <div>
                  <span className="small muted">Mandatory</span>
                  <div className="pf-chips">
                    {frameworks.mandatory.map((key) => (
                      <Link key={key} className="pf-chip strong" href={`/compliance?framework=${key}`}>
                        {frameworkLabel(key)}
                      </Link>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="small muted">Voluntary baselines</span>
                  <div className="pf-chips">
                    {frameworks.voluntary.map((key) => (
                      <Link key={key} className="pf-chip" href={`/compliance?framework=${key}`}>
                        {frameworkLabel(key)}
                      </Link>
                    ))}
                  </div>
                </div>
                {frameworks.note ? <p className="small muted">{frameworks.note}</p> : null}
              </div>
            ) : (
              <p className="small muted">
                Set your entity type on the <Link href="/setup">tool selection page</Link> to see
                which frameworks apply.
              </p>
            )}
          </Card>

          <Card title="Session" subtitle="Signing out clears this browser's session.">
            <LogoutButton />
          </Card>
        </div>
      </div>
    </div>
  );
}
