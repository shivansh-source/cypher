"use client";

import { useRef, useState } from "react";
import { recommendPortfolio, type ApiResult } from "@/lib/api";
import { controlCategoryLabel, formatInr, formatPercent } from "@/lib/format";
import type { ChangeLabel } from "@/lib/labels";
import type { Control, ControlCandidates, ControlGap, PortfolioRecommendation } from "@/lib/types";
import { Card } from "./Card";
import { InfoTip } from "./InfoTip";
import { Unavailable } from "./Unavailable";

/** Parse a rupee amount typed by a person: digits, optional commas/₹/spaces, optional decimals. */
function parseInr(raw: string): number | null {
  const cleaned = raw.replace(/[₹,\s]/g, "");
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

interface Run {
  signature: string;
  budget: number;
  result: ApiResult<PortfolioRecommendation>;
}

const REJECTION_TEXT: Record<string, string> = {
  over_budget: "Doesn't fit the budget left",
  no_reduction: "No further cut once the funded changes are in",
};

/**
 * Budget optimization over declared-cost candidate changes (`POST /optimize`).
 *
 * The candidates are `core.optimizer.find_control_gaps` on the current
 * snapshot, listed in the priority plan's order. Their costs are typed in
 * here, because nothing in the system knows what a change costs and the
 * optimizer will not invent it; they are sent with the request and never
 * stored. The recommendation, its cost total and its risk reduction are the
 * optimizer's own — every figure comes from joint re-simulation (principle 7).
 */
export function InvestmentPlanner({
  candidates,
  labels,
  order,
}: {
  candidates: ControlCandidates;
  labels: Record<string, ChangeLabel>;
  order: string[];
}) {
  const rank = (gap: ControlGap) => {
    const i = order.indexOf(gap.control_id);
    return i === -1 ? order.length : i;
  };
  const gaps = [...candidates.gaps].sort((a, b) => rank(a) - rank(b));
  const [costs, setCosts] = useState<Record<string, string>>({});
  const [excluded, setExcluded] = useState<Record<string, boolean>>({});
  const [bulk, setBulk] = useState<Record<string, string>>({});
  const [budget, setBudget] = useState("");
  const [pending, setPending] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const latestRequest = useRef(0);

  const budgetValue = parseInr(budget);
  const priced: Control[] = gaps.flatMap((gap) => {
    const cost = parseInr(costs[gap.control_id] ?? "");
    return excluded[gap.control_id] || cost === null ? [] : [{ ...gap, estimated_cost_inr: cost }];
  });
  const signature = JSON.stringify([budgetValue, priced]);
  const canRun = budgetValue !== null && priced.length > 0 && !pending;
  const categories = Array.from(new Set(gaps.map((gap) => gap.control_category)));

  async function submit() {
    if (budgetValue === null || priced.length === 0) return;
    const request = ++latestRequest.current;
    setPending(true);
    const result = await recommendPortfolio(budgetValue, priced);
    if (request !== latestRequest.current) return;
    setPending(false);
    setRun({ signature, budget: budgetValue, result });
  }

  function applyBulk(category: string) {
    const value = bulk[category] ?? "";
    if (parseInr(value) === null) return;
    setCosts((current) => {
      const next = { ...current };
      for (const gap of gaps) if (gap.control_category === category) next[gap.control_id] = value;
      return next;
    });
  }

  return (
    <Card
      title="Fund it within a budget"
      subtitle="Enter what each change would cost in its first year, then a budget. The optimizer picks the set that cuts the most loss."
      actions={
        <InfoTip id="budget-basis" label="How the budget search works">
          Costs are your estimates — the system never guesses one, and unpriced rows are left out.
          The search adds, one at a time, the change that cuts the most loss per rupee given what is
          already funded, and also checks whether one large change beats several small ones. Every
          figure is a joint re-simulation, so overlapping changes are never counted twice. It finds a
          strong plan, not a proven optimum.
        </InfoTip>
      }
    >
      {categories.length > 1 || gaps.length > 3 ? (
        <div className="bulk">
          <span className="small muted">Price every change of a kind at once:</span>
          {categories.map((category) => (
            <form
              key={category}
              className="bulkform"
              onSubmit={(event) => {
                event.preventDefault();
                applyBulk(category);
              }}
            >
              <label className="small" htmlFor={`bulk-${category}`}>
                {controlCategoryLabel(category)}
              </label>
              <input
                id={`bulk-${category}`}
                className="input cost"
                inputMode="decimal"
                placeholder="₹ each"
                value={bulk[category] ?? ""}
                aria-invalid={bulk[category] ? parseInr(bulk[category]) === null : undefined}
                onChange={(event) => setBulk({ ...bulk, [category]: event.target.value })}
              />
              <button className="btn ghost" type="submit">
                Apply
              </button>
            </form>
          ))}
        </div>
      ) : null}

      <ul className="pricelist">
        {gaps.map((gap) => {
          const label = labels[gap.control_id];
          const raw = costs[gap.control_id] ?? "";
          const invalid = raw !== "" && parseInr(raw) === null;
          const off = Boolean(excluded[gap.control_id]);
          return (
            <li key={gap.control_id} className={off ? "off" : undefined}>
              <input
                type="checkbox"
                checked={!off}
                aria-label={`Include ${label?.title ?? gap.control_id} on ${label?.where ?? ""}`}
                onChange={(event) => setExcluded({ ...excluded, [gap.control_id]: !event.target.checked })}
              />
              <span className="what">
                <b>{label?.title ?? gap.control_id}</b>
                <span className="where">
                  {label?.where}
                  {label?.ref ? <span className="mono"> {label.ref}</span> : null}
                </span>
              </span>
              <input
                className="input cost"
                inputMode="decimal"
                placeholder="Cost, ₹"
                aria-label={`First-year cost of ${label?.title ?? gap.control_id}`}
                aria-invalid={invalid || undefined}
                disabled={off}
                value={raw}
                onChange={(event) => setCosts({ ...costs, [gap.control_id]: event.target.value })}
              />
            </li>
          );
        })}
      </ul>

      <form
        className="budgetbar"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="field">
          <label htmlFor="budget">Budget, first year (₹)</label>
          <input
            id="budget"
            className="input"
            inputMode="decimal"
            placeholder="e.g. 5,00,000"
            value={budget}
            aria-invalid={budget !== "" && budgetValue === null ? true : undefined}
            onChange={(event) => setBudget(event.target.value)}
          />
        </div>
        <span className="small muted">
          {priced.length} of {gaps.length} priced
        </span>
        <button className="btn" type="submit" disabled={!canRun}>
          {pending ? "Simulating…" : "Recommend what to fund"}
        </button>
      </form>
      {budget !== "" && budgetValue === null ? (
        <p className="small" style={{ color: "var(--crit)", marginTop: 8 }}>
          Enter the budget as a rupee amount, e.g. 500000.
        </p>
      ) : null}

      {pending ? (
        <p className="small muted" style={{ marginTop: 14 }} role="status">
          Re-simulating candidate portfolios against the current snapshot…
        </p>
      ) : run === null ? null : run.result.state !== "ok" ? (
        <div style={{ marginTop: 14 }}>
          <Unavailable result={run.result} what="portfolio recommendation" />
        </div>
      ) : (
        <Recommendation
          data={run.result.data}
          budget={run.budget}
          labels={labels}
          stale={run.signature !== signature}
          pageSnapshotId={candidates.snapshot_id}
        />
      )}
    </Card>
  );
}

function Recommendation({
  data,
  budget,
  labels,
  stale,
  pageSnapshotId,
}: {
  data: PortfolioRecommendation;
  budget: number;
  labels: Record<string, ChangeLabel>;
  stale: boolean;
  pageSnapshotId: string;
}) {
  const baseline = data.baseline_risk_figure.expected_annual_loss_inr;
  const residual = data.post_investment_risk_figure.expected_annual_loss_inr;
  const cutShare = baseline > 0 ? data.risk_reduction_inr / baseline : 0;
  const n = data.selected_controls.length;
  const name = (c: Control) => labels[c.control_id]?.title ?? c.control_id;
  const where = (c: Control) => labels[c.control_id]?.where ?? c.affected_asset_ids.join(", ");

  return (
    <div className="reco">
      {stale ? (
        <p className="notice">
          The budget or costs changed since this recommendation. Run it again for the current inputs.
        </p>
      ) : null}
      {data.snapshot_id !== pageSnapshotId ? (
        <p className="notice">
          A newer snapshot was committed after this page loaded; the optimizer ran against it.
          Reload the page so the list matches.
        </p>
      ) : null}

      <div className="planhead">
        {n === 0 ? (
          <p className="headline">Nothing to fund within {formatInr(budget)}</p>
        ) : (
          <p className="headline">
            Fund {n === 1 ? "1 change" : `${n} changes`} for {formatInr(data.total_cost_inr)} to cut
            expected annual loss by {formatPercent(cutShare, 1)}
          </p>
        )}
        <p className="small muted">
          {n === 0
            ? "No priced change fits this budget and reduces loss. See why below."
            : `From ${formatInr(baseline)} to ${formatInr(residual)} a year, on the same simulated years.`}
        </p>
      </div>

      <div className="stats">
        <div>
          <div className="k">Spend</div>
          <div className="x">{formatInr(data.total_cost_inr)}</div>
          <div className="e">
            {budget > 0 ? `${formatPercent(data.total_cost_inr / budget)} of ` : "of "}
            {formatInr(budget)}
          </div>
        </div>
        <div>
          <div className="k">Loss cut a year</div>
          <div className="x" style={{ color: data.risk_reduction_inr > 0 ? "var(--good)" : undefined }}>
            {formatInr(data.risk_reduction_inr)}
          </div>
          <div className="e">joint re-simulation</div>
        </div>
        <div>
          <div className="k">Loss left a year</div>
          <div className="x">{formatInr(residual)}</div>
        </div>
        <div>
          <div className="k">
            Bad-year loss cut (VaR {formatPercent(data.post_investment_risk_figure.value_at_risk_percentile)})
          </div>
          <div className="x">{formatInr(data.value_at_risk_reduction_inr)}</div>
        </div>
      </div>

      {data.steps.length > 0 ? (
        <ol className="funded">
          {data.steps.map((step, i) => (
            <li key={step.control.control_id}>
              <span className="rk">{i + 1}</span>
              <span className="what">
                <b>{name(step.control)}</b>
                <span className="where">{where(step.control)}</span>
              </span>
              <span className="num">{formatInr(step.control.estimated_cost_inr)}</span>
              <span className="num good">−{formatInr(step.marginal_reduction_inr)}</span>
              <span className="num muted">{formatInr(step.expected_annual_loss_inr)} left</span>
            </li>
          ))}
        </ol>
      ) : null}

      {data.rejected.length > 0 ? (
        <details className="explain">
          <summary>
            {data.rejected.length} not funded, and why
          </summary>
          <ul className="rejected">
            {data.rejected.map((r) => (
              <li key={r.control.control_id}>
                <b>{name(r.control)}</b> <span className="muted">on {where(r.control)}</span>
                <span className="mini">
                  {REJECTION_TEXT[r.reason] ?? r.reason}
                </span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <p className="small muted">
        Funding a change here does not make any regulatory control “met” — compliance is derived only
        from evidence about controls and findings as they stand.
      </p>
    </div>
  );
}
