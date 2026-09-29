import Link from "next/link";
import { Card } from "@/components/Card";
import { ExposureTrendChart } from "@/components/charts/ExposureTrendChart";
import { LossExceedanceChart } from "@/components/charts/LossExceedanceChart";
import { Kpi, KpiStrip, RupeeKpi } from "@/components/Kpi";
import { ProvenanceStrip } from "@/components/ProvenanceStrip";
import { SnapshotConsistency } from "@/components/SnapshotConsistency";
import { Unavailable } from "@/components/Unavailable";
import { WhatIf } from "@/components/WhatIf";
import {
  fetchAssets,
  fetchControlGaps,
  fetchExposure,
  fetchExposureHistory,
  fetchLossExceedance,
  fetchSnapshotProvenance,
  type ApiResult,
} from "@/lib/api";
import { formatCount, formatInr, formatPercent } from "@/lib/format";
import { assetCriticality, assetName, contributionLabel } from "@/lib/labels";
import type { AssetsResponse, AssetView, RiskFigure } from "@/lib/types";

/** How many contributors the overview ranks; the full list is on /assets. */
const RANKED_CONTRIBUTORS = 6;

export default async function OverviewPage() {
  const [exposure, provenance, history, curve, assets, candidates] = await Promise.all([
    fetchExposure(),
    fetchSnapshotProvenance(),
    fetchExposureHistory(),
    fetchLossExceedance(),
    fetchAssets(),
    fetchControlGaps(),
  ]);

  if (exposure.state !== "ok") {
    return (
      <div className="grid">
        <Unavailable result={exposure} what="Expected Annual Loss" />
        <ProvenanceStrip result={provenance} />
      </div>
    );
  }

  const figure = exposure.data;
  const percentile = figure.value_at_risk_percentile;
  const reachable = provenance.state === "ok" ? provenance.data.scan_scope.reachable_scanners : null;
  const unreachable = provenance.state === "ok" ? provenance.data.scan_scope.unreachable_scanners : null;
  // Names are only ever drawn from an inventory of this exact snapshot — never a stale or
  // differently-scoped one, which SnapshotConsistency separately warns about above.
  const inventory =
    assets.state === "ok" && assets.data.snapshot_id === figure.snapshot_id
      ? assets.data.assets
      : null;
  const top = figure.top_contributors[0];
  const topShare = top && figure.expected_annual_loss_inr > 0 ? top.expected_annual_loss_inr / figure.expected_annual_loss_inr : null;

  return (
    <div className="grid">
      <SnapshotConsistency results={[exposure, provenance, curve, assets, candidates]} />

      <KpiStrip>
        <RupeeKpi
          hero
          label="Expected annual loss"
          valueInr={figure.expected_annual_loss_inr}
          note={
            <>
              Mean of {formatCount(figure.monte_carlo_iterations)} simulated years
              {top && topShare !== null && topShare >= 0.4 ? (
                <>
                  {" "}
                  · {formatPercent(topShare, 0)} from{" "}
                  <b>{contributionLabel(top, inventory).title}</b> on{" "}
                  {contributionLabel(top, inventory).where}
                </>
              ) : null}
            </>
          }
        />
        <RupeeKpi
          label={`Value at risk · ${formatPercent(percentile)}`}
          valueInr={figure.value_at_risk_inr}
          note={`Exceeded in about 1 year in ${Math.round(1 / (1 - percentile))}`}
        />
        <Kpi
          label="Open loss scenarios"
          value={formatCount(figure.top_contributors.length)}
          note={<KevNote assets={assets} />}
        />
        <Kpi
          label="Scanners reporting"
          value={
            reachable && unreachable
              ? `${reachable.length} / ${reachable.length + unreachable.length}`
              : "unavailable"
          }
          note={
            unreachable && unreachable.length > 0
              ? `Not reporting: ${unreachable.join(", ")}`
              : unreachable
                ? "Every expected scanner reported"
                : undefined
          }
        />
      </KpiStrip>

      <ProvenanceStrip result={provenance} />

      <Card
        title="Expected annual loss over time"
        subtitle="Every committed snapshot, re-simulated in full by the engine. Bands are the scenarios driving loss in the latest snapshot."
      >
        {history.state === "ok" ? (
          <ExposureTrendChart snapshots={history.data.snapshots} assets={inventory} />
        ) : (
          <Unavailable result={history} what="snapshot history" />
        )}
      </Card>

      <div className="grid g-2">
        <Card
          title="Loss exceedance curve"
          subtitle="Chance that total cyber loss in a year exceeds each amount. The mean hides the tail; this curve shows both."
        >
          {curve.state === "ok" ? (
            <LossExceedanceChart
              curve={curve.data}
              expectedAnnualLoss={figure.expected_annual_loss_inr}
              valueAtRisk={figure.value_at_risk_inr}
              valueAtRiskPercentile={percentile}
            />
          ) : (
            <Unavailable result={curve} what="loss exceedance curve" />
          )}
        </Card>
        <Card
          title="Top risk contributors"
          subtitle="Open loss scenarios as ranked by the engine."
          actions={
            <Link className="btn ghost" href="/assets">
              Drill down
            </Link>
          }
        >
          <ContributorRank figure={figure} inventory={inventory} />
        </Card>
      </div>

      <Card
        title="What-if scenarios"
        subtitle="Changes are applied together to a copy of the current snapshot and re-simulated jointly, on the same random draws as their baseline."
      >
        <WhatIf candidates={candidates} />
      </Card>

      <Card
        title="Exposure by asset"
        subtitle="The same figures, rolled up by asset instead of by scenario."
        actions={
          <Link className="btn ghost" href="/assets">
            Drill down
          </Link>
        }
      >
        <AssetBars assets={assets} />
      </Card>
    </div>
  );
}

function KevNote({ assets }: { assets: ApiResult<AssetsResponse> }) {
  if (assets.state !== "ok") return <>Known-exploited count unavailable</>;
  const open = assets.data.assets.flatMap((a) => a.findings.filter((f) => f.scenario !== null));
  const kev = open.filter((f) => f.kev_listed === true).length;
  return (
    <>
      {kev} known-exploited (CISA KEV) · one scenario per open finding
    </>
  );
}

function ContributorRank({ figure, inventory }: { figure: RiskFigure; inventory: AssetView[] | null }) {
  const contributors = figure.top_contributors;
  const total = figure.expected_annual_loss_inr;
  if (contributors.length === 0) {
    return (
      <p className="small muted">
        The engine returned a figure with no scenario breakdown. A bottom-line number with no
        explanation of what drives it cannot be acted on — this is a gap in the engine output, not
        an empty result.
      </p>
    );
  }
  const ranked = contributors.slice(0, RANKED_CONTRIBUTORS);
  const largest = ranked[0].expected_annual_loss_inr;
  return (
    <>
      <div className="rank">
        {ranked.map((c, i) => (
          <div className="it" key={c.scenario_id}>
            <span className="n">{i + 1}</span>
            <span className="nm" title={c.description}>
              {contributionLabel(c, inventory).title}
            </span>
            <span className="val">{formatInr(c.expected_annual_loss_inr)}</span>
            <span className="meta">
              <span title={c.asset_id}>{contributionLabel(c, inventory).where}</span>
              {total > 0 ? <span>· {formatPercent(c.expected_annual_loss_inr / total)} of EAL</span> : null}
            </span>
            <div className="bar">
              <i
                style={{
                  width: `${largest > 0 ? (c.expected_annual_loss_inr / largest) * 100 : 0}%`,
                  background: i < 5 ? `var(--s${i + 1})` : "var(--other)",
                }}
              />
            </div>
          </div>
        ))}
      </div>
      {total > 0 ? (
        <p className="small muted" style={{ marginTop: 8 }}>
          {ranked.length < contributors.length
            ? `These ${ranked.length} of ${contributors.length} scenarios account for ${formatPercent(
                ranked.reduce((sum, c) => sum + c.expected_annual_loss_inr, 0) / total,
              )} of expected annual loss; the rest is in the remaining scenarios, listed under Assets & findings.`
            : `All ${contributors.length} scenarios are shown.`}
        </p>
      ) : null}
    </>
  );
}

function AssetBars({ assets }: { assets: ApiResult<AssetsResponse> }) {
  if (assets.state !== "ok") return <Unavailable result={assets} what="asset roll-up" />;
  const rows = assets.data.assets
    .flatMap((a) =>
      a.expected_annual_loss_inr === null
        ? []
        : [{ asset: a, name: assetName(a), tier: assetCriticality(a), eal: a.expected_annual_loss_inr }],
    )
    .sort((a, b) => b.eal - a.eal);
  const unmodelled = assets.data.assets.length - rows.length;
  if (rows.length === 0) {
    return (
      <p className="small muted">No asset has an open finding, so the engine models no scenario on any asset.</p>
    );
  }
  const largest = rows[0].eal;
  const total = assets.data.expected_annual_loss_inr;
  return (
    <div className="hbars">
      {rows.map((row) => (
        <div className="hb" key={row.asset.asset_id}>
          <span className="small wrap hb-name" title={row.asset.asset_id}>
            <b>{row.name}</b> <span className={`crit-${row.tier}`}>{row.tier}</span>
          </span>
          <div className="tr">
            <i style={{ width: `${largest > 0 ? (row.eal / largest) * 100 : 0}%` }} />
          </div>
          <span className="num">{formatInr(row.eal)}</span>
        </div>
      ))}
      <p className="small muted" style={{ marginTop: 4 }}>
        {total > 0
          ? `Shares of total: ${rows.map((row) => `${row.name} ${formatPercent(row.eal / total)}`).join(" · ")}. `
          : ""}
        {unmodelled > 0
          ? `${unmodelled} asset${unmodelled === 1 ? " has" : "s have"} no open finding, so no scenario is modelled there — which is not the same as no risk.`
          : ""}
      </p>
    </div>
  );
}
