import Link from "next/link";
import { Card } from "@/components/Card";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssets } from "@/lib/api";
import {
  daysBetween,
  formatDate,
  formatDecimal,
  formatInr,
  formatPercent,
  humanize,
} from "@/lib/format";
import type { AssetFinding, AssetView, PertEstimate, ScenarioParameters } from "@/lib/types";

/** Display order only — which of an asset's service tiers to name first. */
const CRITICALITY_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };

function highestCriticality(asset: AssetView): string {
  const tiers = asset.services.map((s) => s.criticality);
  if (tiers.length === 0) return "unknown";
  return tiers.reduce((a, b) => ((CRITICALITY_RANK[b] ?? 0) > (CRITICALITY_RANK[a] ?? 0) ? b : a));
}

type ChipState = "on" | "off" | "na";

function mfaChip(asset: AssetView): [ChipState, string] {
  const mfa = asset.identity_access?.mfa_enforced;
  if (mfa === true) return ["on", "MFA enforced"];
  if (mfa === false) return ["off", "MFA not enforced"];
  return ["na", "MFA posture not recorded (unknown, not assumed)"];
}

function edrChip(asset: AssetView): [ChipState, string] {
  const edr = asset.edr;
  if (!edr) return ["na", "EDR posture not recorded"];
  if (!edr.agent_installed) return ["off", "No EDR agent installed"];
  if (edr.agent_healthy === true) return ["on", "EDR agent installed and healthy"];
  if (edr.agent_healthy === false) return ["off", "EDR agent installed but unhealthy"];
  return ["na", "EDR agent installed, health unknown"];
}

function backupChip(asset: AssetView): [ChipState, string] {
  if (asset.services.length === 0) return ["na", "No related service, so no backup posture"];
  if (asset.services.some((s) => !s.backup.exists)) return ["off", "A related service has no backup"];
  if (asset.services.some((s) => s.backup.last_tested_at === null))
    return ["off", "A related service's backup has never been tested"];
  return ["on", "Every related service has a tested backup"];
}

function Chips({ asset }: { asset: AssetView }) {
  const chips: [string, [ChipState, string]][] = [
    ["MFA", mfaChip(asset)],
    ["EDR", edrChip(asset)],
    ["BKP", backupChip(asset)],
  ];
  return (
    <span className="ctl">
      {chips.map(([label, [state, title]]) => (
        <i key={label} className={state} title={title}>
          {label}
          {state === "na" ? "?" : ""}
        </i>
      ))}
    </span>
  );
}

function pert(estimate: PertEstimate, format: (value: number) => string) {
  return `${format(estimate.min)} / ${format(estimate.most_likely)} / ${format(estimate.max)}`;
}

function exploitSource(finding: AssetFinding, scenario: ScenarioParameters): string {
  const base = finding.epss_score;
  if (finding.kev_listed && (base === null || scenario.exploit_probability > base))
    return "KEV-listed floor";
  if (base === null) return "baseline for an unscored finding";
  return "EPSS score";
}

export default async function AssetsPage(props: PageProps<"/assets">) {
  const params = await props.searchParams;
  const requested = Array.isArray(params.asset) ? params.asset[0] : params.asset;
  const result = await fetchAssets();

  if (result.state !== "ok") {
    return <Unavailable result={result} what="asset inventory" />;
  }

  const { assets, observed_at: observedAt } = result.data;
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

  if (rows.length === 0) {
    return (
      <Card title="Assets">
        <p className="small muted">The current snapshot contains no assets.</p>
      </Card>
    );
  }

  return (
    <div className="grid">
      <div className="grid g-2">
        <Card
          title="Assets"
          subtitle="Select an asset to see the Open FAIR parameters behind its figure. Criticality comes from each asset's related services, as recorded — never inferred."
        >
          <div className="tbl">
            <table>
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Criticality</th>
                  <th>Controls</th>
                  <th className="r">Open</th>
                  <th className="r">Expected annual loss</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((asset) => {
                  const open = asset.findings.filter((f) => f.scenario !== null).length;
                  const criticality = highestCriticality(asset);
                  const internet = asset.network?.internet_facing;
                  return (
                    <tr key={asset.asset_id} className={asset === selected ? "sel" : undefined}>
                      <td>
                        <Link
                          className="rowlink mono"
                          href={`/assets?asset=${encodeURIComponent(asset.asset_id)}`}
                          aria-current={asset === selected ? "true" : undefined}
                          scroll={false}
                        >
                          {asset.asset_id}
                        </Link>
                        <div className="sub">
                          {asset.services.map((s) => s.name).join(", ") || "no related service"} ·{" "}
                          {internet === true
                            ? "internet-facing"
                            : internet === false
                              ? "internal"
                              : "exposure unknown"}
                        </div>
                      </td>
                      <td className={`crit-${criticality}`} style={{ fontWeight: 600 }}>
                        {criticality}
                      </td>
                      <td>
                        <Chips asset={asset} />
                      </td>
                      <td className="r mono">{open}</td>
                      <td className="r mono nowrap">
                        {asset.expected_annual_loss_inr === null ? (
                          <span className="muted" title="No open finding, so no scenario is modelled on this asset">
                            not modelled
                          </span>
                        ) : (
                          formatInr(asset.expected_annual_loss_inr)
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 10 }}>
            Chips: green is observed active, red is observed absent, grey “?” is not recorded — an
            unknown posture is never read as protected.
          </p>
        </Card>

        <section className="card">
          <AssetDetail asset={selected} observedAt={observedAt} />
        </section>
      </div>

      <Card
        title="Remediation backlog"
        subtitle="Every open finding, ordered by the expected annual loss the engine attributes to it. Each traces to the connector and raw record that produced it."
      >
        {backlog.length === 0 ? (
          <p className="small muted">No open findings in the current snapshot.</p>
        ) : (
          <div className="tbl">
            <table>
              <thead>
                <tr>
                  <th>Finding</th>
                  <th>Asset</th>
                  <th>Signals</th>
                  <th className="r">Open for</th>
                  <th>Source</th>
                  <th className="r">Expected annual loss</th>
                </tr>
              </thead>
              <tbody>
                {backlog.map(({ asset, finding, scenario }) => {
                  const days = daysBetween(finding.first_seen_at, observedAt);
                  return (
                    <tr key={scenario.scenario_id}>
                      <td>
                        <b>{finding.cve_id ?? humanize(finding.type)}</b>
                        <div className="sub mono">
                          {finding.finding_id} · {humanize(finding.type)} · criticality{" "}
                          {finding.criticality ?? "not evaluated"}
                        </div>
                      </td>
                      <td className="mono small">{asset.asset_id}</td>
                      <td>
                        <span className="ctl">
                          {finding.epss_score !== null ? (
                            <span className="mini">EPSS {formatDecimal(finding.epss_score, 2)}</span>
                          ) : (
                            <span className="mini">unscored</span>
                          )}
                          {finding.kev_listed ? <span className="mini kev">KEV</span> : null}
                        </span>
                      </td>
                      <td className="r mono nowrap">{days === null ? "unknown" : `${days} d`}</td>
                      <td className="mono small">
                        {finding.provenance.connector}
                        <div className="sub">{finding.provenance.raw_source_id}</div>
                      </td>
                      <td className="r mono nowrap">{formatInr(scenario.expected_annual_loss_inr)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="small muted" style={{ marginTop: 10 }}>
          “Open for” is measured from first detection to when this snapshot was observed (
          {formatDate(observedAt)}), not to today.
        </p>
      </Card>
    </div>
  );
}

function AssetDetail({ asset, observedAt }: { asset: AssetView; observedAt: string }) {
  const open = asset.findings.filter((f) => f.scenario !== null);
  const remediated = asset.findings.filter((f) => f.remediated_at != null);
  const criticality = highestCriticality(asset);
  return (
    <div className="detail">
      <div>
        <div className="eyebrow mono">{asset.asset_id}</div>
        <h2 style={{ marginTop: 4 }}>
          {asset.services.map((s) => s.name).join(", ") || "No related service"}
        </h2>
        <p className="small muted" style={{ marginTop: 4 }}>
          <span className={`crit-${criticality}`}>{criticality}</span> ·{" "}
          {asset.network?.internet_facing === true
            ? "internet-facing"
            : asset.network?.internet_facing === false
              ? "internal"
              : "exposure unknown"}
          {asset.network?.open_ports?.length ? ` · open ports ${asset.network.open_ports.join(", ")}` : ""}
          {asset.identity_access?.privileged_accounts_count != null
            ? ` · ${asset.identity_access.privileged_accounts_count} privileged account${asset.identity_access.privileged_accounts_count === 1 ? "" : "s"}`
            : ""}
        </p>
        {asset.unresolved_service_ids.length > 0 ? (
          <p className="notice" style={{ marginTop: 8 }}>
            Related service{asset.unresolved_service_ids.length === 1 ? "" : "s"}{" "}
            {asset.unresolved_service_ids.join(", ")} not found in the snapshot, so the engine
            leaves {asset.unresolved_service_ids.length === 1 ? "it" : "them"} out: this asset&apos;s
            criticality and backup posture come only from the services that did resolve (or fall
            back to unknown criticality and no backup if none did).
          </p>
        ) : null}
      </div>

      <div className="kv">
        <div>
          <div className="k">Asset expected annual loss</div>
          <div className="x">
            {asset.expected_annual_loss_inr === null ? "not modelled" : formatInr(asset.expected_annual_loss_inr)}
          </div>
        </div>
        <div>
          <div className="k">Open findings</div>
          <div className="x">{open.length}</div>
        </div>
        <div>
          <div className="k">Remediated findings</div>
          <div className="x">{remediated.length}</div>
        </div>
      </div>

      <div>
        <h3 style={{ marginBottom: 8 }}>Open findings and their FAIR parameters</h3>
        {open.length === 0 ? (
          <p className="small muted">
            No open finding on this asset, so the engine models no loss scenario here. Threat paths
            that do not start from a discrete finding are not modelled yet — this is not a
            statement that the asset carries no risk.
          </p>
        ) : (
          <div className="grid" style={{ gap: 10 }}>
            {open.map((finding) => {
              const scenario = finding.scenario!;
              const controls = Object.entries(scenario.active_control_resistances);
              return (
                <div className="scenario" key={finding.finding_id}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div>
                      <b>{finding.cve_id ?? humanize(finding.type)}</b>{" "}
                      {finding.kev_listed ? <span className="mini kev">KEV</span> : null}
                      <div className="sub mono">
                        {finding.finding_id} · via {finding.provenance.connector} · first seen{" "}
                        {formatDate(finding.first_seen_at)}
                        {(() => {
                          const days = daysBetween(finding.first_seen_at, observedAt);
                          return days === null ? "" : ` (${days} d before this snapshot)`;
                        })()}
                      </div>
                    </div>
                    <div className="mono" style={{ fontWeight: 600 }}>
                      {formatInr(scenario.expected_annual_loss_inr)} / yr
                    </div>
                  </div>
                  <div className="kv">
                    <div>
                      <div className="k">Threat events / yr (min / likely / max)</div>
                      <div className="x">{pert(scenario.threat_event_frequency, (v) => formatDecimal(v, 2))}</div>
                      <div className="e">{humanize(scenario.exposure_profile)}</div>
                    </div>
                    <div>
                      <div className="k">Exploit probability</div>
                      <div className="x">{formatDecimal(scenario.exploit_probability)}</div>
                      <div className="e">{exploitSource(finding, scenario)}</div>
                    </div>
                    <div>
                      <div className="k">Controls credited</div>
                      <div className="x">
                        {controls.length === 0
                          ? "none"
                          : controls.map(([name, r]) => `${humanize(name)} ${formatPercent(r)}`).join(", ")}
                      </div>
                      <div className="e">resistance, varied per simulated year</div>
                    </div>
                    <div>
                      <div className="k">Vulnerability</div>
                      <div className="x">{formatPercent(scenario.vulnerability, 1)}</div>
                      <div className="e">exploit probability net of controls</div>
                    </div>
                    <div>
                      <div className="k">Loss events / yr (min / likely / max)</div>
                      <div className="x">{pert(scenario.loss_event_frequency, (v) => formatDecimal(v))}</div>
                    </div>
                    <div>
                      <div className="k">Loss per event (min / likely / max)</div>
                      <div className="x" style={{ fontSize: 12 }}>
                        {pert(scenario.loss_magnitude, formatInr)}
                      </div>
                      <div className="e">
                        {scenario.criticality_tier}-tier impact · {humanize(scenario.backup_posture)}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {remediated.length > 0 ? (
        <div>
          <h3 style={{ marginBottom: 6 }}>Remediated</h3>
          <div className="rank">
            {remediated.map((finding) => (
              <div className="it two" key={finding.finding_id}>
                <span className="nm">{finding.cve_id ?? humanize(finding.type)}</span>
                <span className="pill good">✓ Remediated {formatDate(finding.remediated_at!)}</span>
                <span className="meta mono">
                  {finding.finding_id} · via {finding.provenance.connector}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <p className="small muted">
        Threat events per year × vulnerability = loss events per year; each event&apos;s cost is
        drawn from the loss-per-event range. The expected annual loss comes from simulating those
        distributions, not from multiplying the likely values above.
      </p>
    </div>
  );
}
