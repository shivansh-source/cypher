import Link from "next/link";
import { Panel } from "@/components/Panel";
import { ControlStatusPill } from "@/components/StatusPill";
import { Unavailable } from "@/components/Unavailable";
import { fetchFrameworkStatus } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import type {
  ControlStatusValue,
  FrameworkStatus,
  WeightedScoreResult,
} from "@/lib/types";

/** Framework keys matching the YAML filenames under governance/control_library/. */
const FRAMEWORKS = [
  { key: "rbi_2026_directions", label: "RBI Directions 2026" },
  { key: "sebi_cscrf_cci", label: "SEBI CSCRF / CCI" },
  { key: "cis_controls", label: "CIS Controls" },
  { key: "nist_csf", label: "NIST CSF" },
  { key: "iso_27001", label: "ISO 27001" },
] as const;

const STATUS_ORDER: ControlStatusValue[] = [
  "not_met",
  "expired_attestation",
  "unknown",
  "met",
];

export default async function CompliancePage(
  props: PageProps<"/compliance">,
) {
  const params = await props.searchParams;
  const requested = Array.isArray(params.framework)
    ? params.framework[0]
    : params.framework;
  const framework =
    FRAMEWORKS.find((entry) => entry.key === requested)?.key ??
    FRAMEWORKS[0].key;

  const status = await fetchFrameworkStatus(framework);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Compliance</h1>
        <p className="mt-1 text-sm text-muted">
          Control-by-control status derived from evidence in the current
          snapshot — never from what the optimizer recommended funding.
        </p>
      </div>

      <nav className="flex flex-wrap gap-2" aria-label="Framework">
        {FRAMEWORKS.map((entry) => (
          <Link
            key={entry.key}
            href={`/compliance?framework=${entry.key}`}
            aria-current={entry.key === framework ? "page" : undefined}
            className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
              entry.key === framework
                ? "border-accent/50 bg-accent/10 text-accent"
                : "border-line bg-surface text-muted hover:text-ink"
            }`}
          >
            {entry.label}
          </Link>
        ))}
      </nav>

      {status.state !== "ok" ? (
        <Unavailable result={status} what="framework status" />
      ) : (
        <FrameworkDetail status={status.data} />
      )}
    </div>
  );
}

function FrameworkDetail({ status }: { status: FrameworkStatus }) {
  const counts = STATUS_ORDER.map((value) => ({
    value,
    count: status.controls.filter((control) => control.status === value).length,
  }));

  const sorted = [...status.controls].sort(
    (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status),
  );

  return (
    <div className="space-y-6">
      <Panel
        title={status.framework}
        subtitle={`Version ${status.framework_version}${
          status.effective_from ? ` · effective from ${status.effective_from}` : ""
        }`}
      >
        <div className="flex flex-wrap gap-6">
          {counts.map((entry) => (
            <div key={entry.value}>
              <p className="tnum text-2xl font-semibold text-ink">
                {entry.count}
              </p>
              <div className="mt-1">
                <ControlStatusPill status={entry.value} />
              </div>
            </div>
          ))}
        </div>
        <p className="mt-5 border-t border-line pt-4 text-xs leading-relaxed text-faint">
          These counts are not a compliance verdict. A framework is not
          &ldquo;passed&rdquo; at some threshold of met controls, and this page
          deliberately does not compute one.
        </p>
      </Panel>

      {status.weighted_score ? (
        <WeightedScore score={status.weighted_score} />
      ) : null}

      <Panel
        title="Controls"
        subtitle="Worst status first. Every status carries the evidence that produced it."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs tracking-wider text-faint uppercase">
                <th className="pb-2 font-medium">Control</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Evidence</th>
                <th className="pb-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((control) => (
                <tr
                  key={control.control_id}
                  className="border-b border-line/60 align-top last:border-0"
                >
                  <td className="py-3 pr-6 font-medium whitespace-nowrap text-ink">
                    {control.control_id}
                  </td>
                  <td className="py-3 pr-6">
                    <ControlStatusPill status={control.status} />
                  </td>
                  <td className="py-3 pr-6">
                    {control.evidence_refs.length === 0 ? (
                      <span className="text-xs text-faint">
                        No evidence — which is why the status is unknown
                      </span>
                    ) : (
                      <ul className="space-y-0.5">
                        {control.evidence_refs.map((ref) => (
                          <li
                            key={ref}
                            className="font-mono text-xs text-muted"
                          >
                            {ref}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="py-3 text-xs whitespace-nowrap">
                    <span
                      className={
                        control.confidence === "low" ? "text-warn" : "text-muted"
                      }
                    >
                      {control.confidence}
                    </span>
                    <span className="block text-faint">
                      {control.verified_by_human
                        ? "human-verified"
                        : "not human-verified"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function WeightedScore({ score }: { score: WeightedScoreResult }) {
  return (
    <Panel
      title="Weighted score"
      subtitle="A composite score, reported with the limits of what it can speak to."
    >
      {score.score === null ? (
        <p className="text-sm text-muted">
          No control in this framework carries a weight, so there is nothing to
          score.
        </p>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-10">
            <div>
              <p className="text-xs tracking-wider text-faint uppercase">
                Score
              </p>
              <p className="tnum mt-1 text-3xl font-semibold text-ink">
                {formatPercent(score.score, 1)}
              </p>
            </div>
            <div>
              <p className="text-xs tracking-wider text-faint uppercase">
                Coverage
              </p>
              <p className="tnum mt-1 text-3xl font-semibold text-ink">
                {score.coverage_fraction === null
                  ? "n/a"
                  : formatPercent(score.coverage_fraction, 1)}
              </p>
            </div>
            <div>
              <p className="text-xs tracking-wider text-faint uppercase">
                Low-confidence share
              </p>
              <p className="tnum mt-1 text-3xl font-semibold text-warn">
                {score.low_confidence_fraction_of_determined === null
                  ? "n/a"
                  : formatPercent(
                      score.low_confidence_fraction_of_determined,
                      1,
                    )}
              </p>
            </div>
          </div>

          <p className="border-t border-line pt-4 text-xs leading-relaxed text-faint">
            The score covers{" "}
            {score.coverage_fraction === null
              ? "an undetermined share"
              : formatPercent(score.coverage_fraction, 1)}{" "}
            of total framework weight — the rest is controls whose status is
            unknown or resting on an expired attestation, which this score
            cannot speak to either way.
            {score.low_confidence_fraction_of_determined !== null &&
            score.low_confidence_fraction_of_determined > 0 ? (
              <>
                {" "}
                Of the part it can speak to,{" "}
                {formatPercent(
                  score.low_confidence_fraction_of_determined,
                  1,
                )}{" "}
                rests on low-confidence regulatory mappings.
              </>
            ) : null}
            {score.controls_excluded_no_weight.length > 0 ? (
              <>
                {" "}
                {score.controls_excluded_no_weight.length} control
                {score.controls_excluded_no_weight.length === 1
                  ? " carries"
                  : "s carry"}{" "}
                no weight and{" "}
                {score.controls_excluded_no_weight.length === 1 ? "is" : "are"}{" "}
                excluded entirely.
              </>
            ) : null}
          </p>
        </div>
      )}
    </Panel>
  );
}
