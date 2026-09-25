import { AttackGraphExplorer } from "@/components/attack-graph/Explorer";
import type { TargetState } from "@/components/attack-graph/NodeDrawer";
import { Card } from "@/components/Card";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssets, fetchAttackGraph, fetchAttackGraphTarget, type ApiResult } from "@/lib/api";
import { SAMPLE_ATTACK_GRAPH } from "@/lib/sample-attack-graph";
import type { AssetsResponse, AttackGraphResponse } from "@/lib/types";

/** Up to this many assets, the page offers the sample network as a richer example. */
const SAMPLE_HINT_MAX_ASSETS = 5;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * The attack graph, full-bleed. `?target=<asset_id>` opens that asset's
 * drawer; `?sample=1` shows the labelled sample network instead of the
 * current snapshot.
 */
export default async function AttackPathsPage(props: PageProps<"/attack-paths">) {
  const params = await props.searchParams;
  const requested = first(params.target);
  const sample = first(params.sample) === "1";
  const [graphResult, assetsResult]: [ApiResult<AttackGraphResponse>, ApiResult<AssetsResponse>] = sample
    ? [
        { state: "ok", data: SAMPLE_ATTACK_GRAPH.graph },
        { state: "ok", data: SAMPLE_ATTACK_GRAPH.assets },
      ]
    : await Promise.all([fetchAttackGraph(), fetchAssets()]);

  if (graphResult.state !== "ok") {
    return <Unavailable result={graphResult} what="attack graph" />;
  }
  const graph = graphResult.data;
  if (graph.nodes.length === 0) {
    return (
      <Card title="Attack graph">
        <p className="small muted">The current snapshot contains no assets.</p>
      </Card>
    );
  }

  // Names and findings come from an inventory of the same snapshot only.
  const inventory =
    assetsResult.state === "ok" && assetsResult.data.snapshot_id === graph.snapshot_id
      ? assetsResult.data.assets
      : null;
  const selected = requested ? graph.nodes.find((n) => n.asset_id === requested) ?? null : null;
  let initialTarget: TargetState | null = null;
  if (selected && selected.role !== "unknown") {
    if (sample) {
      const data = SAMPLE_ATTACK_GRAPH.targets[selected.asset_id];
      initialTarget = data ? { state: "ok", data } : null;
    } else {
      const result = await fetchAttackGraphTarget(selected.asset_id);
      initialTarget =
        result.state === "ok" && result.data.snapshot_id !== graph.snapshot_id
          ? { state: "error", reason: "A new snapshot was committed while this page loaded. Reload the page." }
          : result;
    }
  }

  return (
    <AttackGraphExplorer
      // A different snapshot (or the sample) is a different canvas: start fresh.
      key={`${sample ? "sample" : "live"}:${graph.snapshot_id}`}
      graph={graph}
      inventory={inventory}
      sample={sample}
      showSampleLink={sample || graph.nodes.length <= SAMPLE_HINT_MAX_ASSETS}
      initialSelectedId={selected?.asset_id ?? null}
      initialTarget={initialTarget}
    />
  );
}
