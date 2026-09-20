import { FigureCard } from "@/components/FigureCard";
import { Panel } from "@/components/Panel";
import { Unavailable } from "@/components/Unavailable";
import { fetchRecommendation } from "@/lib/api";
import { formatInr, formatPercent } from "@/lib/format";
import type { PortfolioRecommendation } from "@/lib/types";

export default async function InvestmentPage(
  props: PageProps<"/investment">,
) {
  const params = await props.searchParams;
  const raw = Array.isArray(params.budget) ? params.budget[0] : params.budget;
  const budgetInr = raw !== undefined ? Number(raw) : undefined;
  const budgetIsValid =
    budgetInr !== undefined && Number.isFinite(budgetInr) && budgetInr > 0;

  const recommendation = budgetIsValid
    ? await fetchRecommendation(budgetInr)
    : undefined;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Investment</h1>
        <p className="mt-1 text-sm text-muted">
          Where a finite security budget buys the most risk reduction.
        </p>
      </div>

      <Panel
        title="Budget"
        subtitle="The optimizer selects a portfolio of controls that fits within this amount."
      >
        <form method="get" className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs tracking-wider text-faint uppercase">
              Available budget (INR)
            </span>
            <input
              type="number"
              name="budget"
              min={1}
              step={100000}
              defaultValue={raw ?? ""}
              placeholder="15000000"
              className="tnum w-64 rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
            />
          </label>
          <button
            type="submit"
            className="rounded-md border border-accent/50 bg-accent/10 px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/20"
          >
            Recommend portfolio
          </button>
        </form>
        {raw !== undefined && !budgetIsValid ? (
          <p className="mt-3 text-xs text-danger">
            Enter a positive rupee amount.
          </p>
        ) : null}
      </Panel>

      {recommendation === undefined ? (
        <Panel title="No portfolio requested yet">
          <p className="max-w-3xl text-sm leading-relaxed text-muted">
            Enter a budget above to get a recommendation. Each candidate
            portfolio is evaluated by re-running the Monte Carlo simulation
            against the portfolio as a whole, so the reported benefit accounts
            for controls that overlap — patching a vulnerability that an EDR
            rule would also have caught does not get counted twice.
          </p>
        </Panel>
      ) : recommendation.state !== "ok" ? (
        <Unavailable result={recommendation} what="portfolio recommendation" />
      ) : (
        <Recommendation data={recommendation.data} budgetInr={budgetInr!} />
      )}
    </div>
  );
}

function Recommendation({
  data,
  budgetInr,
}: {
  data: PortfolioRecommendation;
  budgetInr: number;
}) {
  const baselineEal = data.baseline_risk_figure.expected_annual_loss_inr;
  const postEal = data.post_investment_risk_figure.expected_annual_loss_inr;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <FigureCard
          label="Portfolio cost"
          valueInr={data.total_cost_inr}
          qualifier={`${formatPercent(
            data.total_cost_inr / budgetInr,
          )} of the ${formatInr(budgetInr)} budget`}
        />
        <FigureCard
          label="Risk reduction"
          valueInr={data.risk_reduction_inr}
          tone="ok"
          qualifier="From a joint re-simulation of the whole portfolio"
        />
        <FigureCard
          label="Residual annual loss"
          valueInr={postEal}
          qualifier={`Down from ${formatInr(baselineEal)} today`}
        />
      </div>

      <Panel
        title="Recommended controls"
        subtitle="Funded together, evaluated together."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs tracking-wider text-faint uppercase">
                <th className="pb-2 font-medium">Control</th>
                <th className="pb-2 font-medium">Category</th>
                <th className="pb-2 font-medium">Affects</th>
                <th className="pb-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.selected_controls.map((control) => (
                <tr
                  key={control.control_id}
                  className="border-b border-line/60 align-top last:border-0"
                >
                  <td className="py-3 pr-6 font-medium text-ink">
                    {control.control_id}
                  </td>
                  <td className="py-3 pr-6 font-mono text-xs text-muted">
                    {control.control_category}
                  </td>
                  <td className="py-3 pr-6 text-xs text-muted">
                    {control.affected_asset_ids.length} asset
                    {control.affected_asset_ids.length === 1 ? "" : "s"}
                  </td>
                  <td className="tnum py-3 text-right whitespace-nowrap text-ink">
                    {formatInr(control.estimated_cost_inr)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-line">
                <td colSpan={3} className="pt-3 text-xs text-faint">
                  Total portfolio cost
                </td>
                <td className="tnum pt-3 text-right font-semibold text-ink">
                  {formatInr(data.total_cost_inr)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <p className="mt-5 border-t border-line pt-4 text-xs leading-relaxed text-faint">
          The risk reduction above is the difference between two jointly
          simulated figures — Expected Annual Loss with none of these controls
          in place, and with all of them in place at once. It is deliberately
          not the sum of each control&apos;s individual benefit, which would
          overstate the total wherever two controls defend against the same
          loss event.
        </p>
      </Panel>

      <Panel title="Compliance note">
        <p className="max-w-3xl text-sm leading-relaxed text-muted">
          Funding a control here does not make any regulatory control
          &ldquo;met&rdquo;. Compliance status is derived only from evidence
          about findings and controls as they actually stand — see the{" "}
          <span className="text-ink">Compliance</span> tab, which is computed
          independently of anything on this page.
        </p>
      </Panel>
    </div>
  );
}
