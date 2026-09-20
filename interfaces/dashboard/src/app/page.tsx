import { FigureCard } from "@/components/FigureCard";
import { Panel } from "@/components/Panel";
import { ProvenanceStrip } from "@/components/ProvenanceStrip";
import { Unavailable } from "@/components/Unavailable";
import { fetchExposure, fetchSnapshotProvenance } from "@/lib/api";
import { formatCount, formatInr, formatPercent } from "@/lib/format";

export default async function ExposurePage() {
  const [exposure, provenance] = await Promise.all([
    fetchExposure(),
    fetchSnapshotProvenance(),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Current exposure</h1>
        <p className="mt-1 text-sm text-muted">
          What a year of cyber risk is expected to cost, and what a bad year
          looks like.
        </p>
      </div>

      {exposure.state !== "ok" ? (
        <Unavailable result={exposure} what="Expected Annual Loss" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <FigureCard
              label="Expected Annual Loss"
              valueInr={exposure.data.expected_annual_loss_inr}
              qualifier={`Mean of ${formatCount(
                exposure.data.monte_carlo_iterations,
              )} Monte Carlo iterations`}
            />
            <FigureCard
              label="Value at Risk"
              valueInr={exposure.data.value_at_risk_inr}
              tone="danger"
              qualifier={`At the ${formatPercent(
                exposure.data.value_at_risk_percentile,
              )} percentile — losses exceed this in 1 year out of ${Math.round(
                1 / (1 - exposure.data.value_at_risk_percentile),
              )}`}
            />
          </div>

          <ProvenanceStrip result={provenance} />

          <Panel
            title="What drives the number"
            subtitle="Loss-event scenarios ranked by contribution to Expected Annual Loss, as ranked by the engine."
          >
            <ContributorTable
              contributors={exposure.data.top_contributors}
              totalEal={exposure.data.expected_annual_loss_inr}
            />
          </Panel>
        </>
      )}
    </div>
  );
}

function ContributorTable({
  contributors,
  totalEal,
}: {
  contributors: {
    scenario_id: string;
    asset_id: string;
    expected_annual_loss_inr: number;
    description: string;
  }[];
  totalEal: number;
}) {
  if (contributors.length === 0) {
    return (
      <p className="text-sm text-muted">
        The engine returned a figure with no scenario breakdown. A bottom-line
        number with no explanation of what drives it cannot be acted on — this
        is a gap in the engine output, not an empty result.
      </p>
    );
  }

  const accountedFor = contributors.reduce(
    (sum, contributor) => sum + contributor.expected_annual_loss_inr,
    0,
  );

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs tracking-wider text-faint uppercase">
              <th className="pb-2 font-medium">Scenario</th>
              <th className="pb-2 font-medium">Asset</th>
              <th className="pb-2 text-right font-medium">Annual loss</th>
              <th className="pb-2 pl-6 text-right font-medium">Share</th>
            </tr>
          </thead>
          <tbody>
            {contributors.map((contributor) => (
              <tr
                key={contributor.scenario_id}
                className="border-b border-line/60 align-top last:border-0"
              >
                <td className="py-3 pr-6">
                  <p className="font-medium text-ink">
                    {contributor.scenario_id}
                  </p>
                  <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted">
                    {contributor.description}
                  </p>
                </td>
                <td className="py-3 pr-6 font-mono text-xs text-muted">
                  {contributor.asset_id}
                </td>
                <td className="tnum py-3 text-right whitespace-nowrap text-ink">
                  {formatInr(contributor.expected_annual_loss_inr)}
                </td>
                <td className="tnum py-3 pl-6 text-right text-muted">
                  {totalEal > 0
                    ? formatPercent(
                        contributor.expected_annual_loss_inr / totalEal,
                      )
                    : "n/a"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalEal > 0 ? (
        <p className="text-xs leading-relaxed text-faint">
          These scenarios account for {formatPercent(accountedFor / totalEal)}{" "}
          of Expected Annual Loss. The remainder sits in the tail of scenarios
          not shown — it is part of the headline figure, not missing from it.
        </p>
      ) : null}
    </div>
  );
}
