import { humanize } from "./format";
import type { AssetFinding, AssetView, ControlGap } from "./types";

/**
 * Display names for identifiers the API returns. Presentation only — nothing
 * here changes what the underlying data means, and every lookup falls back
 * to a readable form of the raw id.
 */

function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Connector ids, and the kind of telemetry each supplies. */
const SCANNER_LABELS: Record<string, { name: string; role: string }> = {
  nessus_connector: { name: "Nessus", role: "Vulnerability scanning" },
  greenbone_connector: { name: "Greenbone", role: "Vulnerability scanning" },
  prowler_connector: { name: "Prowler", role: "Cloud configuration" },
  scoutsuite_connector: { name: "ScoutSuite", role: "Cloud configuration" },
  wazuh_connector: { name: "Wazuh", role: "Endpoint detection" },
  iam_connector: { name: "IAM (PMapper)", role: "Identity and access" },
  nmap_connector: { name: "Nmap", role: "Network exposure" },
  threat_intel_connector: { name: "EPSS and CISA KEV", role: "Threat intelligence" },
  cmdb_connector: { name: "CMDB", role: "Asset inventory" },
};

export function scannerLabel(id: string): { name: string; role: string | null } {
  return (
    SCANNER_LABELS[id] ?? { name: sentenceCase(humanize(id.replace(/_connector$/, ""))), role: null }
  );
}

/** Control-resistance keys from `core/assumptions.py`, as short names. */
const CONTROL_LABELS: Record<string, string> = {
  mfa_enforced: "MFA",
  edr_active: "EDR",
};

export function controlLabel(key: string): string {
  return CONTROL_LABELS[key] ?? sentenceCase(humanize(key));
}

/** Backup postures from `core/engine/parameterization.py`, as phrases. */
const BACKUP_LABELS: Record<string, string> = {
  backup_tested_immutable: "tested, immutable backup",
  backup_tested_no_immutable: "tested backup, no immutable copy",
  backup_untested: "untested backup",
  no_backup: "no backup",
};

export function backupLabel(posture: string): string {
  return BACKUP_LABELS[posture] ?? humanize(posture);
}

/** A snake_case vocabulary value (exposure profile, backup posture, type) as a phrase. */
export function phrase(value: string): string {
  return sentenceCase(humanize(value));
}

/** An asset by the service(s) it runs, falling back to its id. */
export function assetName(asset: AssetView): string {
  return asset.services.map((s) => s.name).join(", ") || asset.asset_id;
}

/** A finding's name: its CVE when it has one, otherwise its type. */
export function findingTitle(finding: Pick<AssetFinding, "cve_id" | "type">): string {
  return finding.cve_id ?? phrase(finding.type);
}

/** What a candidate change does, in words, and where. */
export interface ChangeLabel {
  title: string;
  where: string;
  /** A supporting identifier (scanner check id, service id), shown small. */
  ref: string | null;
}

/**
 * Describe candidate changes from the asset inventory. Falls back to the raw
 * ids for anything the inventory does not hold (e.g. an inventory from a
 * different snapshot), so a change is never shown unlabelled.
 */
export function describeChanges(
  gaps: ControlGap[],
  assets: AssetView[] | null,
): Record<string, ChangeLabel> {
  const byId = new Map((assets ?? []).map((a) => [a.asset_id, a]));
  const where = (ids: string[]) =>
    ids.map((id) => (byId.has(id) ? assetName(byId.get(id)!) : id)).join(", ");
  const labels: Record<string, ChangeLabel> = {};
  for (const gap of gaps) {
    const place = where(gap.affected_asset_ids);
    if (gap.control_category === "mfa_enforced") {
      labels[gap.control_id] = { title: "Enforce MFA", where: place, ref: gap.affected_asset_ids.join(", ") };
    } else if (gap.control_category === "edr_active") {
      labels[gap.control_id] = {
        title: "Deploy a healthy EDR agent",
        where: place,
        ref: gap.affected_asset_ids.join(", "),
      };
    } else if (gap.control_category === "remediate_finding") {
      const finding = gap.affected_asset_ids
        .flatMap((id) => byId.get(id)?.findings ?? [])
        .find((f) => f.finding_id === gap.finding_id);
      labels[gap.control_id] = {
        title: finding ? `Fix ${finding.cve_id ?? humanize(finding.type)}` : `Fix ${gap.finding_id ?? "finding"}`,
        where: place,
        ref: finding ? finding.provenance.raw_source_id : (gap.finding_id ?? null),
      };
    } else if (gap.control_category === "harden_backup") {
      const service = gap.affected_asset_ids
        .flatMap((id) => byId.get(id)?.services ?? [])
        .find((s) => s.service_id === gap.service_id);
      labels[gap.control_id] = {
        title: "Test backups and keep an immutable copy",
        where: service ? service.name : (gap.service_id ?? place),
        ref: gap.service_id ?? null,
      };
    } else {
      labels[gap.control_id] = { title: phrase(gap.control_category), where: place, ref: null };
    }
  }
  return labels;
}
