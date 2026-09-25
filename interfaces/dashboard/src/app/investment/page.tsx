import { Card } from "@/components/Card";
import { InfoTip } from "@/components/InfoTip";
import { InvestmentPlanner } from "@/components/InvestmentPlanner";
import { SnapshotConsistency } from "@/components/SnapshotConsistency";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssets, fetchControlGaps, fetchPriorityPlan } from "@/lib/api";
import { formatInr, formatPercent } from "@/lib/format";
import { describeChanges, type ChangeLabel } from "@/lib/labels";
import type { PriorityPlan } from "@/lib/types";

export default async function InvestmentPage() {
  const [candidates, plan, assets] = await Promise.all([
    fetchControlGaps(),
    fetchPriorityPlan(),
    fetchAssets(),
  ]);

  if (candidates.state !== "ok") {
    return <Unavailable result={candidates} what="candidate changes" />;
  }

  const gaps = candidates.data.gaps;
  if (gaps.length === 0) {
    return (
      <Card title="Nothing to act on">
        <p className="small muted">
          The current snapshot has no open finding, every modelled control (MFA and EDR) is active on
          every asset, and every service has a tested, immutable backup — so there is no change for
          the optimizer to weigh.
        </p>
      </Card>
    );
  }

  // Names come from an inventory of the same snapshot only; otherwise raw ids are shown.
  const inventory =
    assets.state === "ok" && assets.data.snapshot_id === candidates.data.snapshot_id
      ? assets.data.assets
      : null;
  const labels = describeChanges(gaps, inventory);
  const order =
    plan.state === "ok" && plan.data.snapshot_id === candidates.data.snapshot_id
      ? [
          ...plan.data.steps.map((s) => s.gap.control_id),
          ...plan.data.no_effect.map((g) => g.control_id),
        ]
      : [];

  return (
    <div className="grid">
      <SnapshotConsistency results={[candidates, plan, assets]} />
      {plan.state !== "ok" ? (
        <Card title="Where to act first">
          <Unavailable result={plan} what="priority plan" />
        </Card>
      ) : (
        <PlanCard plan={plan.data} labels={labels} />
      )}
      <InvestmentPlanner candidates={candidates.data} labels={labels} order={order} />
    </div>
  );
}

/**
 * The priority plan as a burn-down: today's expected annual loss, then what
 * is left after each change, in the order that cuts loss fastest. Every
 * figure is the engine's joint simulation of that step and all before it.
 */
function PlanCard({ plan, labels }: { plan: PriorityPlan; labels: Record<string, ChangeLabel> }) {
  const baseline = plan.baseline_risk_figure.expected_annual_loss_inr;
  const steps = plan.steps;
  const width = (value: number) => (baseline > 0 ? Math.max(0, (value / baseline) * 100) : 0);
  const first = steps[0];
  const firstShare = first && baseline > 0 ? first.marginal_reduction_inr / baseline : 0;
  const last = steps.at(-1);
  const plannedShare = last && baseline > 0 ? 1 - last.expected_annual_loss_inr / baseline : 0;

  return (
    <Card
      title="Where to act first"
      subtitle="Every change the model can weigh, ordered by how much loss each removes after the ones above it. No costs needed."
      actions={
        <InfoTip id="plan-basis" label="How the order is chosen">
          At each step the engine re-simulates the snapshot with the changes already chosen plus
          each remaining candidate, and takes the one that removes the most expected annual loss.
          Overlap is counted once: after a finding is fixed, a control that only protected it drops
          down the list. Each bar is a joint simulation, so the cuts add up exactly to the total.
        </InfoTip>
      }
    >
      <div className="planhead">
        {first === undefined ? (
          <p className="headline">No change reduces modelled loss.</p>
        ) : firstShare >= 0.5 ? (
          <p className="headline">
            {labels[first.gap.control_id]?.title ?? first.gap.control_id} on{" "}
            {labels[first.gap.control_id]?.where ?? first.gap.affected_asset_ids.join(", ")} removes{" "}
            {formatPercent(firstShare, 1)} of expected annual loss
          </p>
        ) : (
          <p className="headline">
            {steps.length === 1 ? "One change removes" : `These ${steps.length} changes remove`}{" "}
            {formatPercent(plannedShare, 1)} of expected annual loss
          </p>
        )}
      </div>

      <ol className="burn">
        <li className="start">
          <span className="rk" aria-hidden="true" />
          <span className="what">
            <b>Expected annual loss today</b>
          </span>
          <span className="bar" aria-hidden="true">
            <i className="left" style={{ width: "100%" }} />
          </span>
          <span className="fig">{formatInr(baseline)}</span>
        </li>
        {steps.map((step, i) => {
          const label = labels[step.gap.control_id];
          const before = step.expected_annual_loss_inr + step.marginal_reduction_inr;
          const share = baseline > 0 ? step.marginal_reduction_inr / baseline : 0;
          return (
            <li key={step.gap.control_id}>
              <span className="rk">{i + 1}</span>
              <span className="what">
                <b>{label?.title ?? step.gap.control_id}</b>
                <span className="where">
                  {label?.where}
                  {label?.ref ? <span className="mono"> {label.ref}</span> : null}
                </span>
              </span>
              <span className="bar" aria-hidden="true">
                <i className="left" style={{ width: `${width(step.expected_annual_loss_inr)}%` }} />
                <i
                  className="cut"
                  style={{
                    width: `${Math.max(width(before) - width(step.expected_annual_loss_inr), 0.4)}%`,
                  }}
                />
              </span>
              <span className="fig">
                <span className="minus">
                  −{formatInr(step.marginal_reduction_inr)} ({formatPercent(share, 1)})
                </span>
                <span className="after">{formatInr(step.expected_annual_loss_inr)} left</span>
              </span>
            </li>
          );
        })}
      </ol>

      {plan.truncated ? (
        <p className="small muted" style={{ marginTop: 10 }}>
          The {steps.length} changes that matter most are shown; further changes would still reduce
          loss a little.
        </p>
      ) : null}
      {plan.no_effect.length > 0 ? (
        <details className="explain noeffect">
          <summary>
            {plan.no_effect.length} change{plan.no_effect.length === 1 ? "" : "s"} with no modelled
            effect
          </summary>
          <p>
            These protect nothing the model can see once the steps above are in place — for example
            MFA on an asset with no open finding. That is a limit of what is modelled, not proof they
            are worthless.
          </p>
          <ul>
            {plan.no_effect.map((gap) => (
              <li key={gap.control_id}>
                {labels[gap.control_id]?.title ?? gap.control_id}{" "}
                <span className="muted">on {labels[gap.control_id]?.where}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </Card>
  );
}
