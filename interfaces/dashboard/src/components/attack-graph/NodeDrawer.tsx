"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import type { ApiResult } from "@/lib/api";
import { formatCount, formatDecimal, formatInr, formatPercent } from "@/lib/format";
import { controlLabel, findingTitle, phrase, scannerLabel } from "@/lib/labels";
import type { AssetView, AttackGraphNode, AttackGraphResponse, AttackGraphTarget } from "@/lib/types";

/**
 * The panel that slides over the attack graph: one asset's detail, or the
 * network's topology. Every figure shown is engine output passed in from the
 * API (or, on the sample network, captured engine output); nothing here is
 * computed beyond formatting.
 */

export type TargetState = ApiResult<AttackGraphTarget> | { state: "loading" };
export type DrawerTab = "overview" | "routes" | "findings" | "path";

/**
 * Below this, a finding's reach-given-exploit is treated as the same as the
 * route's plain reach and not called out. Display threshold only.
 */
const CORRELATION_NOTE_MIN_DIFF = 0.005;

const ROLE_LABEL: Record<AttackGraphNode["role"], string> = {
  entry: "Entry point",
  reachable: "Reachable",
  unreachable: "No path in",
  unknown: "Segment unknown",
};

interface Common {
  graph: AttackGraphResponse;
  /** Display name per asset id (service names, or the id itself). */
  nameOf: (id: string) => string;
  onClose: () => void;
  onSelect: (assetId: string) => void;
  sample: boolean;
}

export function NodeDrawer({
  node,
  asset,
  target,
  tab,
  onTab,
  ...common
}: Common & {
  node: AttackGraphNode;
  asset: AssetView | null;
  target: TargetState | null;
  tab: DrawerTab;
  onTab: (tab: DrawerTab) => void;
}) {
  const { graph, nameOf, onClose, sample } = common;
  const segmentName = graph.segments.find((s) => s.segment_id === node.segment_id)?.name ?? node.segment_id;
  const openFindings = asset?.findings.filter((f) => f.scenario !== null) ?? [];
  const tabs: { id: DrawerTab; label: string; count?: number }[] = [
    { id: "overview", label: "Overview" },
    { id: "routes", label: "Routes in", count: node.routes.length },
    { id: "findings", label: "Findings", count: node.open_finding_count },
    { id: "path", label: "Path" },
  ];

  return (
    <aside className="gd" aria-labelledby="gd-title" data-canvas-ignore>
      <header className="gd-head">
        <div className="gd-kicker">
          <span className={`gd-role r-${node.role}`} aria-hidden="true" />
          Asset
          <span className="gd-actions">
            {!sample ? (
              <Link
                className="gd-icon"
                href={`/assets?asset=${encodeURIComponent(node.asset_id)}`}
                title="Open in Assets & findings"
                aria-label="Open in Assets & findings"
              >
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M9.5 2.5h4v4M13.5 2.5L7.5 8.5M12 9.5v4h-9.5v-9.5h4" />
                </svg>
              </Link>
            ) : null}
            <button className="gd-icon" type="button" onClick={onClose} title="Close (Esc)" aria-label="Close details">
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M4 4l8 8M12 4l-8 8" />
              </svg>
            </button>
          </span>
        </div>
        <h2 id="gd-title">{nameOf(node.asset_id)}</h2>
        <CopyId value={node.asset_id} />
        <div className="gd-badges">
          <span className="gd-badge">{ROLE_LABEL[node.role]}</span>
          {segmentName ? <span className="gd-badge">{segmentName}</span> : null}
          <span className="gd-badge">
            {formatCount(node.open_finding_count)} open finding{node.open_finding_count === 1 ? "" : "s"}
          </span>
          {node.kev_finding_count > 0 ? (
            <span className="gd-badge crit">{formatCount(node.kev_finding_count)} known exploited</span>
          ) : null}
          {asset?.expected_annual_loss_inr != null ? (
            <span className="gd-badge strong">EAL {formatInr(asset.expected_annual_loss_inr)}</span>
          ) : null}
        </div>
      </header>

      <nav className="gd-tabs" role="tablist" aria-label="Asset detail">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className="gd-tab"
            onClick={() => onTab(t.id)}
          >
            {t.label}
            {t.count !== undefined ? <span className="gd-count">{t.count}</span> : null}
          </button>
        ))}
      </nav>

      <div className="gd-body" role="tabpanel">
        {tab === "overview" ? (
          <Overview node={node} asset={asset} target={target} segmentName={segmentName} {...common} />
        ) : tab === "routes" ? (
          <Routes node={node} asset={asset} {...common} />
        ) : tab === "findings" ? (
          <Findings node={node} findings={openFindings} {...common} />
        ) : (
          <PathTab node={node} target={target} {...common} />
        )}
      </div>
    </aside>
  );
}

function CopyId({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="gd-id"
      title="Copy asset id"
      onClick={() => {
        void navigator.clipboard?.writeText(value).then(
          () => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1400);
          },
          () => undefined,
        );
      }}
    >
      <span className="mono">{value}</span>
      <span className="gd-copy">{copied ? "Copied" : "Copy"}</span>
    </button>
  );
}

function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="gd-sec">
      <div className="gd-sec-h">
        <h3>{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="gd-kv">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Overview({
  node,
  asset,
  target,
  segmentName,
}: Common & { node: AttackGraphNode; asset: AssetView | null; target: TargetState | null; segmentName: string | null }) {
  const perimeter = target?.state === "ok" ? target.data : null;
  const services = asset?.services ?? [];
  const edr = asset?.edr;
  const mfa = asset?.identity_access?.mfa_enforced;
  return (
    <>
      <Section title="What the graph says">
        <p className="gd-lead">{roleSentence(node)}</p>
        <Rows
          rows={[
            ["Role", ROLE_LABEL[node.role]],
            ["Segment", segmentName ?? <span className="muted">Not reported</span>],
            ["Routes in", node.role === "entry" ? "Attacked directly" : formatCount(node.routes.length)],
            [
              "Compromised, all entry points hit",
              perimeter ? (
                <span className="num">{formatPercent(perimeter.compromise_probability, 1)}</span>
              ) : (
                <PerimeterStatus node={node} target={target} />
              ),
            ],
            [
              "Reached, all entry points hit",
              perimeter ? (
                <span className="num">{formatPercent(perimeter.reached_probabilities[node.asset_id] ?? 0, 1)}</span>
              ) : (
                <PerimeterStatus node={node} target={target} />
              ),
            ],
          ]}
        />
      </Section>

      <Section title="Posture">
        <Rows
          rows={[
            ["Internet-facing", node.internet_facing ? "Yes" : "No"],
            [
              "Open ports",
              asset?.network?.open_ports?.length ? (
                <span className="mono">{asset.network.open_ports.join(", ")}</span>
              ) : (
                <span className="muted">None reported</span>
              ),
            ],
            [
              "EDR",
              !edr ? (
                <span className="muted">Not reported</span>
              ) : !edr.agent_installed ? (
                <span className="gd-flag crit">No agent</span>
              ) : edr.agent_healthy === false ? (
                <span className="gd-flag warn">Agent unhealthy</span>
              ) : (
                "Agent healthy"
              ),
            ],
            [
              "MFA",
              mfa === true ? "Enforced" : mfa === false ? <span className="gd-flag warn">Not enforced</span> : <span className="muted">Unknown</span>,
            ],
            ["Privileged accounts", asset?.identity_access?.privileged_accounts_count ?? <span className="muted">Unknown</span>],
          ]}
        />
      </Section>

      {services.length > 0 ? (
        <Section title="Services">
          <ul className="gd-list">
            {services.map((s) => (
              <li key={s.service_id}>
                <span>
                  <b>{s.name}</b>
                  <span className="sub">{describeBackup(s.backup)}</span>
                </span>
                <span className={`gd-badge${s.criticality === "critical" ? " crit" : ""}`}>{phrase(s.criticality)}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </>
  );
}

/** The service's backup facts as reported, in words. */
function describeBackup(b: AssetView["services"][number]["backup"]): string {
  if (!b.exists) return "No backup";
  const tested = b.last_tested_at ? "Backup restore-tested" : "Backup never restore-tested";
  return b.immutable_copy ? `${tested}, immutable copy` : tested;
}

function PerimeterStatus({ node, target }: { node: AttackGraphNode; target: TargetState | null }) {
  if (node.role === "unknown") return <span className="muted">Not in the graph</span>;
  if (!target || target.state === "loading") return <span className="gd-skel" aria-label="Loading" />;
  if (target.state !== "ok") return <span className="muted">{target.reason}</span>;
  return null;
}

function roleSentence(node: AttackGraphNode): string {
  switch (node.role) {
    case "entry":
      return "Internet-facing, so it is attacked directly at the rate for its exposure. Routes to other assets start here.";
    case "reachable":
      return `Not internet-facing. Attacks reach it through ${node.routes.length} entry point${node.routes.length === 1 ? "" : "s"}, and the engine sets its attack rate from those routes.`;
    case "unreachable":
      return "No internet-facing asset has a path here under the known topology, so the engine models no attacks reaching it. That holds only while the topology is complete.";
    case "unknown":
      return "Its segment is unknown, so the graph cannot say what reaches it. The engine scores it on its own exposure, without the graph. Unknown is not the same as unreachable.";
  }
}

function Routes({ node, asset, nameOf, onSelect }: Common & { node: AttackGraphNode; asset: AssetView | null }) {
  if (node.role !== "reachable") {
    return <p className="gd-empty">{roleSentence(node)}</p>;
  }
  const findingNames = Object.fromEntries((asset?.findings ?? []).map((f) => [f.finding_id, findingTitle(f)]));
  const notes = node.routes.flatMap((route) =>
    Object.entries(route.reach_given_finding)
      .filter(([, given]) => Math.abs(given - route.reach_probability) >= CORRELATION_NOTE_MIN_DIFF)
      .map(([findingId, given]) => ({ route, findingId, given })),
  );
  return (
    <>
      <Section title="Where attacks come from" aside={<span className="gd-hint">Share of arriving attacks</span>}>
        <ul className="gd-routes">
          {node.routes.map((route) => (
            <li key={route.entry_asset_id}>
              <button type="button" className="gd-row" onClick={() => onSelect(route.entry_asset_id)}>
                <span className="gd-row-main">
                  <b>{nameOf(route.entry_asset_id)}</b>
                  <span className="sub mono">{route.entry_asset_id}</span>
                </span>
                <span className="gd-bar" aria-hidden="true">
                  <i style={{ width: `${route.share * 100}%` }} />
                </span>
                <span className="num gd-row-fig">{formatPercent(route.share)}</span>
              </button>
              <span className="gd-row-sub">
                A campaign starting here gets through <span className="num">{formatPercent(route.reach_probability, 1)}</span> of the time
              </span>
            </li>
          ))}
        </ul>
      </Section>
      {notes.length > 0 ? (
        <Section title="Shared exploits">
          {notes.map(({ route, findingId, given }) => (
            <p key={`${route.entry_asset_id}:${findingId}`} className="gd-note">
              <b>{findingNames[findingId] ?? findingId}</b> is also open on an asset on the way in from{" "}
              {nameOf(route.entry_asset_id)}. When it works here, an attack from there arrives{" "}
              <span className="num">{formatPercent(given, 1)}</span> of the time, not{" "}
              <span className="num">{formatPercent(route.reach_probability, 1)}</span>. The engine uses the
              higher figure for this finding.
            </p>
          ))}
        </Section>
      ) : null}
    </>
  );
}

function Findings({
  node,
  findings,
  sample,
}: Common & { node: AttackGraphNode; findings: AssetView["findings"] }) {
  if (findings.length === 0) {
    return (
      <p className="gd-empty">
        {node.open_finding_count === 0
          ? "No open findings, so the engine models no loss on this asset. Attackers can still pass through it only if one of its findings works, so with none it stops them here."
          : "Finding detail comes from the asset inventory, which is not available for this snapshot."}
      </p>
    );
  }
  return (
    <ul className="gd-findings">
      {findings.map((finding) => {
        const s = finding.scenario;
        if (!s) return null;
        return (
          <li key={finding.finding_id}>
            <div className="gd-f-h">
              {sample ? (
                <b>{findingTitle(finding)}</b>
              ) : (
                <Link
                  className="rowlink"
                  href={`/assets?asset=${encodeURIComponent(node.asset_id)}&finding=${encodeURIComponent(finding.finding_id)}#finding-${encodeURIComponent(finding.finding_id)}`}
                >
                  {findingTitle(finding)}
                </Link>
              )}
              <span className="num gd-f-eal">{formatInr(s.expected_annual_loss_inr)}</span>
            </div>
            <div className="gd-badges tight">
              {finding.kev_listed ? <span className="gd-badge crit">KEV</span> : null}
              {finding.epss_score !== null ? <span className="gd-badge">EPSS {formatDecimal(finding.epss_score, 2)}</span> : null}
              {finding.cve_id ? null : <span className="gd-badge">{phrase(finding.type)}</span>}
              <span className="gd-badge">{scannerLabel(finding.provenance.connector).name}</span>
            </div>
            <dl className="gd-kv compact">
              <div>
                <dt>Attacks a year</dt>
                <dd className="num">
                  {formatDecimal(s.threat_event_frequency.most_likely, 2)}
                  <span className="sub">{s.graph_reachability_applied ? " via attack routes" : ` ${phrase(s.exposure_profile).toLowerCase()}`}</span>
                </dd>
              </div>
              <div>
                <dt>Chance one succeeds</dt>
                <dd className="num">
                  {formatPercent(s.vulnerability, 1)}
                  {Object.keys(s.active_control_resistances).length > 0 ? (
                    <span className="sub">
                      {" "}after {Object.keys(s.active_control_resistances).map(controlLabel).join(", ")}
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt>Expected annual loss</dt>
                <dd className="num">{formatInr(s.expected_annual_loss_inr)}</dd>
              </div>
            </dl>
          </li>
        );
      })}
    </ul>
  );
}

function PathTab({ node, target, nameOf, onSelect }: Common & { node: AttackGraphNode; target: TargetState | null }) {
  if (node.role === "unknown") {
    return (
      <p className="gd-empty">
        Nothing to simulate: with no segment reported, the graph has no path to follow to this asset.
      </p>
    );
  }
  if (!target || target.state === "loading") {
    return (
      <div className="gd-loading" aria-label="Loading">
        <span className="gd-skel" />
        <span className="gd-skel" />
        <span className="gd-skel" />
      </div>
    );
  }
  if (target.state !== "ok") return <p className="gd-empty">{target.reason}</p>;
  const t = target.data;
  const path = [...t.included_asset_ids].sort((a, b) => (t.node_probabilities[b] ?? 0) - (t.node_probabilities[a] ?? 0));
  return (
    <Section title="If every entry point is hit at once" aside={<span className="gd-hint">{formatCount(t.samples)} simulated attacks</span>}>
      <p className="gd-lead">
        A worst case for seeing the path as a whole: this asset is compromised in{" "}
        <b className="num">{formatPercent(t.compromise_probability, 1)}</b> of attacks. The engine&apos;s own figures use the
        separate routes instead, each at its entry point&apos;s own rate.
      </p>
      <table className="gd-table">
        <thead>
          <tr>
            <th scope="col">Asset on the way</th>
            <th scope="col" className="r">Reached</th>
            <th scope="col" className="r">Compromised</th>
          </tr>
        </thead>
        <tbody>
          {path.map((id) => (
            <tr key={id} className={id === node.asset_id ? "sel" : undefined}>
              <td>
                <button type="button" className="gd-link" onClick={() => onSelect(id)}>
                  {nameOf(id)}
                </button>
                <span className="sub mono">{id}</span>
              </td>
              <td className="r num">{formatPercent(t.reached_probabilities[id] ?? 0, 1)}</td>
              <td className="r num">{formatPercent(t.node_probabilities[id] ?? 0, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

/** The drawer's other mode: how the network's segments connect, and what is outside the graph. */
export function TopologyDrawer({ graph, nameOf, onClose, onSelect }: Common) {
  const segmentName = new Map(graph.segments.map((s) => [s.segment_id, s.name]));
  const unknown = graph.nodes.filter((n) => n.role === "unknown");
  const undeclared = graph.segments.filter((s) => !s.declared);
  return (
    <aside className="gd" aria-labelledby="gd-title" data-canvas-ignore>
      <header className="gd-head">
        <div className="gd-kicker">
          Network
          <span className="gd-actions">
            <button className="gd-icon" type="button" onClick={onClose} title="Close (Esc)" aria-label="Close topology">
              <svg viewBox="0 0 16 16" aria-hidden="true">
                <path d="M4 4l8 8M12 4l-8 8" />
              </svg>
            </button>
          </span>
        </div>
        <h2 id="gd-title">Topology</h2>
        <div className="gd-badges">
          <span className="gd-badge">{formatCount(graph.segments.length)} segments</span>
          <span className="gd-badge">{formatCount(graph.segment_links.length)} segment links</span>
          <span className="gd-badge">{formatCount(graph.edge_count)} asset edges</span>
        </div>
      </header>
      <div className="gd-body">
        <p className="gd-lead">
          Every path is read from the snapshot&apos;s network topology; none is guessed. Assets in one segment can reach each
          other, and a link lets every asset in one segment reach every asset in the other, one way only.
        </p>
        <Section title="Segments">
          <ul className="gd-list">
            {graph.segments.map((s) => (
              <li key={s.segment_id}>
                <span>
                  <b>{s.name}</b>
                  <span className="sub mono">{s.segment_id}</span>
                </span>
                <span className={`gd-badge${s.declared ? "" : " warn"}`}>
                  {s.declared ? `${formatCount(s.asset_ids.length)} assets` : "Undeclared"}
                </span>
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Links between segments">
          {graph.segment_links.length === 0 ? (
            <p className="gd-empty">None declared. Attacks cannot be followed past the segment they land in.</p>
          ) : (
            <ul className="gd-list">
              {graph.segment_links.map((l) => (
                <li key={`${l.from_segment_id}>${l.to_segment_id}`}>
                  <span>
                    {segmentName.get(l.from_segment_id) ?? l.from_segment_id} → {segmentName.get(l.to_segment_id) ?? l.to_segment_id}
                  </span>
                  <span className="sub">one way</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
        {unknown.length > 0 || undeclared.length > 0 ? (
          <Section title="Outside the graph">
            <ul className="gd-list">
              {unknown.map((n) => (
                <li key={n.asset_id}>
                  <button type="button" className="gd-link" onClick={() => onSelect(n.asset_id)}>
                    {nameOf(n.asset_id)}
                  </button>
                  <span className="sub">no segment reported</span>
                </li>
              ))}
              {undeclared.map((s) => (
                <li key={s.segment_id}>
                  <span>{s.name}</span>
                  <span className="sub">missing from the topology, so no links in or out</span>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}
      </div>
    </aside>
  );
}
