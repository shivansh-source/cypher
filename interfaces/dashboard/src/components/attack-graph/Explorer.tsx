"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { fetchAttackGraphTarget } from "@/lib/api";
import {
  GROUP_HEAD,
  INTERNET_R,
  NODE_R,
  edgeKey,
  edgePath,
  layoutAttackGraph,
  type GraphLayout,
  type PlacedNode,
} from "@/lib/attack-map";
import { formatCount, formatPercent } from "@/lib/format";
import { assetName } from "@/lib/labels";
import { SAMPLE_ATTACK_GRAPH } from "@/lib/sample-attack-graph";
import type { AssetView, AttackGraphNode, AttackGraphResponse } from "@/lib/types";
import { KEY_PAN_STEP, useZoomPan, type View } from "@/lib/use-zoom-pan";
import { NodeDrawer, TopologyDrawer, type DrawerTab, type TargetState } from "./NodeDrawer";

/** The drawer's width; the canvas keeps a node clear of it when centring. */
const DRAWER_W = 440;
/** Stroke width of the internet edge into an entry point carrying every route (share 1). */
const ROUTE_MAX_W = 12;
const ROUTE_MIN_W = 2.5;
/** The strongest red tint a node gets, at compromise probability 1. */
const HEAT_MAX_MIX = 72;
const NAME_CHARS = 22;
const ZOOM_STEP = 1.25;
/** Dot-grid spacing in world units. */
const GRID = 24;
const MINIMAP_W = 184;
const MINIMAP_MAX_H = 128;
const SEARCH_RESULTS = 8;

type Panel = { kind: "node"; id: string } | { kind: "topology" } | null;

function pageUrl(sample: boolean, target: string | null): string {
  const params = new URLSearchParams();
  if (sample) params.set("sample", "1");
  if (target) params.set("target", target);
  const query = params.toString();
  return `/attack-paths${query ? `?${query}` : ""}`;
}

/**
 * The attack graph as a full-bleed, zoomable canvas.
 *
 * Drag or two-finger scroll to pan, pinch or mouse wheel to zoom (see
 * `useZoomPan`); selecting an asset opens a detail drawer over
 * the canvas and highlights the bounded subgraph behind its figures. Every
 * probability and figure drawn comes from the API (or, on the sample network,
 * captured engine output); nothing is estimated here.
 */
export function AttackGraphExplorer({
  graph,
  inventory,
  sample,
  showSampleLink,
  initialSelectedId,
  initialTarget,
}: {
  graph: AttackGraphResponse;
  /** `/assets` for the same snapshot, or null when it is unavailable or from another snapshot. */
  inventory: AssetView[] | null;
  sample: boolean;
  showSampleLink: boolean;
  initialSelectedId: string | null;
  initialTarget: TargetState | null;
}) {
  const layout = useMemo(() => layoutAttackGraph(graph), [graph]);
  const nodesById = useMemo(() => new Map(graph.nodes.map((n) => [n.asset_id, n])), [graph]);
  const assetsById = useMemo(() => new Map((inventory ?? []).map((a) => [a.asset_id, a])), [inventory]);
  const nameOf = useCallback((id: string) => {
    const asset = assetsById.get(id);
    return asset ? assetName(asset) : id;
  }, [assetsById]);
  // Several assets can run the same service; on the canvas each node needs a
  // label of its own, so a shared name falls back to the asset id.
  const labelOf = useMemo(() => {
    const counts = new Map<string, number>();
    for (const n of graph.nodes) counts.set(nameOf(n.asset_id), (counts.get(nameOf(n.asset_id)) ?? 0) + 1);
    return (id: string) => ((counts.get(nameOf(id)) ?? 0) > 1 ? id : nameOf(id));
  }, [graph, nameOf]);

  const [panel, setPanel] = useState<Panel>(initialSelectedId ? { kind: "node", id: initialSelectedId } : null);
  const [tab, setTab] = useState<DrawerTab>("overview");
  const [targets, setTargets] = useState<Record<string, TargetState>>(
    initialSelectedId && initialTarget ? { [initialSelectedId]: initialTarget } : {},
  );
  const [legendOpen, setLegendOpen] = useState(true);

  const canvasRef = useRef<HTMLDivElement>(null);
  const zp = useZoomPan(canvasRef);
  const { view, size } = zp;
  const drawerW = panel ? Math.min(DRAWER_W, size.w) : 0;

  // Fit the graph once the canvas has a size (and centre a deep-linked asset).
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current || size.w === 0) return;
    fitted.current = true;
    zp.fit(layout, { animated: false, insetRight: initialSelectedId ? Math.min(DRAWER_W, size.w) : 0 });
  }, [size.w, layout, zp, initialSelectedId]);

  const selectedId = panel?.kind === "node" ? panel.id : null;
  const selected = selectedId ? nodesById.get(selectedId) ?? null : null;
  const targetState = selectedId ? targets[selectedId] ?? null : null;
  const target = targetState?.state === "ok" ? targetState.data : null;

  const loadTarget = useCallback(
    (node: AttackGraphNode) => {
      if (node.role === "unknown" || targets[node.asset_id]) return;
      if (sample) {
        const data = SAMPLE_ATTACK_GRAPH.targets[node.asset_id];
        setTargets((t) => ({
          ...t,
          [node.asset_id]: data
            ? { state: "ok", data }
            : { state: "unavailable", reason: "The sample network has no simulation for this asset." },
        }));
        return;
      }
      setTargets((t) => ({ ...t, [node.asset_id]: { state: "loading" } }));
      void fetchAttackGraphTarget(node.asset_id).then((result) => {
        const checked: TargetState =
          result.state === "ok" && result.data.snapshot_id !== graph.snapshot_id
            ? {
                state: "error",
                reason: "A new snapshot was committed after this page loaded, so this simulation describes a different snapshot. Reload the page.",
              }
            : result;
        setTargets((t) => ({ ...t, [node.asset_id]: checked }));
      });
    },
    [targets, sample, graph.snapshot_id],
  );

  const select = useCallback(
    (id: string) => {
      const node = nodesById.get(id);
      if (!node) return;
      setPanel({ kind: "node", id });
      loadTarget(node);
      window.history.replaceState(null, "", pageUrl(sample, id));
      // Keep the chosen node in view, clear of the drawer.
      const placed = layout.nodeAt.get(id);
      if (placed) {
        const inset = Math.min(DRAWER_W, size.w);
        const sx = placed.cx * view.k + view.x;
        const sy = placed.cy * view.k + view.y;
        if (sx < 60 || sx > size.w - inset - 60 || sy < 60 || sy > size.h - 60) {
          zp.centerOn(placed.cx, placed.cy, inset);
        }
      }
    },
    [nodesById, loadTarget, sample, layout, size, view, zp],
  );

  const close = useCallback(() => {
    setPanel(null);
    window.history.replaceState(null, "", pageUrl(sample, null));
  }, [sample]);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const onCanvasKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if ((event.target as Element).closest("input, [data-canvas-ignore]")) return;
    if (event.key === "+" || event.key === "=") zp.zoomBy(ZOOM_STEP);
    else if (event.key === "-" || event.key === "_") zp.zoomBy(1 / ZOOM_STEP);
    else if (event.key === "0") zp.fit(layout, { insetRight: drawerW });
    else if (event.key.startsWith("Arrow")) {
      event.preventDefault();
      const step = KEY_PAN_STEP;
      zp.panBy(
        event.key === "ArrowLeft" ? step : event.key === "ArrowRight" ? -step : 0,
        event.key === "ArrowUp" ? step : event.key === "ArrowDown" ? -step : 0,
      );
    }
  };

  const included = new Set(target?.included_asset_ids ?? []);
  const hot = new Set(target?.edges.map(edgeKey) ?? []);
  const shareByEntry = new Map(selected?.routes.map((r) => [r.entry_asset_id, r]) ?? []);
  const focused = target !== null;

  const counts = {
    entry: graph.nodes.filter((n) => n.role === "entry").length,
    reachable: graph.nodes.filter((n) => n.role === "reachable").length,
    unreachable: graph.nodes.filter((n) => n.role === "unreachable").length,
    unknown: graph.nodes.filter((n) => n.role === "unknown").length,
  };

  return (
    <div
      className="gx"
      ref={canvasRef}
      {...zp.handlers}
      onKeyDown={onCanvasKey}
      tabIndex={0}
      aria-label="Attack graph canvas. Arrow keys move the view, plus and minus zoom, 0 fits it to the screen."
      onClick={(event) => {
        if (zp.wasDrag()) return;
        if ((event.target as Element).closest("[data-node], [data-canvas-ignore]")) return;
        if (panel) close();
      }}
      style={{
        backgroundSize: `${GRID * view.k}px ${GRID * view.k}px`,
        backgroundPosition: `${view.x}px ${view.y}px`,
      }}
    >
      <svg className={`gx-svg amap${focused ? " focused" : ""}`} aria-label="Attack graph" role="group">
        <defs>
          <marker id="am-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 z" className="am-arrowhead" />
          </marker>
          <marker id="am-arrow-hot" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 z" className="am-arrowhead hot" />
          </marker>
        </defs>
        <g
          className="gx-world"
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`,
            transition: zp.animate ? "transform 0.35s cubic-bezier(0.2, 0.7, 0.2, 1)" : "none",
          }}
        >
          <g className="am-layers">
            <text x={layout.internet.cx} y={20} textAnchor="middle">
              Attacker
            </text>
            {layout.layers.map((layer) => (
              <text key={layer.column} x={layer.cx} y={20} textAnchor="middle">
                {layer.title}
              </text>
            ))}
          </g>

          <g className="am-caption-g">
            {layout.groups.map((group) =>
              group.segmentId !== null ? (
                <text
                  key={group.key}
                  className={`am-caption${group.declared ? "" : " tentative"}`}
                  x={group.cx}
                  y={group.y + GROUP_HEAD - 12}
                  textAnchor="middle"
                >
                  {group.name}
                  {group.declared ? "" : " (undeclared)"}
                </text>
              ) : null,
            )}
          </g>

          <g className="am-edges">
            {layout.edges.map((edge) => {
              const a = layout.nodeAt.get(edge.a);
              const b = layout.nodeAt.get(edge.b);
              if (!a || !b) return null;
              const isHot = edge.directed.some((k) => hot.has(k));
              const marker = isHot ? "url(#am-arrow-hot)" : "url(#am-arrow)";
              return (
                <path
                  key={edge.key}
                  className={isHot ? "hot" : undefined}
                  d={edgePath(a, b, NODE_R + 3, NODE_R + 3)}
                  markerEnd={marker}
                  markerStart={edge.twoWay ? marker : undefined}
                >
                  <title>
                    {edge.twoWay
                      ? `${nameOf(edge.a)} and ${nameOf(edge.b)} can reach each other (${edge.reasons.join("; ")})`
                      : `${nameOf(edge.a)} can reach ${nameOf(edge.b)} (${edge.reasons.join("; ")})`}
                  </title>
                </path>
              );
            })}
          </g>

          <g className="am-inet-edges">
            {[...layout.nodeAt.values()]
              .filter((p) => p.node.role === "entry")
              .map((p) => {
                const route = shareByEntry.get(p.node.asset_id);
                const isHot = focused && (route !== undefined || p.node.asset_id === selectedId);
                return (
                  <path
                    key={p.node.asset_id}
                    className={isHot ? "hot" : undefined}
                    d={edgePath(layout.internet, p, INTERNET_R + 3, NODE_R + 8)}
                    markerEnd={isHot ? "url(#am-arrow-hot)" : "url(#am-arrow)"}
                    style={route && focused ? ({ strokeWidth: ROUTE_MIN_W + route.share * (ROUTE_MAX_W - ROUTE_MIN_W) } as CSSProperties) : undefined}
                  >
                    <title>
                      {route && selected
                        ? `Internet to ${nameOf(p.node.asset_id)}: ${formatPercent(route.share)} of attacks that reach ${nameOf(selected.asset_id)} start here`
                        : `${nameOf(p.node.asset_id)} is internet-facing`}
                    </title>
                  </path>
                );
              })}
          </g>

          <InternetNode layout={layout} />

          {layout.groups.flatMap((group) =>
            group.nodes.map((p) => (
              <NodeMark
                key={p.node.asset_id}
                placed={p}
                name={nameOf(p.node.asset_id)}
                label={labelOf(p.node.asset_id)}
                selected={p.node.asset_id === selectedId}
                dimmed={focused && !included.has(p.node.asset_id)}
                compromise={target?.node_probabilities[p.node.asset_id]}
                onSelect={() => {
                  if (!zp.wasDrag()) select(p.node.asset_id);
                }}
              />
            )),
          )}
        </g>
      </svg>

      <div className="gx-top" style={{ right: drawerW + 12 }} data-canvas-ignore>
        <div className="gx-chips">
          {sample ? (
            <span className="gx-chip sample">
              Sample network, invented assets
              <Link href="/attack-paths">Back to your snapshot</Link>
            </span>
          ) : null}
          {!graph.topology_declared ? <span className="gx-chip warn">No network topology in this snapshot</span> : null}
          <span className="gx-chip"><i className="dot r-entry" />{formatCount(counts.entry)} entry points</span>
          <span className="gx-chip"><i className="dot r-reachable" />{formatCount(counts.reachable)} reachable</span>
          {counts.unreachable > 0 ? (
            <span className="gx-chip"><i className="dot r-unreachable" />{formatCount(counts.unreachable)} no path in</span>
          ) : null}
          {counts.unknown > 0 ? (
            <span className="gx-chip warn"><i className="dot r-unknown" />{formatCount(counts.unknown)} segment unknown</span>
          ) : null}
        </div>
        <div className="gx-tools">
          <Search nodes={graph.nodes} nameOf={nameOf} onPick={select} />
          <button
            type="button"
            className={`gx-btn${panel?.kind === "topology" ? " on" : ""}`}
            onClick={() => (panel?.kind === "topology" ? close() : setPanel({ kind: "topology" }))}
          >
            Topology
          </button>
          {showSampleLink && !sample ? (
            <Link className="gx-btn" href="/attack-paths?sample=1">
              Sample network
            </Link>
          ) : null}
        </div>
      </div>

      <div className="gx-bl" data-canvas-ignore>
        {legendOpen ? <Legend focused={focused} /> : null}
        <div className="gx-controls" role="toolbar" aria-label="Zoom">
          <button type="button" onClick={() => zp.zoomBy(ZOOM_STEP)} title="Zoom in (+)" aria-label="Zoom in">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v10M3 8h10" /></svg>
          </button>
          <span className="gx-zoom num" aria-live="polite">{Math.round(view.k * 100)}%</span>
          <button type="button" onClick={() => zp.zoomBy(1 / ZOOM_STEP)} title="Zoom out (-)" aria-label="Zoom out">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10" /></svg>
          </button>
          <button type="button" onClick={() => zp.fit(layout, { insetRight: drawerW })} title="Fit to screen (0)" aria-label="Fit to screen">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" /></svg>
          </button>
          <button
            type="button"
            className={legendOpen ? "on" : undefined}
            onClick={() => setLegendOpen((open) => !open)}
            title={legendOpen ? "Hide key" : "Show key"}
            aria-pressed={legendOpen}
            aria-label="Key"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5" /><path d="M8 7.2v3.6M8 5.2v.1" /></svg>
          </button>
        </div>
      </div>

      <Minimap
        layout={layout}
        view={view}
        size={size}
        selectedId={selectedId}
        right={drawerW + 14}
        onJump={(wx, wy, animated) => zp.centerOn(wx, wy, 0, animated)}
      />

      {!panel ? (
        <p className="gx-hint" data-canvas-ignore>
          Drag or two-finger scroll to move, pinch or mouse wheel to zoom, select an asset to see how attacks reach it
        </p>
      ) : null}

      {panel?.kind === "node" && selected ? (
        <NodeDrawer
          node={selected}
          asset={assetsById.get(selected.asset_id) ?? null}
          target={targetState}
          tab={tab}
          onTab={setTab}
          graph={graph}
          nameOf={nameOf}
          onClose={close}
          onSelect={select}
          sample={sample}
        />
      ) : panel?.kind === "topology" ? (
        <TopologyDrawer graph={graph} nameOf={nameOf} onClose={close} onSelect={select} sample={sample} />
      ) : null}
    </div>
  );
}

function InternetNode({ layout }: { layout: GraphLayout }) {
  const { cx: ix, cy: iy } = layout.internet;
  return (
    <g className="am-internet">
      <circle cx={ix} cy={iy} r={INTERNET_R} />
      <path
        d={`M${ix - 12},${iy} H${ix + 12} M${ix},${iy - 12} C${ix - 8},${iy - 6} ${ix - 8},${iy + 6} ${ix},${iy + 12} C${ix + 8},${iy + 6} ${ix + 8},${iy - 6} ${ix},${iy - 12}`}
      />
      <text x={ix} y={iy + INTERNET_R + 17} textAnchor="middle">
        Internet
      </text>
    </g>
  );
}

const ROLE_TEXT: Record<AttackGraphNode["role"], (n: AttackGraphNode) => string> = {
  entry: () => "internet-facing",
  reachable: (n) => `${n.routes.length} route${n.routes.length === 1 ? "" : "s"} in`,
  unreachable: () => "no path in",
  unknown: () => "segment unknown",
};

function NodeMark({
  placed,
  name,
  label,
  selected,
  dimmed,
  compromise,
  onSelect,
}: {
  placed: PlacedNode;
  name: string;
  label: string;
  selected: boolean;
  dimmed: boolean;
  compromise: number | undefined;
  onSelect: () => void;
}) {
  const { node, cx, cy } = placed;
  const heat = compromise !== undefined ? Math.round(compromise * HEAT_MAX_MIX) : 0;
  const status = compromise !== undefined ? `${formatPercent(compromise, 1)} compromised` : ROLE_TEXT[node.role](node);
  const kev = node.kev_finding_count > 0 ? `, ${node.kev_finding_count} known exploited` : "";
  const aria = `${name} (${node.asset_id}): ${status}, ${node.open_finding_count} open finding${node.open_finding_count === 1 ? "" : "s"}${kev}`;
  return (
    <g
      className={`am-node r-${node.role}${selected ? " sel" : ""}${dimmed ? " dim" : ""}`}
      data-node
      role="button"
      tabIndex={0}
      aria-label={aria}
      aria-pressed={selected}
      onClick={(event) => {
        event.stopPropagation();
        onSelect();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <title>{aria}</title>
      {node.role === "entry" ? <circle className="am-ring" cx={cx} cy={cy} r={NODE_R + 5} /> : null}
      <circle
        className="am-dot"
        cx={cx}
        cy={cy}
        r={NODE_R}
        style={heat > 0 ? ({ fill: `color-mix(in srgb, var(--crit) ${heat}%, var(--surface))` } as CSSProperties) : undefined}
      />
      <text className="am-count" x={cx} y={cy + 4.5} textAnchor="middle">
        {node.open_finding_count}
      </text>
      {node.kev_finding_count > 0 ? <circle className="am-kev" cx={cx + NODE_R * 0.74} cy={cy - NODE_R * 0.74} r={5} /> : null}
      <text className="am-name" x={cx} y={cy + NODE_R + 17} textAnchor="middle">
        {label.length > NAME_CHARS ? `${label.slice(0, NAME_CHARS - 1)}…` : label}
      </text>
      <text className="am-status" x={cx} y={cy + NODE_R + 31} textAnchor="middle">
        {status}
      </text>
    </g>
  );
}

function Legend({ focused }: { focused: boolean }) {
  return (
    <ul className="gx-legend" aria-label="Key">
      <li>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle className="lg-node" cx="12" cy="12" r="8" />
          <circle className="lg-kev" cx="18" cy="6" r="3.5" />
        </svg>
        Asset, with its open findings; red dot if one is known exploited
      </li>
      <li>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle className="lg-ring" cx="12" cy="12" r="10.5" />
          <circle className="lg-node" cx="12" cy="12" r="7" />
        </svg>
        Internet-facing
      </li>
      <li>
        <svg viewBox="0 0 24 10" aria-hidden="true">
          <path className="lg-link" d="M5,5 H19" markerStart="url(#am-arrow)" markerEnd="url(#am-arrow)" />
        </svg>
        Can reach; two heads when both ways
      </li>
      {focused ? (
        <>
          <li>
            <svg viewBox="0 0 24 10" aria-hidden="true">
              <path className="lg-hot" d="M1,5 H23" />
            </svg>
            On a path to the selected asset
          </li>
          <li>
            <span className="lg-heat" aria-hidden="true" />
            Redder is more often compromised
          </li>
        </>
      ) : null}
    </ul>
  );
}

function Search({
  nodes,
  nameOf,
  onPick,
}: {
  nodes: AttackGraphNode[];
  nameOf: (id: string) => string;
  onPick: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const q = query.trim().toLowerCase();
  const results = q
    ? nodes
        .filter((n) => n.asset_id.toLowerCase().includes(q) || nameOf(n.asset_id).toLowerCase().includes(q))
        .slice(0, SEARCH_RESULTS)
    : [];
  const pick = (id: string) => {
    onPick(id);
    setQuery("");
    setOpen(false);
  };
  return (
    <div className="gx-search">
      <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" /></svg>
      <input
        type="search"
        placeholder="Find an asset"
        value={query}
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls="gx-search-list"
        aria-activedescendant={open && results[active] ? `gx-opt-${results[active].asset_id}` : undefined}
        aria-autocomplete="list"
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((i) => Math.min(i + 1, results.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (event.key === "Enter" && results[active]) {
            event.preventDefault();
            pick(results[active].asset_id);
          } else if (event.key === "Escape") {
            // First Esc clears the query; with nothing typed it falls through
            // to the page and closes the drawer.
            if (query) {
              event.stopPropagation();
              setQuery("");
            } else {
              event.currentTarget.blur();
            }
          }
        }}
      />
      {open && q ? (
        <ul className="gx-results" id="gx-search-list" role="listbox">
          {results.length === 0 ? (
            <li className="none">No asset matches</li>
          ) : (
            results.map((n, i) => (
              <li
                key={n.asset_id}
                id={`gx-opt-${n.asset_id}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(event) => {
                  event.preventDefault();
                  pick(n.asset_id);
                }}
                onMouseEnter={() => setActive(i)}
              >
                <i className={`dot r-${n.role}`} />
                <span>
                  {nameOf(n.asset_id)}
                  <span className="sub mono">{n.asset_id}</span>
                </span>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}

function Minimap({
  layout,
  view,
  size,
  selectedId,
  right,
  onJump,
}: {
  layout: GraphLayout;
  view: View;
  size: { w: number; h: number };
  selectedId: string | null;
  right: number;
  onJump: (wx: number, wy: number, animated: boolean) => void;
}) {
  const s = Math.min(MINIMAP_W / layout.width, MINIMAP_MAX_H / layout.height);
  const w = layout.width * s;
  const h = layout.height * s;
  const dragging = useRef(false);
  const toWorld = (event: ReactPointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return [(event.clientX - rect.left) / s, (event.clientY - rect.top) / s] as const;
  };
  if (size.w === 0) return null;
  return (
    <div className="gx-mini" style={{ right }} data-canvas-ignore>
      <svg
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        aria-label="Minimap: select to move the view"
        onPointerDown={(event) => {
          dragging.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          const [x, y] = toWorld(event);
          onJump(x, y, true);
        }}
        onPointerMove={(event) => {
          if (!dragging.current) return;
          const [x, y] = toWorld(event);
          onJump(x, y, false);
        }}
        onPointerUp={() => {
          dragging.current = false;
        }}
      >
        {[...layout.nodeAt.values()].map((p) => (
          <circle
            key={p.node.asset_id}
            className={`mm-node r-${p.node.role}${p.node.asset_id === selectedId ? " sel" : ""}`}
            cx={p.cx * s}
            cy={p.cy * s}
            r={p.node.asset_id === selectedId ? 3.5 : 2.4}
          />
        ))}
        <rect
          className="mm-view"
          x={(-view.x / view.k) * s}
          y={(-view.y / view.k) * s}
          width={(size.w / view.k) * s}
          height={(size.h / view.k) * s}
        />
      </svg>
    </div>
  );
}
