"use client";

import { useRef, useState } from "react";
import { recommendPortfolio, type ApiResult } from "@/lib/api";
import { controlCategoryLabel, formatInr, formatPercent } from "@/lib/format";
import type { Control, ControlCandidates, PortfolioRecommendation } from "@/lib/types";
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
  submitted: Control[];
  result: ApiResult<PortfolioRecommendation>;
}

/**
 * Budget optimization over declared-cost candidate controls (`POST /optimize`).
 *
 * The candidates are the control gaps `core.optimizer.find_control_gaps` found
 * in the current snapshot. Their costs are typed in here, because nothing in
 * the system knows what a control costs and the optimizer will not invent it;
 * they are sent with the request and never stored. The recommendation, its
 * cost total and its risk reduction are the optimizer's own — the reduction
 * comes from one joint re-simulation of the whole portfolio (principle 7).
 */
export function InvestmentPlanner({ candidates }: { candidates: ControlCandidates }) {
  const gaps = candidates.gaps;
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
    return excluded[gap.control_id] || cost === null
      ? []
      : [{ ...gap, estimated_cost_inr: cost }];
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
    setRun({ signature, budget: budgetValue, submitted: priced, result });
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
    <div className="grid">
      <section className="card">
        <div className="card-h">
          <div>
            <h2>Candidate controls</h2>
            <p>
              Every control the engine can model that is not observed active on an asset in the
              current snapshot. Enter what each would cost in its first year — a declared input,
              not something the system measures — and untick any you would not fund.
            </p>
          </div>
        </div>

        {categories.length > 1 || gaps.length > 3 ? (
          <div className="ctrls" style={{ marginBottom: 12 }}>
            {categories.map((category) => (
              <form
                key={category}
                className="ctrls"
                style={{ alignItems: "center" }}
                onSubmit={(event) => {
                  event.preventDefault();
                  applyBulk(category);
                }}
              >
                <label className="small" htmlFor={`bulk-${category}`}>
                  Every “{controlCategoryLabel(category)}” at
                </label>
                <input
                  id={`bulk-${category}`}
                  className="input cost"
                  inputMode="decimal"
                  placeholder="₹"
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

        <div className="tbl">
          <table>
            <thead>
              <tr>
                <th>
                  <span className="sr-only">Include</span>
                </th>
                <th>Control</th>
                <th>Asset</th>
                <th className="r">Declared first-year cost (₹)</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((gap) => {
                const raw = costs[gap.control_id] ?? "";
                const invalid = raw !== "" && parseInr(raw) === null;
                return (
                  <tr key={gap.control_id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={!excluded[gap.control_id]}
                        aria-label={`Include ${gap.control_id}`}
                        onChange={(event) =>
                          setExcluded({ ...excluded, [gap.control_id]: !event.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <b>{controlCategoryLabel(gap.control_category)}</b>
                      <div className="sub mono">{gap.control_id}</div>
                    </td>
                    <td className="mono small">{gap.affected_asset_ids.join(", ")}</td>
                    <td className="r">
                      <input
                        className="input cost"
                        inputMode="decimal"
                        placeholder="not priced"
                        aria-label={`Declared cost for ${gap.control_id}`}
                        aria-invalid={invalid || undefined}
                        value={raw}
                        onChange={(event) =>
                          setCosts({ ...costs, [gap.control_id]: event.target.value })
                        }
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          {priced.length} of {gaps.length} candidate{gaps.length === 1 ? "" : "s"} priced and
          included. Unpriced candidates are left out — the optimizer is never given a guessed cost.
        </p>
      </section>

      <section className="card">
        <form
          className="budget"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="field">
            <label className="eyebrow" htmlFor="budget">
              Security budget, first-year cost (₹)
            </label>
            <input
              id="budget"
              className="input"
              inputMode="decimal"
              placeholder="e.g. 1,00,00,000"
              value={budget}
              aria-invalid={budget !== "" && budgetValue === null ? true : undefined}
              onChange={(event) => setBudget(event.target.value)}
            />
          </div>
          <button className="btn" type="submit" disabled={!canRun}>
            {pending ? "Simulating portfolios…" : "Recommend portfolio"}
          </button>
        </form>
        {budget !== "" && budgetValue === null ? (
          <p className="small" style={{ color: "var(--crit)", marginTop: 8 }}>
            Enter the budget as a rupee amount, e.g. 5000000.
          </p>
        ) : null}

        {pending ? (
          <p className="small muted" style={{ marginTop: 14 }} role="status">
            Re-simulating candidate portfolios against the current snapshot…
          </p>
        ) : run === null ? (
          <p className="small muted" style={{ marginTop: 14 }}>
            Each candidate portfolio is evaluated by re-running the Monte Carlo simulation on the
            portfolio as a whole, so controls that defend the same asset are not counted twice.
          </p>
        ) : run.result.state !== "ok" ? (
          <div style={{ marginTop: 14 }}>
            <Unavailable result={run.result} what="portfolio recommendation" />
          </div>
        ) : (
          <Recommendation
            data={run.result.data}
            budget={run.budget}
            submitted={run.submitted}
            stale={run.signature !== signature}
            pageSnapshotId={candidates.snapshot_id}
          />
        )}
      </section>
    </div>
  );
}

function Recommendation({
  data,
  budget,
  submitted,
  stale,
  pageSnapshotId,
}: {
  data: PortfolioRecommendation;
  budget: number;
  submitted: Control[];
  stale: boolean;
  pageSnapshotId: string;
}) {
  const selectedIds = new Set(data.selected_controls.map((c) => c.control_id));
  const notSelected = submitted.filter((c) => !selectedIds.has(c.control_id));

  return (
    <>
      {stale ? (
        <p className="notice" style={{ marginTop: 14 }}>
          The budget or candidates changed since this recommendation was produced. Run it again
          to see a recommendation for the current inputs.
        </p>
      ) : null}
      {data.snapshot_id !== pageSnapshotId ? (
        <p className="notice" style={{ marginTop: 14 }}>
          A newer snapshot was committed after this page loaded; the optimizer ran against it.
          Reload the page so the candidate list matches.
        </p>
      ) : null}
      <div className="stats">
        <div>
          <div className="k">Portfolio cost</div>
          <div className="x">{formatInr(data.total_cost_inr)}</div>
          <div className="e">
            {budget > 0 ? `${formatPercent(data.total_cost_inr / budget)} of ` : ""}the{" "}
            {formatInr(budget)} budget
          </div>
        </div>
        <div>
          <div className="k">Risk reduction (joint)</div>
          <div className="x" style={{ color: "var(--good)" }}>
            {formatInr(data.risk_reduction_inr)} / yr
          </div>
          <div className="e">from one joint re-simulation</div>
        </div>
        <div>
          <div className="k">Residual expected annual loss</div>
          <div className="x">{formatInr(data.post_investment_risk_figure.expected_annual_loss_inr)}</div>
        </div>
        <div>
          <div className="k">Baseline (same draws)</div>
          <div className="x">{formatInr(data.baseline_risk_figure.expected_annual_loss_inr)}</div>
        </div>
      </div>

      {data.selected_controls.length === 0 ? (
        <p className="notice info" style={{ marginTop: 14 }}>
          No candidate reduced expected annual loss within this budget, so nothing is
          recommended.
        </p>
      ) : (
        <div className="tbl" style={{ marginTop: 14 }}>
          <table>
            <thead>
              <tr>
                <th>Recommended control</th>
                <th>Asset</th>
                <th className="r">Declared cost</th>
              </tr>
            </thead>
            <tbody>
              {data.selected_controls.map((control) => (
                <tr key={control.control_id}>
                  <td>
                    <b>{controlCategoryLabel(control.control_category)}</b>
                    <div className="sub mono">{control.control_id}</div>
                  </td>
                  <td className="mono small">{control.affected_asset_ids.join(", ")}</td>
                  <td className="r mono">{formatInr(control.estimated_cost_inr)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={2}>Total portfolio cost</td>
                <td className="r mono">{formatInr(data.total_cost_inr)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {notSelected.length > 0 ? (
        <p className="small muted" style={{ marginTop: 10 }}>
          Not selected: <span className="mono">{notSelected.map((c) => c.control_id).join(", ")}</span>{" "}
          — each either did not fit the remaining budget or gave no further reduction once
          simulated together with the controls already chosen.
        </p>
      ) : null}

      <div className="callout">
        <span aria-hidden="true">≠</span>
        <span>
          The risk reduction is the difference between two jointly simulated figures — expected
          annual loss with none of these controls, and with all of them at once. It is
          deliberately not the sum of each control&apos;s standalone benefit, which would overstate
          the total wherever two controls defend the same asset. The search is greedy: it finds a
          defensible portfolio, not a proven optimum.
        </span>
      </div>
      <div className="callout">
        <span aria-hidden="true">i</span>
        <span>
          Funding a control here does not make any regulatory control “met”. Compliance status is
          derived only from evidence about controls and findings as they stand — see Compliance,
          which is computed independently of this page.
        </span>
      </div>
    </>
  );
}
