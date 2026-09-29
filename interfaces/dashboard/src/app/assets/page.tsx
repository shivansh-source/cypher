import Link from "next/link";
import { Card } from "@/components/Card";
import { InfoTip } from "@/components/InfoTip";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssets } from "@/lib/api";
import {
  daysBetween,
  formatCount,
  formatDate,
  formatDecimal,
  formatInr,
  formatPercent,
} from "@/lib/format";
import { assetCriticality, assetName, backupLabel, controlLabel, findingTitle, phrase, scannerLabel } from "@/lib/labels";
import type { AssetFinding, AssetView, ScenarioParameters } from "@/lib/types";

function exposure(asset: AssetView): string {
  const internet = asset.network?.internet_facing;
  return internet === true ? "Internet-facing" : internet === false ? "Internal" : "Exposure unknown";
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

type Posture = { state: "on" | "off" | "na"; label: string; detail: string };

/** Observed posture, spelled out. An unrecorded posture is "?", never read as protected. */
function posture(asset: AssetView): Posture[] {
  const mfa = asset.identity_access?.mfa_enforced;
  const edr = asset.edr;
  const backup: Posture =
    asset.services.length === 0
      ? { state: "na", label: "Backup", detail: "No related service, so no backup posture" }
      : asset.services.some((s) => !s.backup.exists)
        ? { state: "off", label: "Backup", detail: "A related service has no backup" }
        : asset.services.some((s) => s.backup.last_tested_at === null)
          ? { state: "off", label: "Backup", detail: "A related service's backup has never been tested" }
          : { state: "on", label: "Backup", detail: "Every related service has a tested backup" };
  return [
    mfa === true
      ? { state: "on", label: "MFA", detail: "MFA enforced" }
      : mfa === false
        ? { state: "off", label: "MFA", detail: "MFA not enforced" }
        : { state: "na", label: "MFA", detail: "MFA posture not recorded (unknown, not assumed)" },
    !edr
      ? { state: "na", label: "EDR", detail: "EDR posture not recorded" }
      : !edr.agent_installed
        ? { state: "off", label: "EDR", detail: "No EDR agent installed" }
        : edr.agent_healthy === true
          ? { state: "on", label: "EDR", detail: "EDR agent installed and healthy" }
          : edr.agent_healthy === false
            ? { state: "off", label: "EDR", detail: "EDR agent installed but unhealthy" }
            : { state: "na", label: "EDR", detail: "EDR agent installed, health unknown" },
    backup,
  ];
}

const POSTURE_ICON = { on: "✓", off: "✕", na: "?" } as const;

function PostureChips({ asset }: { asset: AssetView }) {
  return (
    <span className="posture">
      {posture(asset).map((p) => (
        <span key={p.label} className={`pc ${p.state}`} title={p.detail}>
          <span aria-hidden="true">{POSTURE_ICON[p.state]}</span> {p.label}
          <span className="sr-only">: {p.detail}</span>
        </span>
      ))}
    </span>
  );
}

function exploitSource(finding: AssetFinding, scenario: ScenarioParameters): string {
  const base = finding.epss_score;
  if (finding.kev_listed && (base === null || scenario.exploit_probability > base))
    return "the KEV-listed floor";
  if (base === null) return "the baseline for unscored findings";
  return "its EPSS score";
}

function assetHref(assetId: string, findingId?: string): string {
  const base = `/assets?asset=${encodeURIComponent(assetId)}`;
  if (!findingId) return base;
  const id = encodeURIComponent(findingId);
  return `${base}&finding=${id}#finding-${id}`;
}

export default async function AssetsPage(props: PageProps<"/assets">) {
  const params = await props.searchParams;
  const requested = Array.isArray(params.asset) ? params.asset[0] : params.asset;
  const highlighted = Array.isArray(params.finding) ? params.finding[0] : params.finding;
  const result = await fetchAssets();

  if (result.state !== "ok") {
    return <Unavailable result={result} what="asset inventory" />;
  }

  const { assets, observed_at: observedAt } = result.data;
  if (assets.length === 0) {
    return (
      <Card title="Assets">
        <p className="small muted">The current snapshot contains no assets.</p>
      </Card>
    );
  }

  const rows = [...assets].sort(
    (a, b) => (b.expected_annual_loss_inr ?? -1) - (a.expected_annual_loss_inr ?? -1),
  );
  const selected = rows.find((a) => a.asset_id === requested) ?? rows[0];
  const backlog = assets
    .flatMap((asset) =>
      asset.findings.flatMap((finding) =>
        finding.scenario ? [{ asset, finding, scenario: finding.scenario }] : [],
      ),
    )
    .sort((a, b) => b.scenario.expected_annual_loss_inr - a.scenario.expected_annual_loss_inr);

  return (
    <div className="grid">
      <AssetList
        rows={rows}
        selected={selected}
        totalInr={result.data.expected_annual_loss_inr}
      />
      <AssetDetail
        asset={selected}
        observedAt={observedAt}
        highlighted={highlighted}
        iterations={result.data.monte_carlo_iterations}
      />
      <Backlog backlog={backlog} observedAt={observedAt} />
    </div>
  );
}

/**
 * Every asset, largest expected annual loss first, each with its share of the
 * modelled loss. Shares compare the engine's own per-asset figures; no rupee
 * amount is derived here.
 */
function AssetList({
  rows,
  selected,
  totalInr,
}: {
  rows: AssetView[];
  selected: AssetView;
  totalInr: number;
}) {
  const modelled = rows.reduce((sum, a) => sum + (a.expected_annual_loss_inr ?? 0), 0);
  const share = (a: AssetView) =>
    modelled > 0 && a.expected_annual_loss_inr !== null ? a.expected_annual_loss_inr / modelled : null;
  const top = rows[0];
  const topShare = share(top);

  return (
    <Card
      title="Assets"
      subtitle="Largest expected annual loss first. Select one to see how its figure is built."
      actions={
        <InfoTip id="assets-basis" label="How to read this list">
          Criticality comes from each asset&apos;s related services, as recorded — never inferred.
          Posture shows what was observed: ✓ active, ✕ absent, ? not recorded. An unrecorded
          posture is never read as protected.
        </InfoTip>
      }
    >
      <div className="concentration">
        {topShare === null ? (
          <p className="headline">No asset has an open finding, so no loss is modelled yet.</p>
        ) : (
          <>
            <p className="headline">
              {assetName(top)} carries {formatPercent(topShare, 1)} of the modelled loss
            </p>
            <p className="small muted">
              {formatInr(totalInr)} expected annual loss across {plural(rows.length, "asset")}
            </p>
          </>
        )}
      </div>

      <ul className="alist">
        {rows.map((asset) => {
          const tier = assetCriticality(asset);
          const open = asset.findings.filter((f) => f.scenario !== null).length;
          const s = share(asset);
          const current = asset === selected;
          return (
            <li key={asset.asset_id}>
              <Link
                className="arow"
                href={assetHref(asset.asset_id)}
                aria-current={current ? "true" : undefined}
                scroll={false}
              >
                <span className="who">
                  <b>{assetName(asset)}</b>
                  <span className="meta">
                    <span className="mono">{asset.asset_id}</span>
                    <span>{exposure(asset)}</span>
                    <span>{open === 0 ? "No open findings" : plural(open, "open finding")}</span>
                  </span>
                </span>
                <span className={`tier crit-${tier}`}>{phrase(tier)}</span>
                <PostureChips asset={asset} />
                <span className="loss">
                  {asset.expected_annual_loss_inr === null ? (
                    <span className="muted" title="No open finding, so no scenario is modelled">
                      Not modelled
                    </span>
                  ) : (
                    <>
                      <span className="amt">{formatInr(asset.expected_annual_loss_inr)}</span>
                      <span className="share">
                        <span className="track" aria-hidden="true">
                          <i style={{ width: `${Math.max((s ?? 0) * 100, 1)}%` }} />
                        </span>
                        <span className="pct">{s === null ? "" : formatPercent(s, 1)}</span>
                      </span>
                    </>
                  )}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/**
 * The selected asset and, for each open finding, the Open FAIR chain that
 * produces its figure. `highlighted` is a finding_id to mark — set when
 * another page (the compliance evidence list) links to one finding.
 */
function AssetDetail({
  asset,
  observedAt,
  highlighted,
  iterations,
}: {
  asset: AssetView;
  observedAt: string;
  highlighted?: string;
  iterations: number;
}) {
  const open = asset.findings.filter((f) => f.scenario !== null);
  const remediated = asset.findings.filter((f) => f.remediated_at != null);
  const tier = assetCriticality(asset);
  const ports = asset.network?.open_ports;
  const privileged = asset.identity_access?.privileged_accounts_count;

  return (
    <Card
      title={assetName(asset)}
      subtitle={
        <span className="assetfacts">
          <span className="mono">{asset.asset_id}</span>
          <span>{exposure(asset)}</span>
          {ports?.length ? <span>Open ports {ports.join(", ")}</span> : null}
          {privileged != null ? <span>{plural(privileged, "privileged account")}</span> : null}
        </span>
      }
      actions={
        <span className="fwmeta">
          <span className={`tier crit-${tier}`}>{phrase(tier)}</span>
          <InfoTip id="fair-basis" label="How the figure is built">
            Threat events a year × the chance an attempt succeeds gives loss events a year; each
            loss event&apos;s cost is drawn from its range. The expected annual loss is the mean of
            {` ${formatCount(iterations)} `}simulated years — not the product of the likely values
            shown.
          </InfoTip>
        </span>
      }
    >
      {asset.unresolved_service_ids.length > 0 ? (
        <p className="notice" style={{ marginBottom: 14 }}>
          Related service{asset.unresolved_service_ids.length === 1 ? "" : "s"}{" "}
          {asset.unresolved_service_ids.join(", ")} not found in the snapshot, so the engine leaves{" "}
          {asset.unresolved_service_ids.length === 1 ? "it" : "them"} out: this asset&apos;s
          criticality and backup posture come only from the services that did resolve (or fall back
          to unknown criticality and no backup if none did).
        </p>
      ) : null}

      {open.length === 0 ? (
        <p className="small muted">
          No open finding on this asset, so the engine models no loss scenario here. Threat paths
          that do not start from a discrete finding are not modelled yet — this is not a statement
          that the asset carries no risk.
        </p>
      ) : (
        <div className="scenarios">
          {open.map((finding) => (
            <FairChain
              key={finding.finding_id}
              assetId={asset.asset_id}
              finding={finding}
              scenario={finding.scenario!}
              observedAt={observedAt}
              highlighted={finding.finding_id === highlighted}
              iterations={iterations}
            />
          ))}
        </div>
      )}

      {remediated.length > 0 ? (
        <div className="fixed">
          <h3>Remediated</h3>
          <ul>
            {remediated.map((finding) => (
              <li
                key={finding.finding_id}
                id={`finding-${finding.finding_id}`}
                className={finding.finding_id === highlighted ? "hl" : undefined}
              >
                <span className="ok" aria-hidden="true">
                  ✓
                </span>
                <b>{findingTitle(finding)}</b>
                <span className="muted small">
                  fixed {formatDate(finding.remediated_at!)}, found by{" "}
                  {scannerLabel(finding.provenance.connector).name}
                </span>
                <span className="mono sub" title={finding.finding_id}>
                  {finding.provenance.raw_source_id}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}

/**
 * One finding's figure as the Open FAIR equation it comes from:
 * threat events × chance of success = loss events, × cost per event,
 * simulated into an expected annual loss. Values are the engine's scenario
 * parameters exactly as returned.
 */
function FairChain({
  assetId,
  finding,
  scenario,
  observedAt,
  highlighted,
  iterations,
}: {
  assetId: string;
  finding: AssetFinding;
  scenario: ScenarioParameters;
  observedAt: string;
  highlighted: boolean;
  iterations: number;
}) {
  const days = daysBetween(finding.first_seen_at, observedAt);
  const controls = Object.entries(scenario.active_control_resistances);
  const tef = scenario.threat_event_frequency;
  const lef = scenario.loss_event_frequency;
  const lm = scenario.loss_magnitude;

  return (
    <article className={`scenario${highlighted ? " hl" : ""}`} id={`finding-${finding.finding_id}`}>
      <header className="sc-h">
        <div>
          <h3>
            {findingTitle(finding)}
            {finding.kev_listed ? <span className="mini kev">KEV</span> : null}
          </h3>
          <p className="assetfacts">
            <span className="mono">{finding.provenance.raw_source_id}</span>
            <span>Found by {scannerLabel(finding.provenance.connector).name}</span>
            <span>
              First seen {formatDate(finding.first_seen_at)}
              {days === null ? "" : `, ${days} d before this snapshot`}
            </span>
            <span className="mono">{finding.finding_id}</span>
          </p>
        </div>
      </header>

      <div className="chain">
        <div className="step">
          <span className="lbl">Threat events a year</span>
          <span className="val">{formatDecimal(tef.most_likely, 2)}</span>
          <span className="rng">
            {formatDecimal(tef.min, 2)} – {formatDecimal(tef.max, 2)}
          </span>
          <span className="why">
            {scenario.graph_reachability_applied ? (
              <Link href={`/attack-paths?target=${encodeURIComponent(assetId)}`}>
                {scenario.attack_routes && scenario.attack_routes.length > 0
                  ? `Arriving by ${scenario.attack_routes.length} attack route${scenario.attack_routes.length === 1 ? "" : "s"}`
                  : "No attack route reaches it"}
              </Link>
            ) : (
              phrase(scenario.exposure_profile)
            )}
          </span>
        </div>
        <span className="op" aria-hidden="true">
          ×
        </span>
        <div className="step">
          <span className="lbl">Chance an attempt succeeds</span>
          <span className="val">{formatPercent(scenario.vulnerability, 1)}</span>
          <span className="rng">
            {formatPercent(scenario.exploit_probability, 1)} exploit chance, from{" "}
            {exploitSource(finding, scenario)}
          </span>
          <span className="why">
            {controls.length === 0
              ? "No controls credited"
              : `Reduced by ${controls.map(([k, r]) => `${controlLabel(k)} ${formatPercent(r)}`).join(", ")}`}
          </span>
        </div>
        <span className="op" aria-hidden="true">
          =
        </span>
        <div className="step">
          <span className="lbl">Loss events a year</span>
          <span className="val">{formatDecimal(lef.most_likely)}</span>
          <span className="rng">
            {formatDecimal(lef.min)} – {formatDecimal(lef.max)}
          </span>
        </div>
        <span className="op" aria-hidden="true">
          ×
        </span>
        <div className="step">
          <span className="lbl">Cost per loss event</span>
          <span className="val">{formatInr(lm.most_likely)}</span>
          <span className="rng">
            {formatInr(lm.min)} – {formatInr(lm.max)}
          </span>
          <span className="why">
            {phrase(scenario.criticality_tier)} tier, {backupLabel(scenario.backup_posture)}
          </span>
        </div>
        <span className="op sim" aria-hidden="true">
          <span>simulated</span>→
        </span>
        <div className="step out">
          <span className="lbl">Expected annual loss</span>
          <span className="val">{formatInr(scenario.expected_annual_loss_inr)}</span>
          <span className="rng">mean of {formatCount(iterations)} years</span>
        </div>
      </div>
    </article>
  );
}

/** Every open finding across the estate, ranked by the loss the engine attributes to it. */
function Backlog({
  backlog,
  observedAt,
}: {
  backlog: { asset: AssetView; finding: AssetFinding; scenario: ScenarioParameters }[];
  observedAt: string;
}) {
  return (
    <Card
      title="Remediation backlog"
      subtitle="Open findings across every asset, ranked by expected annual loss."
      actions={
        <InfoTip id="backlog-basis" label="How the backlog is ordered">
          Each finding is ranked by the expected annual loss the engine attributes to it, and traces
          to the scanner and raw record that produced it. &ldquo;Open for&rdquo; runs from first
          detection to when this snapshot was observed ({formatDate(observedAt)}), not to today.
        </InfoTip>
      }
    >
      {backlog.length === 0 ? (
        <p className="small muted">No open findings in the current snapshot.</p>
      ) : (
        <div className="tbl">
          <table className="backlog">
            <thead>
              <tr>
                <th scope="col" className="rk">
                  <span className="sr-only">Rank</span>
                </th>
                <th scope="col">Finding</th>
                <th scope="col">Asset</th>
                <th scope="col">Signals</th>
                <th scope="col" className="r">
                  Open for
                </th>
                <th scope="col" className="r">
                  Expected annual loss
                </th>
              </tr>
            </thead>
            <tbody>
              {backlog.map(({ asset, finding, scenario }, i) => {
                const days = daysBetween(finding.first_seen_at, observedAt);
                return (
                  <tr key={scenario.scenario_id}>
                    <td className="rk">{i + 1}</td>
                    <td>
                      <Link className="rowlink" href={assetHref(asset.asset_id, finding.finding_id)} scroll={false}>
                        {findingTitle(finding)}
                      </Link>
                      <div className="sub">
                        <span className="mono">{finding.provenance.raw_source_id}</span>, found by{" "}
                        {scannerLabel(finding.provenance.connector).name}
                      </div>
                    </td>
                    <td>
                      {assetName(asset)}
                      <div className="sub mono">{asset.asset_id}</div>
                    </td>
                    <td>
                      <span className="ctl">
                        {finding.epss_score !== null ? (
                          <span className="mini">EPSS {formatDecimal(finding.epss_score, 2)}</span>
                        ) : (
                          <span className="mini">Unscored</span>
                        )}
                        {finding.kev_listed ? <span className="mini kev">KEV</span> : null}
                        {finding.criticality ? (
                          <span className={`mini crit-${finding.criticality}`}>
                            {phrase(finding.criticality)}
                          </span>
                        ) : null}
                      </span>
                    </td>
                    <td className="r mono nowrap">{days === null ? "unknown" : `${days} d`}</td>
                    <td className="r mono nowrap amtcell">
                      {formatInr(scenario.expected_annual_loss_inr)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
