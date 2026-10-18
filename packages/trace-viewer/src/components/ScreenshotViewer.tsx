import { useEffect, useMemo, useRef, useState, type WheelEvent } from "react";
import type { ElementBox } from "../types";
import { clamp, cx } from "../utils";

export type OverlayMode = "none" | "target" | "som" | "all";

export interface ScreenshotViewerProps {
  src: string | null | undefined;
  alt?: string;
  /** Element boxes in screenshot pixel coordinates. Overlay is only available when provided. */
  boxes?: ElementBox[];
  /** Bid(s) to emphasise (e.g. the action target). */
  highlightBids?: string[];
  /** Bid hovered elsewhere (e.g. in the AXTree). */
  hoverBid?: string | null;
  overlay?: OverlayMode;
  onOverlayChange?: (mode: OverlayMode) => void;
  defaultOverlay?: OverlayMode;
  onSelectBid?: (bid: string) => void;
  /** Natural image size; inferred from the image when omitted. */
  naturalSize?: { width: number; height: number };
  minZoom?: number;
  maxZoom?: number;
  className?: string;
}

const OVERLAY_LABELS: Record<OverlayMode, string> = { none: "Off", target: "Target", som: "SOM", all: "All" };

export function ScreenshotViewer({
  src,
  alt = "Step screenshot",
  boxes,
  highlightBids = [],
  hoverBid = null,
  overlay,
  onOverlayChange,
  defaultOverlay = "target",
  onSelectBid,
  naturalSize,
  minZoom = 0.25,
  maxZoom = 4,
  className,
}: ScreenshotViewerProps) {
  const [innerOverlay, setInnerOverlay] = useState<OverlayMode>(defaultOverlay);
  const mode = overlay ?? innerOverlay;
  const setMode = (m: OverlayMode) => {
    setInnerOverlay(m);
    onOverlayChange?.(m);
  };
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [measured, setMeasured] = useState<{ width: number; height: number } | null>(null);
  const size = naturalSize ?? measured;
  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewportWidth, setViewportWidth] = useState(0);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => entry && setViewportWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fitScale = size && viewportWidth ? Math.min(1, viewportWidth / size.width) : 1;
  const scale = zoom === "fit" ? fitScale : zoom;
  const setScale = (s: number) => setZoom(clamp(Math.round(s * 100) / 100, minZoom, maxZoom));

  const onWheel = (e: WheelEvent<HTMLDivElement>) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setScale(scale * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
  };

  const visibleBoxes = useMemo(() => {
    if (!boxes || mode === "none") return [];
    const hl = new Set(highlightBids);
    const shown = boxes.filter((b) => {
      if (hl.has(b.bid) || b.bid === hoverBid) return true;
      if (mode === "som") return b.som || b.clickable;
      if (mode === "all") return true;
      return false;
    });
    // draw highlighted boxes last so they sit on top
    return shown.sort((a, b) => Number(hl.has(a.bid)) - Number(hl.has(b.bid)));
  }, [boxes, mode, highlightBids, hoverBid]);

  const hasBoxes = Boolean(boxes && boxes.length);
  const highlightMissing = hasBoxes && highlightBids.some((bid) => !boxes!.some((b) => b.bid === bid));

  return (
    <div className={cx("stv-shot", className)}>
      <div className="stv-shot__toolbar" role="toolbar" aria-label="Screenshot controls">
        <div className="stv-btn-group" role="group" aria-label="Zoom">
          <button type="button" className="stv-btn" onClick={() => setScale(scale / 1.25)} aria-label="Zoom out">
            −
          </button>
          <span className="stv-shot__zoom" aria-live="polite">
            {Math.round(scale * 100)}%
          </span>
          <button type="button" className="stv-btn" onClick={() => setScale(scale * 1.25)} aria-label="Zoom in">
            +
          </button>
          <button
            type="button"
            className="stv-btn"
            aria-pressed={zoom === "fit"}
            onClick={() => setZoom("fit")}
          >
            Fit
          </button>
          <button type="button" className="stv-btn" aria-pressed={zoom === 1} onClick={() => setZoom(1)}>
            1:1
          </button>
        </div>
        {hasBoxes && (
          <div className="stv-btn-group" role="group" aria-label="Element overlay">
            {(Object.keys(OVERLAY_LABELS) as OverlayMode[]).map((m) => (
              <button key={m} type="button" className="stv-btn" aria-pressed={mode === m} onClick={() => setMode(m)}>
                {OVERLAY_LABELS[m]}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="stv-shot__viewport" ref={viewportRef} onWheel={onWheel}>
        {src ? (
          <div
            className="stv-shot__canvas"
            style={size ? { width: size.width * scale, height: size.height * scale } : undefined}
          >
            <img
              src={src}
              alt={alt}
              draggable={false}
              className="stv-shot__img"
              style={size ? { width: size.width * scale, height: size.height * scale } : undefined}
              onLoad={(e) => {
                const img = e.currentTarget;
                if (img.naturalWidth) setMeasured({ width: img.naturalWidth, height: img.naturalHeight });
              }}
            />
            {size && visibleBoxes.length > 0 && (
              <svg
                className="stv-shot__overlay"
                viewBox={`0 0 ${size.width} ${size.height}`}
                preserveAspectRatio="none"
                aria-label="Element boxes"
              >
                {visibleBoxes.map((b) => {
                  const [x, y, w, h] = b.bbox;
                  const isHl = highlightBids.includes(b.bid);
                  const isHover = b.bid === hoverBid;
                  const label = `[${b.bid}]`;
                  const labelW = 7 * label.length + 6;
                  return (
                    <g
                      key={b.bid}
                      className={cx("stv-box", isHl && "stv-box--target", isHover && "stv-box--hover", b.som && "stv-box--som")}
                      data-bid={b.bid}
                      onClick={onSelectBid ? () => onSelectBid(b.bid) : undefined}
                    >
                      <rect x={x} y={y} width={w} height={h} vectorEffect="non-scaling-stroke" />
                      <rect className="stv-box__tag" x={x} y={Math.max(0, y - 14)} width={labelW} height={14} />
                      <text x={x + 3} y={Math.max(0, y - 14) + 11}>
                        {label}
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>
        ) : (
          <div className="stv-empty">No screenshot for this step</div>
        )}
      </div>
      {highlightMissing && mode !== "none" && (
        <div className="stv-shot__note">Target element is not visible in this screenshot.</div>
      )}
    </div>
  );
}
