import Link from "next/link";
import { Card } from "@/components/Card";
import { InfoTip } from "@/components/InfoTip";
import { Lede, type LedeTone } from "@/components/Lede";
import { CONTROL_STATUS_ORDER, CONTROL_STATUS_STYLES } from "@/components/StatusPill";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssets, fetchFrameworkStatus, fetchFrameworks, type ApiResult } from "@/lib/api";
import {
  formatDate,
  formatInr,
  formatInrCompact,
  formatPercent,
  humanize,
  shortSnapshotId,
} from "@/lib/format";
import type {
  AssetFinding,
  AssetView,
  AssetsResponse,
  ControlStatus,
  ControlStatusValue,
  FrameworkStatus,
  FrameworkSummary,
  PenaltyProvision,
  Service,
  WeightedScoreResult,
} from "@/lib/types";
import { FRAMEWORK_ORDER, frameworkLabel } from "@/lib/frameworks";

function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

function countStatuses(status: FrameworkStatus): Record<ControlStatusValue, number> {
  const counts: Record<ControlStatusValue, number> = {
    met: 0,
    not_met: 0,
    unknown: 0,
    expired_attestation: 0,
  };
  for (const control of status.controls) counts[control.status] += 1;
  return counts;
}

/** What an evidence ref points at in the snapshot's asset inventory. */
type EvidenceTarget =
  | { kind: "finding"; finding: AssetFinding; asset: AssetView }
  | { kind: "asset"; asset: AssetView }
  | { kind: "service"; service: Service; asset: AssetView };

type EvidenceIndex = Map<string, EvidenceTarget>;

/**
 * Index the asset inventory by every id an evidence ref can carry
 * (finding_id, asset_id, service_id — see `governance.mapper.ControlStatus`).
 *
 * Returns null unless the inventory comes from the same snapshot the control
 * statuses were evaluated against: resolving a ref against a different
 * snapshot could describe a finding that is not the one that set the status.
 */
function indexEvidence(
  assets: ApiResult<AssetsResponse>,
  snapshotId: string,
): EvidenceIndex | null {
  if (assets.state !== "ok" || assets.data.snapshot_id !== snapshotId) return null;
  const index: EvidenceIndex = new Map();
  for (const asset of assets.data.assets) {
    index.set(asset.asset_id, { kind: "asset", asset });
    for (const finding of asset.findings) {
      index.set(finding.finding_id, { kind: "finding", finding, asset });
    }
    for (const service of asset.services) {
      if (!index.has(service.service_id)) {
        index.set(service.service_id, { kind: "service", service, asset });
      }
    }
  }
  return index;
}

function assetHref(assetId: string, findingId?: string): string {
  const base = `/assets?asset=${encodeURIComponent(assetId)}`;
  if (!findingId) return base;
  const id = encodeURIComponent(findingId);
  return `${base}&finding=${id}#finding-${id}`;
}

/** The row summary's evidence count, by kind where every ref resolved. */
function evidenceSummary(refs: string[], evidence: EvidenceIndex | null): string {
  if (refs.length === 0) return "No evidence";
  const kinds = refs.map((ref) => evidence?.get(ref)?.kind);
  const first = kinds[0];
  if (first !== undefined && kinds.every((k) => k === first)) {
    return plural(refs.length, first);
  }
  return plural(refs.length, "evidence ref");
}

export default async function CompliancePage(props: PageProps<"/compliance">) {
  const params = await props.searchParams;
  const requested = Array.isArray(params.framework) ? params.framework[0] : params.framework;
  // Started now, not after the framework list: it doesn't depend on it.
  const assetsRequest = fetchAssets();
  const frameworks = await fetchFrameworks();

  if (frameworks.state !== "ok") {
    return <Unavailable result={frameworks} what="control libraries" />;
  }

  const rank = (key: string) => {
    const index = FRAMEWORK_ORDER.indexOf(key);
    return index === -1 ? FRAMEWORK_ORDER.length : index;
  };
  const libraries = [...frameworks.data].sort(
    (a, b) => rank(a.framework) - rank(b.framework) || a.framework.localeCompare(b.framework),
  );
  if (libraries.length === 0) {
    return (
      <Card title="Frameworks">
        <p className="small muted">No control library is in force.</p>
      </Card>
    );
  }
  const [statuses, assets] = await Promise.all([
    Promise.all(libraries.map((l) => fetchFrameworkStatus(l.framework))),
    assetsRequest,
  ]);
  const selectedIndex = Math.max(
    0,
    libraries.findIndex((l) => l.framework === requested),
  );
  const selected = libraries[selectedIndex];
  const selectedStatus = statuses[selectedIndex];
  const hasControls = selectedStatus.state === "ok" && selectedStatus.data.controls.length > 0;
  const hasPenalties = selected.penalty_provisions.length > 0;
  const evidence =
    selectedStatus.state === "ok" ? indexEvidence(assets, selectedStatus.data.snapshot_id) : null;

  return (
    <div className="grid">
      <nav className="fwtabs" aria-label="Framework">
        {libraries.map((library, i) => (
          <FrameworkTab
            key={library.framework}
            library={library}
            status={statuses[i]}
            current={i === selectedIndex}
          />
        ))}
      </nav>

      {selectedStatus.state !== "ok" ? (
        <Card title={frameworkLabel(selected.framework)}>
          <Unavailable result={selectedStatus} what="framework status" />
        </Card>
      ) : (
        <Overview library={selected} status={selectedStatus.data} />
      )}

      {hasControls && selectedStatus.state === "ok" ? (
        <div className={hasPenalties ? "grid g-2" : "grid"} style={{ alignItems: "start" }}>
          <ControlList controls={selectedStatus.data.controls} evidence={evidence} />
          {hasPenalties ? <Penalties provisions={selected.penalty_provisions} /> : null}
        </div>
      ) : hasPenalties ? (
        <Penalties provisions={selected.penalty_provisions} />
      ) : null}
    </div>
  );
}

/**
 * One cell of the framework switcher, sized like a KPI strip cell: its size,
 * name, status mix and per-status counts at a glance.
 */
function FrameworkTab({
  library,
  status,
  current,
}: {
  library: FrameworkSummary;
  status: ApiResult<FrameworkStatus>;
  current: boolean;
}) {
  const counts = status.state === "ok" ? countStatuses(status.data) : null;
  const total = library.control_count;
  return (
    <Link
      className="fwtab"
      href={`/compliance?framework=${encodeURIComponent(library.framework)}`}
      aria-current={current ? "page" : undefined}
      scroll={false}
    >
      <span className="eyebrow">{total === 0 ? "No controls" : plural(total, "control")}</span>
      <span className="nm">{frameworkLabel(library.framework)}</span>
      <StatusStack counts={counts} total={total} />
      <span className="meta">
        {total === 0 ? (
          "Statutory provisions only"
        ) : counts === null ? (
          "Status unavailable"
        ) : (
          CONTROL_STATUS_ORDER.map((value) => {
            const style = CONTROL_STATUS_STYLES[value];
            return counts[value] ? (
              <span key={value} title={`${counts[value]} ${style.label.toLowerCase()}`}>
                <span aria-hidden="true" style={{ color: style.colour }}>
                  {style.icon}
                </span>{" "}
                {counts[value]}
                <span className="sr-only"> {style.label.toLowerCase()}</span>
              </span>
            ) : null;
          })
        )}
      </span>
    </Link>
  );
}

/** The status mix as one bar, worst first. Empty track when there is nothing to show. */
function StatusStack({
  counts,
  total,
}: {
  counts: Record<ControlStatusValue, number> | null;
  total: number;
}) {
  return (
    <div className="stack" aria-hidden="true">
      {counts !== null && total > 0
        ? CONTROL_STATUS_ORDER.map((value) =>
            counts[value] ? (
              <i
                key={value}
                style={{
                  width: `${(counts[value] / total) * 100}%`,
                  background: CONTROL_STATUS_STYLES[value].colour,
                }}
              />
            ) : null,
          )
        : null}
    </div>
  );
}

/**
 * The selected framework's summary: which document it is, how its controls
 * break down by status, and what the mapping rests on.
 *
 * Deliberately shows no pass mark or "% compliant" figure — a framework is
 * not passed at some share of met controls, and this page must never imply
 * one.
 */
function Overview({ library, status }: { library: FrameworkSummary; status: FrameworkStatus }) {
  const counts = countStatuses(status);
  const total = status.controls.length;
  const lowConfidence = status.controls.filter((c) => c.confidence === "low").length;
  const humanVerified = status.controls.filter((c) => c.verified_by_human).length;

  return (
    <Card
      title={frameworkLabel(library.framework)}
      subtitle={
        <span className="fwtitle" title={library.version}>
          {library.version}
        </span>
      }
      actions={
        <div className="fwmeta">
          {library.effective_from ? (
            <span className="mini">Effective {formatDate(library.effective_from)}</span>
          ) : null}
          {library.supersedes ? (
            <span className="mini" title={`Supersedes ${library.supersedes}`}>
              Supersedes {library.supersedes}
            </span>
          ) : null}
          <span className="mini" title={status.snapshot_id}>
            Snapshot {shortSnapshotId(status.snapshot_id)}
          </span>
          <InfoTip id="status-basis" label="How status is derived">
            Status is derived only from evidence in the current snapshot and from attestations —
            never because the optimizer recommended funding a control. It is not a compliance
            verdict: no pass mark is computed.
          </InfoTip>
        </div>
      }
    >
      {total === 0 ? (
        <p className="small muted">
          This library defines no controls yet, so there is nothing to evaluate — only its
          statutory provisions are recorded, below.
        </p>
      ) : (
        <>
          <StatusLede counts={counts} total={total} />
          <ControlMap controls={status.controls} counts={counts} />
          <div className="fwfacts">
            <span>
              Mapping confidence{" "}
              <b style={{ color: lowConfidence ? "var(--warn)" : undefined }}>
                {lowConfidence} of {total} low
              </b>
            </span>
            <span>
              Human-verified{" "}
              <b>
                {humanVerified} of {total}
              </b>
            </span>
            <WeightedScoreFact score={status.weighted_score} />
          </div>
        </>
      )}
    </Card>
  );
}

/**
 * The controls outside the headline's status, worst first: "The other 18:
 * 11 undetermined, 7 met." or "The other 4 are met." Empty when there are none.
 */
function describeRest(counts: Record<ControlStatusValue, number>, skip: ControlStatusValue): string {
  const rest = CONTROL_STATUS_ORDER.filter((v) => v !== skip && counts[v] > 0);
  if (rest.length === 0) return "";
  const label = (v: ControlStatusValue) => CONTROL_STATUS_STYLES[v].label.toLowerCase();
  if (rest.length === 1) {
    const n = counts[rest[0]];
    return `The other ${n} ${n === 1 ? "is" : "are"} ${label(rest[0])}.`;
  }
  const n = rest.reduce((sum, v) => sum + counts[v], 0);
  return `The other ${n}: ${rest.map((v) => `${counts[v]} ${label(v)}`).join(", ")}.`;
}

/**
 * The framework's status stated in one line, worst news first.
 *
 * Leads with failures, then expired attestations, then undetermined controls;
 * only when every control is met on evidence does it take the good tone. It
 * reports counts, never a pass mark.
 */
function StatusLede({
  counts,
  total,
}: {
  counts: Record<ControlStatusValue, number>;
  total: number;
}) {
  const lead: { status: ControlStatusValue; tone: LedeTone; title: string } =
    counts.not_met > 0
      ? {
          status: "not_met",
          tone: "crit",
          title: `${plural(counts.not_met, "control")} not met`,
        }
      : counts.expired_attestation > 0
        ? {
            status: "expired_attestation",
            tone: "warn",
            title: `${plural(counts.expired_attestation, "attestation")} expired`,
          }
        : counts.unknown > 0
          ? {
              status: "unknown",
              tone: "info",
              title: `${counts.unknown} of ${total} controls undetermined`,
            }
          : { status: "met", tone: "good", title: `All ${total} controls met` };
  const rest = describeRest(counts, lead.status);
  return (
    <Lede tone={lead.tone} icon={CONTROL_STATUS_STYLES[lead.status].icon} title={lead.title}>
      {lead.status === "unknown" ? `No evidence either way yet. ${rest}` : rest || "On current evidence."}
    </Lede>
  );
}

/**
 * One square per control, worst first, each linking to its row below — the
 * framework at a glance. The legend doubles as the per-status counts.
 */
function ControlMap({
  controls,
  counts,
}: {
  controls: ControlStatus[];
  counts: Record<ControlStatusValue, number>;
}) {
  const ordered = CONTROL_STATUS_ORDER.flatMap((v) => controls.filter((c) => c.status === v));
  return (
    <div className="cmap">
      <div className="cells">
        {ordered.map((control) => {
          const style = CONTROL_STATUS_STYLES[control.status];
          const label = `${control.parameter_name} (${control.framework_ref}): ${style.label}`;
          return (
            <a
              key={control.control_id}
              className={`cm ${control.status}`}
              href={`#control-${control.control_id}`}
              title={label}
              aria-label={label}
            >
              <span aria-hidden="true">{style.icon}</span>
            </a>
          );
        })}
      </div>
      <ul className="cmkey" aria-label="Controls by status">
        {CONTROL_STATUS_ORDER.filter((v) => counts[v] > 0).map((v) => (
          <li key={v}>
            <a href={`#status-${v}`}>
              <span className={`cm sm ${v}`} aria-hidden="true" />
              <b>{counts[v]}</b> {CONTROL_STATUS_STYLES[v].label.toLowerCase()}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

function WeightedScoreFact({ score }: { score: WeightedScoreResult }) {
  if (score.score === null) {
    return (
      <span>
        Weighted score <b className="muted">none</b>{" "}
        <span className="muted">— no control carries a weight</span>
      </span>
    );
  }
  const excluded = score.controls_excluded_no_weight.length;
  const coverage =
    score.coverage_fraction === null ? "an undetermined share" : formatPercent(score.coverage_fraction, 1);
  return (
    <>
      <span
        title={`Met weight ÷ total weight. It can speak to ${coverage} of total framework weight — the rest is controls whose status is unknown or rests on an expired attestation.${
          excluded ? ` ${plural(excluded, "control")} with no weight excluded.` : ""
        }`}
      >
        Weighted score <b>{formatPercent(score.score, 1)}</b>
      </span>
      <span>
        covering <b>{coverage}</b> of framework weight
      </span>
      {score.low_confidence_fraction_of_determined !== null ? (
        <span>
          Low-confidence share{" "}
          <b style={{ color: "var(--warn)" }}>
            {formatPercent(score.low_confidence_fraction_of_determined, 1)}
          </b>
        </span>
      ) : null}
    </>
  );
}

/** Controls grouped by status, worst first; each row expands to its evidence and mapping. */
function ControlList({
  controls,
  evidence,
}: {
  controls: ControlStatus[];
  evidence: EvidenceIndex | null;
}) {
  const groups = CONTROL_STATUS_ORDER.map((value) => ({
    value,
    controls: controls.filter((c) => c.status === value),
  })).filter((g) => g.controls.length > 0);

  return (
    <Card title="Controls" subtitle="Worst first. Open a control for its evidence and mapping.">
      <div className="cgroups">
        {groups.map((group) => {
          const style = CONTROL_STATUS_STYLES[group.value];
          return (
            <details
              key={group.value}
              id={`status-${group.value}`}
              name="cgroup-accordion"
              className="cgroup"
            >
              <summary>
                <span className="dot" style={{ background: style.colour }} aria-hidden="true" />
                {style.label}
                <span className="c">{group.controls.length}</span>
              </summary>
              <ul className="clist">
                {group.controls.map((control) => (
                  <li key={control.control_id} id={`control-${control.control_id}`}>
                    <ControlRow control={control} evidence={evidence} />
                  </li>
                ))}
              </ul>
            </details>
          );
        })}
      </div>
    </Card>
  );
}

function ControlRow({
  control,
  evidence,
}: {
  control: ControlStatus;
  evidence: EvidenceIndex | null;
}) {
  const style = CONTROL_STATUS_STYLES[control.status];
  const refCount = control.evidence_refs.length;
  return (
    <details className="crow">
      <summary>
        <span className="ic" style={{ color: style.colour }} aria-label={style.label}>
          {style.icon}
        </span>
        <span className="nm">
          <b>{control.parameter_name}</b>
          <span className="ref">{control.framework_ref}</span>
        </span>
        <span className={`ev${refCount ? "" : " none"}`}>
          {evidenceSummary(control.evidence_refs, evidence)}
        </span>
      </summary>
      <dl className="cdl">
        <div>
          <dt>Control ID</dt>
          <dd className="mono">{control.control_id}</dd>
        </div>
        <div>
          <dt>Framework reference</dt>
          <dd>{control.framework_ref}</dd>
        </div>
        <div className="wide">
          <dt>Evidence</dt>
          <dd>
            {refCount === 0 ? (
              <span className="muted">
                {control.status === "unknown"
                  ? "None — which is why the status is undetermined."
                  : "No evidence reference returned for this status."}
              </span>
            ) : (
              <ul className="evlist">
                {control.evidence_refs.map((ref) => (
                  <li key={ref}>
                    <EvidenceItem id={ref} target={evidence?.get(ref)} />
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
        <div>
          <dt>Mapping</dt>
          <dd>
            <span style={{ color: control.confidence === "low" ? "var(--warn)" : undefined }}>
              {control.confidence} confidence
            </span>
            {" · "}
            {control.verified_by_human ? "human-verified" : "not human-verified"}
          </dd>
        </div>
      </dl>
    </details>
  );
}

/**
 * One evidence ref, described from the asset inventory and linked to where it
 * is shown in full. A ref the inventory does not hold (an attestation, or an
 * inventory from another snapshot) is shown as recorded.
 */
function EvidenceItem({ id, target }: { id: string; target: EvidenceTarget | undefined }) {
  if (target === undefined) {
    return <span className="mono">{id}</span>;
  }
  if (target.kind === "finding") {
    const { finding, asset } = target;
    return (
      <>
        <Link className="evlink" href={assetHref(asset.asset_id, finding.finding_id)}>
          {finding.cve_id ?? humanize(finding.type)} on {asset.asset_id}
        </Link>
        <span className="sub mono">
          {finding.finding_id} · {finding.provenance.connector} ·{" "}
          {finding.provenance.raw_source_id}
          {finding.criticality ? ` · ${finding.criticality} criticality` : ""}
          {finding.remediated_at ? ` · remediated ${formatDate(finding.remediated_at)}` : ""}
        </span>
      </>
    );
  }
  if (target.kind === "asset") {
    return (
      <>
        <Link className="evlink" href={assetHref(target.asset.asset_id)}>
          {target.asset.asset_id}
        </Link>
        <span className="sub">Asset</span>
      </>
    );
  }
  return (
    <>
      <Link className="evlink" href={assetHref(target.asset.asset_id)}>
        {target.service.name}
      </Link>
      <span className="sub mono">
        {target.service.service_id} · service on {target.asset.asset_id}
      </span>
    </>
  );
}

/**
 * Statutory penalty ceilings — context only. Never an expected loss, and never
 * an input to any control's status.
 */
function Penalties({ provisions }: { provisions: PenaltyProvision[] }) {
  return (
    <Card
      title="Statutory penalty ceilings"
      subtitle="The most a regulator may impose. Context only — never an expected loss, and never an input to control status."
    >
      <ul className="pens">
        {provisions.map((p) => (
          <li key={p.id} className="pen">
            <div className="top">
              <span className="amt">
                {p.penalty_amount_inr === null ? (
                  "No single ceiling"
                ) : (
                  <>
                    Up to {formatInrCompact(p.penalty_amount_inr)}
                    <span className="exact">{formatInr(p.penalty_amount_inr)}</span>
                  </>
                )}
              </span>
              <span className={`pill ${p.currently_in_force ? "warn" : "info"}`}>
                {p.currently_in_force
                  ? "In force"
                  : p.in_force_from
                    ? `From ${formatDate(p.in_force_from)}`
                    : "Not in force"}
              </span>
            </div>
            <div className="prov-ref">{p.provision_ref}</div>
            <div className="sub">{p.statute}</div>
            <details className="explain">
              <summary>Details</summary>
              <p>{p.description}</p>
              <p>
                {p.penalty_formula} · confidence {p.confidence}
                {p.verified_by_human ? "" : ", not human-verified"}
              </p>
            </details>
          </li>
        ))}
      </ul>
    </Card>
  );
}
