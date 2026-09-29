import type { AttackGraphEdge, AttackGraphNode, AttackGraphResponse, AttackGraphSegment } from "./types";

/**
 * A hand-authored, client-side-only extension of the real attack graph.
 *
 * The sandbox's AWS estate has exactly one subnet today, so the real graph is flat: every
 * reachable asset is one hop from an entry point, with nothing deeper to show. This appends
 * a two-hop continuation of the same story — an analytics tier, then a settlement vault —
 * to illustrate what a properly segmented estate's attack path looks like further in.
 *
 * Every id here is invented, never observed by a connector. It is added only to the object
 * this module builds for `layoutAttackGraph`'s benefit; it is never sent to the API, never
 * written to a snapshot, and never read by `core/`. Each added node and segment carries
 * `illustrative: true` so the UI can mark it distinctly (see `Explorer.tsx`'s `NodeMark` and
 * `NodeDrawer.tsx`) and so a viewer can toggle it off to see exactly what `/attack-graph`
 * returned.
 */

const ANALYTICS_SEGMENT_ID = "illustrative-analytics";
const VAULT_SEGMENT_ID = "illustrative-vault";
const ANALYTICS_ASSET_ID = "illustrative:fraud-analytics-service";
const VAULT_ASSET_ID = "illustrative:partner-settlement-vault";

export const ILLUSTRATIVE_NAMES: Record<string, string> = {
  [ANALYTICS_ASSET_ID]: "Fraud analytics service",
  [VAULT_ASSET_ID]: "Partner settlement vault",
};

const ILLUSTRATIVE_SEGMENTS: AttackGraphSegment[] = [
  {
    segment_id: ANALYTICS_SEGMENT_ID,
    name: "Analytics tier",
    declared: true,
    asset_ids: [ANALYTICS_ASSET_ID],
    illustrative: true,
  },
  {
    segment_id: VAULT_SEGMENT_ID,
    name: "Partner settlement vault",
    declared: true,
    asset_ids: [VAULT_ASSET_ID],
    illustrative: true,
  },
];

const ILLUSTRATIVE_NODES: AttackGraphNode[] = [
  {
    asset_id: ANALYTICS_ASSET_ID,
    segment_id: ANALYTICS_SEGMENT_ID,
    internet_facing: false,
    role: "reachable",
    open_finding_count: 0,
    kev_finding_count: 0,
    routes: [],
    illustrative: true,
  },
  {
    asset_id: VAULT_ASSET_ID,
    segment_id: VAULT_SEGMENT_ID,
    internet_facing: false,
    role: "reachable",
    open_finding_count: 0,
    kev_finding_count: 0,
    routes: [],
    illustrative: true,
  },
];

const ILLUSTRATIVE_TAIL_EDGES: AttackGraphEdge[] = [
  {
    source_asset_id: ANALYTICS_ASSET_ID,
    target_asset_id: VAULT_ASSET_ID,
    reason: `illustrative:${ANALYTICS_SEGMENT_ID}->${VAULT_SEGMENT_ID}`,
  },
];

/**
 * Extends a real `/attack-graph` response with the illustrative analytics/vault tail,
 * anchored off whichever real reachable asset currently has the most open findings (a stand-
 * in "already the most concerning asset already reached" anchor, so this re-anchors itself
 * correctly if the underlying snapshot changes instead of naming one asset id by hand).
 *
 * Returns the graph unchanged if there is no real reachable asset to anchor from.
 */
export function withIllustrativeExtension(graph: AttackGraphResponse): AttackGraphResponse {
  const anchor = graph.nodes
    .filter((n) => n.role === "reachable" && n.segment_id !== null)
    .sort((a, b) => b.open_finding_count - a.open_finding_count)[0];
  if (!anchor || anchor.segment_id === null) return graph;

  const anchorEdge: AttackGraphEdge = {
    source_asset_id: anchor.asset_id,
    target_asset_id: ANALYTICS_ASSET_ID,
    reason: `illustrative:${anchor.segment_id}->${ANALYTICS_SEGMENT_ID}`,
  };
  const anchorLink = { from_segment_id: anchor.segment_id, to_segment_id: ANALYTICS_SEGMENT_ID };

  return {
    ...graph,
    segments: [...graph.segments, ...ILLUSTRATIVE_SEGMENTS],
    segment_links: [
      ...graph.segment_links,
      anchorLink,
      { from_segment_id: ANALYTICS_SEGMENT_ID, to_segment_id: VAULT_SEGMENT_ID },
    ],
    edges: [...graph.edges, anchorEdge, ...ILLUSTRATIVE_TAIL_EDGES],
    nodes: [...graph.nodes, ...ILLUSTRATIVE_NODES],
  };
}
