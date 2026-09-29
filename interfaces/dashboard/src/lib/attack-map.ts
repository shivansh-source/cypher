import type { AttackGraphEdge, AttackGraphNode, AttackGraphResponse } from "./types";

/**
 * Geometry for the attack graph drawing: where each node sits and which lines
 * connect them.
 *
 * Presentation only. Drawn like a layered network diagram: the internet is the
 * input layer on the left, and each further layer holds the segments that many
 * hops in (a breadth-first walk over the snapshot's own
 * `segment_reachability`), each layer centred vertically so lines fan between
 * them. Assets of one segment sit together under its caption. No
 * probability, share or figure is derived here — those arrive from the engine
 * through `/attack-graph` and are only drawn.
 */

export const NODE_R = 17;
export const INTERNET_R = 24;
export const INTERNET_X = 52;
export const FIRST_COL_X = 236;
export const COL_STEP = 212;
export const ROW_H = 80;
/** Room for a segment's caption above its nodes within a layer. */
export const GROUP_HEAD = 24;
export const GROUP_GAP = 22;
/** Room for the layer titles along the top. */
export const HEADER_H = 34;
export const BOTTOM = 16;
/** Half the horizontal room a node's label may take. */
export const LABEL_HALF_W = 90;
/**
 * Assets drawn per segment before the rest fold into a "+N more" row. The
 * canvas zooms, so this is only a guard against an estate so large that one
 * segment would be an unreadable column.
 */
export const MAX_NODES_PER_SEGMENT = 60;
/**
 * Same guard, but tighter for the "segment unknown" group specifically. Every
 * other group is a real network segment with real edges; this one is not a
 * segment at all — it is every asset no connector could place on the graph
 * (an IAM role, an S3 bucket, a security-group object itself), each with no
 * edges by construction. A handful of AWS estates can push this group into
 * the hundreds, at which point one unbroken column of disconnected circles
 * stops reading as "a graph" at all; folding it aggressively, ranked by
 * `rank()` so the highest-finding-count assets stay visible, keeps the page
 * honest (the count is never hidden, only the individual circles) without
 * drowning the real, connected part of the graph.
 */
export const MAX_UNKNOWN_SEGMENT_NODES = 8;

export interface PlacedNode {
  node: AttackGraphNode;
  cx: number;
  cy: number;
}

export interface PlacedGroup {
  key: string;
  name: string;
  /** null for the group of assets whose segment is unknown. */
  segmentId: string | null;
  declared: boolean;
  /** Client-added, not from the API — see `attack-map-illustrative.ts`. */
  illustrative: boolean;
  isolated: boolean;
  column: number;
  cx: number;
  /** Top of the caption. */
  y: number;
  h: number;
  nodes: PlacedNode[];
  hidden: number;
}

export interface PlacedLayer {
  column: number;
  cx: number;
  title: string;
}

/** One drawn line: a directed edge, or a pair of opposite edges merged into one two-way line. */
export interface DrawnEdge {
  key: string;
  a: string;
  b: string;
  twoWay: boolean;
  reasons: string[];
  /** Directed keys (`source>target`) this line stands for. */
  directed: string[];
}

export interface GraphLayout {
  width: number;
  height: number;
  internet: { cx: number; cy: number };
  layers: PlacedLayer[];
  groups: PlacedGroup[];
  nodeAt: Map<string, PlacedNode>;
  edges: DrawnEdge[];
}

export function edgeKey(edge: Pick<AttackGraphEdge, "source_asset_id" | "target_asset_id">): string {
  return `${edge.source_asset_id}>${edge.target_asset_id}`;
}

/**
 * Lay the graph out.
 *
 * @param priority Assets to keep visible when a segment is folded.
 */
export function layoutAttackGraph(
  graph: AttackGraphResponse,
  priority: ReadonlySet<string> = new Set(),
): GraphLayout {
  const nodesById = new Map(graph.nodes.map((n) => [n.asset_id, n]));

  const depth = new Map<string, number>();
  const queue: string[] = [];
  for (const segment of graph.segments) {
    if (segment.asset_ids.some((id) => nodesById.get(id)?.role === "entry")) {
      depth.set(segment.segment_id, 0);
      queue.push(segment.segment_id);
    }
  }
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const link of graph.segment_links) {
      if (link.from_segment_id === current && !depth.has(link.to_segment_id)) {
        depth.set(link.to_segment_id, (depth.get(current) ?? 0) + 1);
        queue.push(link.to_segment_id);
      }
    }
  }
  const reachedColumns = depth.size > 0 ? Math.max(...depth.values()) + 1 : 0;
  const hasIsolated = graph.segments.some((s) => !depth.has(s.segment_id));
  const unknownIds = graph.nodes.filter((n) => n.segment_id === null).map((n) => n.asset_id);

  type Entry = Omit<PlacedGroup, "cx" | "y" | "h" | "nodes" | "hidden"> & { ids: string[] };
  const columns: Entry[][] = [];
  const push = (entry: Entry) => (columns[entry.column] ??= []).push(entry);
  for (const segment of graph.segments) {
    const d = depth.get(segment.segment_id);
    push({
      key: segment.segment_id,
      name: segment.name,
      segmentId: segment.segment_id,
      declared: segment.declared,
      illustrative: segment.illustrative ?? false,
      isolated: d === undefined,
      column: d ?? reachedColumns,
      ids: segment.asset_ids,
    });
  }
  if (unknownIds.length > 0) {
    push({
      key: "__unknown",
      name: "Segment unknown",
      segmentId: null,
      declared: false,
      illustrative: false,
      isolated: false,
      column: reachedColumns + (hasIsolated ? 1 : 0),
      ids: unknownIds,
    });
  }

  const groups: PlacedGroup[] = [];
  const nodeAt = new Map<string, PlacedNode>();
  const layers: PlacedLayer[] = [];

  // First pass: size every group, so each layer can be centred on the tallest.
  const sized = columns.map((stack) =>
    (stack ?? []).map((entry) => {
      const ordered = [...entry.ids].sort(
        (a, b) => rank(nodesById.get(b), priority) - rank(nodesById.get(a), priority),
      );
      const cap = entry.segmentId === null ? MAX_UNKNOWN_SEGMENT_NODES : MAX_NODES_PER_SEGMENT;
      const shown = ordered.length > cap ? ordered.slice(0, cap - 1) : ordered;
      const rows = Math.max(shown.length + (ordered.length > shown.length ? 1 : 0), 1);
      return { entry, shown, hidden: ordered.length - shown.length, h: GROUP_HEAD + rows * ROW_H };
    }),
  );
  const layerHeights = sized.map((stack) =>
    stack.reduce((sum, g) => sum + g.h, 0) + Math.max(stack.length - 1, 0) * GROUP_GAP,
  );
  const bodyH = Math.max(...layerHeights, INTERNET_R * 2 + 40);

  sized.forEach((stack, column) => {
    const cx = FIRST_COL_X + column * COL_STEP;
    const first = stack[0]?.entry;
    layers.push({
      column,
      cx,
      title: !first
        ? ""
        : first.segmentId === null
        ? "Segment unknown"
        : first.isolated
        ? "No path from the internet"
        : column === 0
        ? "Entry points"
        : `${column} hop${column === 1 ? "" : "s"} in`,
    });
    let y = HEADER_H + (bodyH - layerHeights[column]) / 2;
    for (const { entry, shown, hidden, h } of stack) {
      const group: PlacedGroup = { ...entry, cx, y, h, nodes: [], hidden };
      shown.forEach((id, i) => {
        const node = nodesById.get(id);
        if (!node) return;
        const placed = { node, cx, cy: y + GROUP_HEAD + NODE_R + 4 + i * ROW_H };
        group.nodes.push(placed);
        nodeAt.set(id, placed);
      });
      groups.push(group);
      y += h + GROUP_GAP;
    }
  });

  return {
    width: FIRST_COL_X + Math.max(columns.length - 1, 0) * COL_STEP + LABEL_HALF_W + 12,
    height: HEADER_H + bodyH + BOTTOM,
    internet: { cx: INTERNET_X, cy: HEADER_H + bodyH / 2 },
    layers,
    groups,
    nodeAt,
    edges: mergeEdges(graph.edges.filter((e) => nodeAt.has(e.source_asset_id) && nodeAt.has(e.target_asset_id))),
  };
}

/** Merge each pair of opposite edges into one two-way line. */
function mergeEdges(edges: AttackGraphEdge[]): DrawnEdge[] {
  const byPair = new Map<string, DrawnEdge>();
  for (const edge of edges) {
    const [a, b] = [edge.source_asset_id, edge.target_asset_id];
    const pair = a < b ? `${a}|${b}` : `${b}|${a}`;
    const existing = byPair.get(pair);
    if (!existing) {
      byPair.set(pair, { key: pair, a, b, twoWay: false, reasons: [edge.reason], directed: [edgeKey(edge)] });
    } else {
      if (existing.a === b && existing.b === a) existing.twoWay = true;
      if (!existing.reasons.includes(edge.reason)) existing.reasons.push(edge.reason);
      existing.directed.push(edgeKey(edge));
    }
  }
  return [...byPair.values()];
}

/** Which assets stay visible when a segment folds: priority first, then entry points, then findings. */
function rank(node: AttackGraphNode | undefined, priority: ReadonlySet<string>): number {
  if (!node) return -1;
  return (
    (priority.has(node.asset_id) ? 1000 : 0) +
    (node.role === "entry" ? 100 : 0) +
    node.kev_finding_count * 10 +
    node.open_finding_count
  );
}

/**
 * The path for a line between two node centres, trimmed to the circles' edges.
 *
 * Nodes in one column are joined by an arc bowing right, so a line never runs
 * through the nodes stacked between them; a line back to an earlier column
 * bows down, so it separates from any line going the other way.
 */
export function edgePath(
  from: { cx: number; cy: number },
  to: { cx: number; cy: number },
  r1: number,
  r2: number,
): string {
  if (from.cx === to.cx) {
    const dir = to.cy > from.cy ? 1 : -1;
    const bow = 26 + Math.abs(to.cy - from.cy) * 0.22;
    const x1 = from.cx + r1 * 0.72;
    const y1 = from.cy + dir * r1 * 0.7;
    const x2 = to.cx + r2 * 0.72;
    const y2 = to.cy - dir * r2 * 0.7;
    return `M${x1},${y1} Q${from.cx + bow},${(from.cy + to.cy) / 2} ${x2},${y2}`;
  }
  const dx = to.cx - from.cx;
  const dy = to.cy - from.cy;
  const len = Math.hypot(dx, dy) || 1;
  const x1 = from.cx + (dx / len) * r1;
  const y1 = from.cy + (dy / len) * r1;
  const x2 = to.cx - (dx / len) * r2;
  const y2 = to.cy - (dy / len) * r2;
  if (dx > 0) return `M${x1},${y1} L${x2},${y2}`;
  return `M${x1},${y1} Q${(x1 + x2) / 2},${(y1 + y2) / 2 + 36} ${x2},${y2}`;
}
