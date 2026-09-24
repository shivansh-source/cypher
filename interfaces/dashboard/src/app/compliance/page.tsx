import Link from "next/link";
import { Card } from "@/components/Card";
import {
  CONTROL_STATUS_ORDER,
  CONTROL_STATUS_STYLES,
  ControlStatusPill,
} from "@/components/StatusPill";
import { Unavailable } from "@/components/Unavailable";
import { fetchFrameworkStatus, fetchFrameworks, type ApiResult } from "@/lib/api";
import { formatDate, formatInr, formatPercent, shortSnapshotId } from "@/lib/format";
import type {
  ControlStatusValue,
  FrameworkStatus,
  FrameworkSummary,
  WeightedScoreResult,
} from "@/lib/types";

/** Display names for the framework keys under governance/control_library/. */
const FRAMEWORK_LABELS: Record<string, string> = {
  rbi_2026_directions: "RBI Directions 2026",
  sebi_cscrf_cci: "SEBI CSCRF + CCI",
  cis_controls: "CIS Controls",
  nist_csf: "NIST CSF",
  iso_27001: "ISO/IEC 27001",
  dpdp_act_2023: "DPDP Act 2023",
};

/** The regulator-led frameworks first; any library not named here follows. */
const FRAMEWORK_ORDER = Object.keys(FRAMEWORK_LABELS);

function frameworkLabel(key: string): string {
  return FRAMEWORK_LABELS[key] ?? key;
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

export default async function CompliancePage(props: PageProps<"/compliance">) {
  const params = await props.searchParams;
  const requested = Array.isArray(params.framework) ? params.framework[0] : params.framework;
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
  const statuses = await Promise.all(libraries.map((l) => fetchFrameworkStatus(l.framework)));
  const selectedIndex = Math.max(
    0,
    libraries.findIndex((l) => l.framework === requested),
  );
  const selected = libraries[selectedIndex];
  const selectedStatus = statuses[selectedIndex];

  return (
    <div className="grid">
      <nav className="fw" aria-label="Framework">
        {libraries.map((library, i) => (
          <FrameworkCard
            key={library.framework}
            library={library}
            status={statuses[i]}
            current={i === selectedIndex}
          />
        ))}
      </nav>

      <div className="grid g-2">
        <Card
          title={`${frameworkLabel(selected.framework)} · controls`}
          subtitle="Status is derived only from evidence in the current snapshot and from attestations. A control is never marked met because the optimizer recommended funding it."
        >
          {selectedStatus.state !== "ok" ? (
            <Unavailable result={selectedStatus} what="framework status" />
          ) : (
            <ControlsTable status={selectedStatus.data} />
          )}
        </Card>

        <div className="grid" style={{ alignContent: "start" }}>
          {selectedStatus.state === "ok" ? (
            <WeightedScore score={selectedStatus.data.weighted_score} />
          ) : null}
          <Card
            title="Statutory penalty ceilings"
            subtitle="Maximum amounts the statute empowers a regulator to impose, as sourced in the control library. Context only — never an expected loss, and never an input to any control's status."
          >
            <Penalties library={selected} />
          </Card>
        </div>
      </div>
    </div>
  );
}

function FrameworkCard({
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
      className="fwc"
      href={`/compliance?framework=${encodeURIComponent(library.framework)}`}
      aria-current={current ? "page" : undefined}
      scroll={false}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
        <h3>{frameworkLabel(library.framework)}</h3>
        <span className="mono small muted">
          {total} control{total === 1 ? "" : "s"}
        </span>
      </div>
      <span className="ver" title={library.version}>
        {library.version}
        {library.effective_from ? ` · effective ${formatDate(library.effective_from)}` : ""}
      </span>
      {total === 0 ? (
        <span className="small muted">No controls modelled in this library yet.</span>
      ) : counts === null ? (
        <span className="small muted">Status unavailable</span>
      ) : (
        <>
          <div className="stack" aria-hidden="true">
            {CONTROL_STATUS_ORDER.map((value) =>
              counts[value] ? (
                <i
                  key={value}
                  style={{
                    width: `${(counts[value] / total) * 100}%`,
                    background: CONTROL_STATUS_STYLES[value].colour,
                  }}
                />
              ) : null,
            )}
          </div>
          <div className="cnt">
            {CONTROL_STATUS_ORDER.map((value) =>
              counts[value] ? (
                <span key={value}>
                  {CONTROL_STATUS_STYLES[value].icon} {counts[value]}{" "}
                  {CONTROL_STATUS_STYLES[value].label.toLowerCase()}
                </span>
              ) : null,
            )}
          </div>
        </>
      )}
    </Link>
  );
}

function ControlsTable({ status }: { status: FrameworkStatus }) {
  if (status.controls.length === 0) {
    return (
      <p className="small muted">
        This library defines no controls yet, so there is nothing to evaluate. Its statutory
        provisions are listed alongside.
      </p>
    );
  }
  const sorted = [...status.controls].sort(
    (a, b) => CONTROL_STATUS_ORDER.indexOf(a.status) - CONTROL_STATUS_ORDER.indexOf(b.status),
  );
  return (
    <>
      <div className="tbl">
        <table>
          <thead>
            <tr>
              <th>Control</th>
              <th>Status</th>
              <th>Evidence</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((control) => (
              <tr key={control.control_id}>
                <td>
                  <b>{control.parameter_name}</b>
                  <div className="sub mono">{control.control_id}</div>
                  <div className="sub">{control.framework_ref}</div>
                </td>
                <td>
                  <ControlStatusPill status={control.status} />
                </td>
                <td className="small">
                  {control.evidence_refs.length === 0 ? (
                    <span className="muted">
                      {control.status === "unknown"
                        ? "No evidence — which is why the status is undetermined"
                        : "No evidence reference returned for this status"}
                    </span>
                  ) : (
                    <ul className="valuelist">
                      {control.evidence_refs.map((ref) => (
                        <li key={ref}>{ref}</li>
                      ))}
                    </ul>
                  )}
                </td>
                <td className="small nowrap">
                  <span style={{ color: control.confidence === "low" ? "var(--warn)" : undefined }}>
                    {control.confidence}
                  </span>
                  <div className="sub">
                    {control.verified_by_human ? "human-verified mapping" : "not human-verified"}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        Evaluated against snapshot{" "}
        <span className="mono" title={status.snapshot_id}>
          {shortSnapshotId(status.snapshot_id)}
        </span>{" "}
        and framework version “{status.version}”. These statuses are not a compliance verdict: a
        framework is not “passed” at some share of met controls, and this page does not compute
        one.
      </p>
    </>
  );
}

function WeightedScore({ score }: { score: WeightedScoreResult }) {
  if (score.score === null) {
    return (
      <Card title="Weighted score">
        <p className="small muted">
          No control in this framework carries a weight, so there is no composite score to report.
        </p>
      </Card>
    );
  }
  return (
    <Card
      title="Weighted score"
      subtitle="A composite score, reported with the limits of what it can speak to."
    >
      <div className="kv">
        <div>
          <div className="k">Score (met weight ÷ total weight)</div>
          <div className="x">{formatPercent(score.score, 1)}</div>
        </div>
        <div>
          <div className="k">Coverage</div>
          <div className="x">
            {score.coverage_fraction === null ? "n/a" : formatPercent(score.coverage_fraction, 1)}
          </div>
        </div>
        <div>
          <div className="k">Low-confidence share</div>
          <div className="x" style={{ color: "var(--warn)" }}>
            {score.low_confidence_fraction_of_determined === null
              ? "n/a"
              : formatPercent(score.low_confidence_fraction_of_determined, 1)}
          </div>
        </div>
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        The score can speak to{" "}
        {score.coverage_fraction === null
          ? "an undetermined share"
          : formatPercent(score.coverage_fraction, 1)}{" "}
        of total framework weight — the rest is controls whose status is unknown or rests on an
        expired attestation, which it cannot speak to either way.
        {score.controls_excluded_no_weight.length > 0
          ? ` ${score.controls_excluded_no_weight.length} control${
              score.controls_excluded_no_weight.length === 1 ? " carries" : "s carry"
            } no weight and ${score.controls_excluded_no_weight.length === 1 ? "is" : "are"} excluded.`
          : ""}
      </p>
    </Card>
  );
}

function Penalties({ library }: { library: FrameworkSummary }) {
  if (library.penalty_provisions.length === 0) {
    return (
      <p className="small muted">
        No statutory penalty is recorded for this framework — voluntary standards carry none of
        their own.
      </p>
    );
  }
  return (
    <div className="rank">
      {library.penalty_provisions.map((p) => (
        <div className="it two" key={p.id}>
          <span className="nm">
            {p.statute} — {p.provision_ref}
          </span>
          <span className={`pill ${p.currently_in_force ? "warn" : "info"}`}>
            {p.currently_in_force
              ? "In force"
              : p.in_force_from
                ? `From ${formatDate(p.in_force_from)}`
                : "Not in force"}
          </span>
          <span className="meta">
            <b className="mono" style={{ color: "var(--ink)" }}>
              {p.penalty_amount_inr === null ? "No single ceiling" : `Up to ${formatInr(p.penalty_amount_inr)}`}
            </b>
            <span>· {p.description}</span>
            <span>
              · {p.penalty_formula} · confidence {p.confidence}
              {p.verified_by_human ? "" : ", not human-verified"}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}
