import { AttackGraphExplorer } from "@/components/attack-graph/Explorer";
import type { TargetState } from "@/components/attack-graph/NodeDrawer";
import { Card } from "@/components/Card";
import { Unavailable } from "@/components/Unavailable";
import { fetchAssets, fetchAttackGraph, fetchAttackGraphTarget } from "@/lib/api";

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/** The attack graph, full-bleed. `?target=<asset_id>` opens that asset's drawer. */
export default async function AttackPathsPage(props: PageProps<"/attack-paths">) {
  const params = await props.searchParams;
  const requested = first(params.target);
  const [graphResult, assetsResult] = await Promise.all([fetchAttackGraph(), fetchAssets()]);

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
    const result = await fetchAttackGraphTarget(selected.asset_id);
    initialTarget =
      result.state === "ok" && result.data.snapshot_id !== graph.snapshot_id
        ? { state: "error", reason: "A new snapshot was committed while this page loaded. Reload the page." }
        : result;
  }

  return (
    <AttackGraphExplorer
      // A different snapshot is a different canvas: start fresh.
      key={graph.snapshot_id}
      graph={graph}
      inventory={inventory}
      initialSelectedId={selected?.asset_id ?? null}
      initialTarget={initialTarget}
    />
  );
}
