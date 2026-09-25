"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from "react";

/**
 * Zoom and pan for a canvas of world coordinates: `screen = world * k + (x, y)`.
 *
 * Gestures follow map and design tools: dragging pans; a trackpad's two-finger
 * scroll pans and its pinch zooms; a mouse wheel zooms about the pointer;
 * Ctrl/⌘ + scroll always zooms and Shift + scroll pans sideways. Presentation
 * only — nothing here knows what is being drawn.
 */

export interface View {
  k: number;
  x: number;
  y: number;
}

export const MIN_ZOOM = 0.2;
export const MAX_ZOOM = 3;
/** Pointer travel, in pixels, beyond which a press is a drag rather than a click. */
const DRAG_THRESHOLD = 4;
/** How strongly one wheel notch zooms. */
const WHEEL_ZOOM_RATE = 0.0016;
/**
 * A mouse wheel reports whole notches (line mode, or pixel deltas of 40+ on one
 * axis); a trackpad reports small, often fractional, pixel deltas on both axes.
 */
const MOUSE_WHEEL_MIN_DELTA = 40;
/** How far one arrow-key press pans, in pixels. */
export const KEY_PAN_STEP = 60;

function isMouseWheel(event: WheelEvent): boolean {
  if (event.deltaMode === 1) return true;
  return event.deltaX === 0 && Number.isInteger(event.deltaY) && Math.abs(event.deltaY) >= MOUSE_WHEEL_MIN_DELTA;
}

const clampK = (k: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, k));

export function useZoomPan(container: RefObject<HTMLElement | null>) {
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const [size, setSize] = useState({ w: 0, h: 0 });
  // True while a programmatic move (fit, centre, button zoom) should ease in.
  const [animate, setAnimate] = useState(false);
  const viewRef = useRef(view);
  useEffect(() => {
    viewRef.current = view;
  }, [view]);
  const drag = useRef<{ id: number; sx: number; sy: number; vx: number; vy: number; moved: boolean } | null>(null);
  const lastWasDrag = useRef(false);

  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [container]);

  // Wheel must be a non-passive listener to stop the page scrolling under the canvas.
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if ((event.target as Element | null)?.closest("[data-canvas-ignore]")) return;
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      const scale = event.deltaMode === 1 ? 16 : 1;
      const dx = event.deltaX * scale;
      const dy = event.deltaY * scale;
      setAnimate(false);
      // Pinch arrives as ctrl + wheel; Ctrl/⌘ + scroll zooms on any device.
      const zoom = event.ctrlKey || event.metaKey || (!event.shiftKey && isMouseWheel(event));
      if (!zoom) {
        // Shift + mouse wheel scrolls sideways; a trackpad already reports both axes.
        const panX = event.shiftKey && dx === 0 ? dy : dx;
        const panY = event.shiftKey && dx === 0 ? 0 : dy;
        setView((v) => ({ ...v, x: v.x - panX, y: v.y - panY }));
        return;
      }
      setView((v) => {
        const k = clampK(v.k * Math.exp(-dy * WHEEL_ZOOM_RATE * (event.ctrlKey ? 4 : 1)));
        return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [container]);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || (event.target as Element).closest("[data-canvas-ignore]")) return;
    const v = viewRef.current;
    drag.current = { id: event.pointerId, sx: event.clientX, sy: event.clientY, vx: v.x, vy: v.y, moved: false };
    lastWasDrag.current = false;
  }, []);

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (!d || d.id !== event.pointerId) return;
    const dx = event.clientX - d.sx;
    const dy = event.clientY - d.sy;
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    if (!d.moved) {
      d.moved = true;
      event.currentTarget.setPointerCapture(event.pointerId);
      setAnimate(false);
    }
    setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy }));
  }, []);

  const onPointerUp = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (!d || d.id !== event.pointerId) return;
    lastWasDrag.current = d.moved;
    drag.current = null;
  }, []);

  /** Whether the press that produced the current click was really a drag. */
  const wasDrag = useCallback(() => lastWasDrag.current, []);

  const zoomBy = useCallback(
    (factor: number) => {
      setAnimate(true);
      setView((v) => {
        const k = clampK(v.k * factor);
        const cx = size.w / 2;
        const cy = size.h / 2;
        return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
      });
    },
    [size],
  );

  /** Fit a world-space box into the canvas, leaving `insetRight` pixels clear (e.g. for a drawer). */
  const fit = useCallback(
    (bounds: { width: number; height: number }, options: { pad?: number; insetRight?: number; maxK?: number; animated?: boolean } = {}) => {
      const { pad = 40, insetRight = 0, maxK = 1.25, animated = true } = options;
      const aw = Math.max(size.w - insetRight - pad * 2, 1);
      const ah = Math.max(size.h - pad * 2, 1);
      const k = clampK(Math.min(aw / bounds.width, ah / bounds.height, maxK));
      setAnimate(animated);
      setView({ k, x: pad + (aw - bounds.width * k) / 2, y: pad + (ah - bounds.height * k) / 2 });
    },
    [size],
  );

  /** Pan by a screen-space offset (keyboard). */
  const panBy = useCallback((dx: number, dy: number) => {
    setAnimate(true);
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  }, []);

  /** Bring a world point to the middle of the canvas (less `insetRight`), keeping the zoom. */
  const centerOn = useCallback(
    (wx: number, wy: number, insetRight = 0, animated = true) => {
      setAnimate(animated);
      setView((v) => ({ ...v, x: (size.w - insetRight) / 2 - wx * v.k, y: size.h / 2 - wy * v.k }));
    },
    [size],
  );

  return {
    view,
    size,
    animate,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp },
    wasDrag,
    zoomBy,
    panBy,
    fit,
    centerOn,
  };
}
