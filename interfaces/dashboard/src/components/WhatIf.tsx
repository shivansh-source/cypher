"use client";

import { useRef, useState } from "react";
import { simulateScenario, type ApiResult } from "@/lib/api";
import { formatInr, formatInrChange, formatPercent } from "@/lib/format";
import type { ControlCandidates, HypotheticalComparison } from "@/lib/types";
import { Unavailable } from "./Unavailable";

const SCENARIO_TEXT: Record<string, { title: string; verb: string }> = {
  mfa_enforced: {
    title: "Enforce MFA on every asset where it is not observed",
    verb: "without MFA observed as enforced",
  },
  edr_active: {
    title: "Deploy a healthy EDR agent on every asset without one",
    verb: "without a healthy EDR agent",
  },
  remediate_finding: {
    title: "Fix every open finding",
    verb: "with open findings",
  },
  harden_backup: {
    title: "Give every service a tested, immutable backup",
    verb: "relying on a weaker backup",
  },
};

function assetList(ids: string[]): string {
  const shown = ids.slice(0, 4).join(", ");
  return ids.length > 4 ? `${shown} +${ids.length - 4} more` : shown;
}

/**
 * The what-if lab: apply control changes to a copy of the current snapshot and
 * re-simulate it through the real engine (`POST /simulate`).
 *
 * Every toggle combination is one joint simulation of all selected changes
 * together, on the same random draws as its own baseline — never a sum of
 * per-change effects (principle 7). The figures shown are the response's own;
 * the change is `core.optimizer`'s, not a subtraction done here.
 */
export function WhatIf({ candidates }: { candidates: ApiResult<ControlCandidates> }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<ApiResult<HypotheticalComparison> | null>(null);
  const latestRequest = useRef(0);

  if (candidates.state !== "ok") {
    return <Unavailable result={candidates} what="what-if candidates" />;
  }
  const gaps = candidates.data.gaps;
  const categories = candidates.data.applicable_categories.filter((category) =>
    gaps.some((gap) => gap.control_category === category),
  );
  if (categories.length === 0) {
    return (
      <p className="notice info">
        Nothing to try: every modelled control is active on every asset, no finding is open, and
        every service already has a tested, immutable backup.
      </p>
    );
  }

  async function toggle(category: string, on: boolean) {
    const next = on ? [...selected, category] : selected.filter((c) => c !== category);
    setSelected(next);
    const request = ++latestRequest.current;
    if (next.length === 0) {
      setPending(false);
      setResult(null);
      return;
    }
    setPending(true);
    const response = await simulateScenario(
      gaps
        .filter((gap) => next.includes(gap.control_category))
        .map(({ control_id, control_category, affected_asset_ids, finding_id, service_id }) => ({
          control_id,
          control_category,
          affected_asset_ids,
          finding_id,
          service_id,
        })),
    );
    // A later toggle supersedes this one; never show a stale combination's result.
    if (request !== latestRequest.current) return;
    setPending(false);
    setResult(response);
  }

  return (
    <>
      <div className="toggles">
        {categories.map((category) => {
          const assets = Array.from(
            new Set(
              gaps
                .filter((gap) => gap.control_category === category)
                .flatMap((gap) => gap.affected_asset_ids),
            ),
          );
          const text = SCENARIO_TEXT[category] ?? { title: category, verb: "affected" };
          return (
            <label key={category} className="tg">
              <input
                type="checkbox"
                checked={selected.includes(category)}
                onChange={(event) => toggle(category, event.target.checked)}
              />
              <div>
                <b>{text.title}</b>
                <span>
                  {assets.length} asset{assets.length === 1 ? "" : "s"} {text.verb}:{" "}
                  <span className="mono">{assetList(assets)}</span>
                </span>
              </div>
            </label>
          );
        })}
      </div>

      {selected.length === 0 ? (
        <p className="small muted" style={{ marginTop: 14 }}>
          Pick one or more changes. They are applied together to a copy of the current snapshot
          and re-simulated as one portfolio.
        </p>
      ) : pending ? (
        <p className="small muted" style={{ marginTop: 14 }} role="status">
          Re-simulating the current snapshot with the selected changes…
        </p>
      ) : result === null ? null : result.state !== "ok" ? (
        <div style={{ marginTop: 14 }}>
          <Unavailable result={result} what="what-if result" />
        </div>
      ) : (
        <WhatIfResult comparison={result.data} pageSnapshotId={candidates.data.snapshot_id} />
      )}
    </>
  );
}

function WhatIfResult({
  comparison,
  pageSnapshotId,
}: {
  comparison: HypotheticalComparison;
  pageSnapshotId: string;
}) {
  const baseline = comparison.baseline;
  const hypothetical = comparison.hypothetical;
  const percentile = formatPercent(hypothetical.value_at_risk_percentile);
  const tone = (change: number) =>
    change < 0 ? "var(--good)" : change > 0 ? "var(--crit)" : undefined;
  const share = (change: number, of: number) =>
    of > 0 && Math.abs(change) / of >= 0.0005
      ? ` (${change > 0 ? "+" : "−"}${formatPercent(Math.abs(change) / of, 1)})`
      : "";

  return (
    <>
      <div className="cmp">
        <div>
          <div className="k">EAL, baseline (same draws)</div>
          <div className="x">{formatInr(baseline.expected_annual_loss_inr)}</div>
        </div>
        <div>
          <div className="k">EAL, what-if</div>
          <div className="x">{formatInr(hypothetical.expected_annual_loss_inr)}</div>
        </div>
        <div>
          <div className="k">Change in EAL</div>
          <div className="x" style={{ color: tone(comparison.expected_annual_loss_change_inr) }}>
            {formatInrChange(comparison.expected_annual_loss_change_inr)}
            {share(comparison.expected_annual_loss_change_inr, baseline.expected_annual_loss_inr)}
          </div>
        </div>
        <div>
          <div className="k">VaR {percentile}, what-if</div>
          <div className="x">{formatInr(hypothetical.value_at_risk_inr)}</div>
        </div>
        <div>
          <div className="k">Change in VaR {percentile}</div>
          <div className="x" style={{ color: tone(comparison.value_at_risk_change_inr) }}>
            {formatInrChange(comparison.value_at_risk_change_inr)}
          </div>
        </div>
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        The baseline here is re-simulated on the same random draws as the what-if, so the
        difference comes from the change, not from sampling noise. It can differ slightly from the
        headline figure above, which uses the snapshot&apos;s own draws — compare the what-if with
        this baseline.
      </p>
      {comparison.snapshot_id !== pageSnapshotId ? (
        <p className="notice" style={{ marginTop: 10 }}>
          A newer snapshot was committed after this page loaded; this what-if ran against it.
          Reload the page to see figures from the same snapshot.
        </p>
      ) : null}
    </>
  );
}
