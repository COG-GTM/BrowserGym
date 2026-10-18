import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useStepDetail, type StepDetailLoader } from "../hooks/useStepDetail";
import { tryParseAction } from "../parsers/action";
import type { ChatMessage, ElementBox, Run, Step, StepDetail } from "../types";
import { clamp, cx, formatDuration } from "../utils";
import { ActionBadge } from "./ActionBadge";
import { AXTreeViewer } from "./AXTreeViewer";
import { ChatTranscript } from "./ChatTranscript";
import { ScreenshotViewer, type OverlayMode } from "./ScreenshotViewer";
import { StepTimeline } from "./StepTimeline";

export const PLAYBACK_SPEEDS = [0.5, 1, 2, 4] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

export interface RunReplayPlayerProps {
  run?: Run | null;
  steps: Array<Step | StepDetail>;
  chat?: ChatMessage[];
  /** Lazily fetch `StepDetail` (axtree etc.) for steps that only carry `Step` fields. */
  getStepDetail?: StepDetailLoader;
  /** Element boxes for the overlay, per step index. */
  getBoxes?: (index: number) => ElementBox[] | undefined;
  /** Resolve the screenshot URL for a step. Defaults to `apiBaseUrl + step.screenshot_url`. */
  resolveScreenshotUrl?: (step: Step) => string | null | undefined;
  /** Prefix for relative `screenshot_url`s, e.g. `http://localhost:8000/api/v1`. */
  apiBaseUrl?: string;
  /** Controlled step index. */
  index?: number;
  onIndexChange?: (index: number) => void;
  initialIndex?: number;
  /** Milliseconds per step at 1x. */
  stepIntervalMs?: number;
  initialSpeed?: PlaybackSpeed;
  autoPlay?: boolean;
  /** When the viewer is on the last step and new steps arrive (live run), jump to the newest. */
  followLatest?: boolean;
  defaultOverlay?: OverlayMode;
  /**
   * Which step carries an action's error. BrowserGym reports it in the *next* observation (`"next"`);
   * use `"same"` if the producer stores it on the step that issued the action.
   */
  errorAttribution?: "next" | "same";
  className?: string;
}

type SideTab = "axtree" | "chat" | "details";

function defaultResolver(apiBaseUrl: string | undefined) {
  return (step: Step) => {
    const url = step.screenshot_url;
    if (!url) return null;
    if (/^(https?:|data:|blob:)/.test(url) || !apiBaseUrl) return url;
    return apiBaseUrl.replace(/\/$/, "") + (url.startsWith("/") ? url : `/${url}`);
  };
}

export function RunReplayPlayer({
  run,
  steps,
  chat = [],
  getStepDetail,
  getBoxes,
  resolveScreenshotUrl,
  apiBaseUrl,
  index: controlledIndex,
  onIndexChange,
  initialIndex = 0,
  stepIntervalMs = 1500,
  initialSpeed = 1,
  autoPlay = false,
  followLatest = true,
  defaultOverlay = "target",
  errorAttribution = "next",
  className,
}: RunReplayPlayerProps) {
  const [innerIndex, setInnerIndex] = useState(initialIndex);
  const last = Math.max(0, steps.length - 1);
  const index = clamp(controlledIndex ?? innerIndex, 0, last);
  const [playing, setPlaying] = useState(autoPlay);
  const [speed, setSpeed] = useState<PlaybackSpeed>(initialSpeed);
  const [tab, setTab] = useState<SideTab>("axtree");
  const [hoverBid, setHoverBid] = useState<string | null>(null);
  const [selectedBid, setSelectedBid] = useState<string | null>(null);

  const setIndex = useCallback(
    (i: number) => {
      const next = clamp(i, 0, last);
      setInnerIndex(next);
      onIndexChange?.(next);
      setSelectedBid(null);
    },
    [last, onIndexChange],
  );

  // live follow
  const prevLen = useRef(steps.length);
  useEffect(() => {
    if (followLatest && steps.length > prevLen.current && index === prevLen.current - 1) setIndex(steps.length - 1);
    prevLen.current = steps.length;
  }, [steps.length, followLatest, index, setIndex]);

  // playback
  useEffect(() => {
    if (!playing) return;
    if (index >= last) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setIndex(index + 1), stepIntervalMs / speed);
    return () => clearTimeout(t);
  }, [playing, index, last, speed, stepIntervalMs, setIndex]);

  const step = steps[index];
  const { detail, loading } = useStepDetail(step, getStepDetail);
  const parsed = tryParseAction(step?.action);
  const actionError =
    errorAttribution === "next" ? steps[index + 1]?.last_action_error : step?.last_action_error;
  const timelineSteps = useMemo(
    () =>
      errorAttribution === "next"
        ? steps
        : steps.map((s, i) => ({ ...s, last_action_error: steps[i - 1]?.last_action_error ?? null })),
    [steps, errorAttribution],
  );
  const resolve = resolveScreenshotUrl ?? defaultResolver(apiBaseUrl);
  const boxes = getBoxes?.(index);
  const targetBids = parsed?.bids ?? [];
  const highlightBids = selectedBid ? [...new Set([...targetBids, selectedBid])] : targetBids;
  const axHighlight = selectedBid ?? parsed?.bid ?? null;

  const togglePlay = () => {
    if (!playing && index >= last) setIndex(0);
    setPlaying((p) => !p);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.defaultPrevented) return;
    const t = e.target as HTMLElement;
    if (t.closest("input, textarea, select, [role=tree], [role=slider]")) return;
    if (e.key === " " || e.key === "k") {
      if (t.tagName === "BUTTON" && e.key === " ") return;
      e.preventDefault();
      togglePlay();
    } else if (e.key === "ArrowRight" || e.key === "l") {
      e.preventDefault();
      setIndex(index + 1);
    } else if (e.key === "ArrowLeft" || e.key === "j") {
      e.preventDefault();
      setIndex(index - 1);
    }
  };

  const chatUntil = step?.timestamp ?? null;
  const duration =
    run?.started_at && run?.finished_at ? Date.parse(run.finished_at) - Date.parse(run.started_at) : null;

  return (
    <div className={cx("stv-root", "stv-player", className)} onKeyDown={onKeyDown}>
      {run && (
        <header className="stv-player__header">
          <div className="stv-player__title">
            <span className={cx("stv-status", `stv-status--${run.status}`)}>{run.status}</span>
            <h2>{run.goal || run.task_id}</h2>
          </div>
          <dl className="stv-player__meta">
            <div>
              <dt>Task</dt>
              <dd>{run.task_id}</dd>
            </div>
            <div>
              <dt>Agent</dt>
              <dd>
                {run.agent.type}
                {run.agent.model ? ` · ${run.agent.model}` : ""}
              </dd>
            </div>
            <div>
              <dt>Steps</dt>
              <dd>
                {run.n_steps}
                {run.max_steps ? ` / ${run.max_steps}` : ""}
              </dd>
            </div>
            {run.reward !== null && run.reward !== undefined && (
              <div>
                <dt>Reward</dt>
                <dd>{run.reward}</dd>
              </div>
            )}
            {duration !== null && (
              <div>
                <dt>Duration</dt>
                <dd>{formatDuration(duration)}</dd>
              </div>
            )}
          </dl>
          {run.error && <div className="stv-alert stv-alert--error">{run.error}</div>}
        </header>
      )}

      <div className="stv-player__body">
        <section className="stv-player__stage" aria-label="Step view">
          <ScreenshotViewer
            src={step ? resolve(step) : null}
            alt={step ? `Screenshot of step ${index + 1}` : undefined}
            boxes={boxes}
            highlightBids={highlightBids}
            hoverBid={hoverBid}
            defaultOverlay={defaultOverlay}
            onSelectBid={(bid) => {
              setSelectedBid(bid);
              setTab("axtree");
            }}
          />
          {step && (
            <div className="stv-stepcard">
              <div className="stv-stepcard__row">
                <span className="stv-stepcard__index">#{index + 1}</span>
                <ActionBadge
                  action={step.action}
                  error={Boolean(actionError)}
                  onBidHover={setHoverBid}
                  onBidClick={(bid) => {
                    setSelectedBid(bid);
                    setTab("axtree");
                  }}
                />
                {step.elapsed_ms !== null && step.elapsed_ms !== undefined && (
                  <span className="stv-stepcard__muted">{formatDuration(step.elapsed_ms)}</span>
                )}
              </div>
              {step.thought && <p className="stv-stepcard__thought">{step.thought}</p>}
              {actionError && (
                <div className="stv-alert stv-alert--error" role="alert">
                  <strong>Action failed:</strong> {actionError}
                </div>
              )}
            </div>
          )}
        </section>

        <section className="stv-player__side" aria-label="Step data">
          <div className="stv-tabs" role="tablist">
            {(
              [
                ["axtree", "AXTree"],
                ["chat", `Chat (${chat.length})`],
                ["details", "Details"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                className="stv-tab"
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="stv-tabpanel" role="tabpanel">
            {tab === "axtree" &&
              (loading && !detail?.axtree_txt ? (
                <div className="stv-empty">Loading…</div>
              ) : (
                <AXTreeViewer
                  axtree={detail?.axtree_txt}
                  highlightBid={axHighlight}
                  focusedBid={detail?.focused_element_bid}
                  onHoverBid={setHoverBid}
                  onSelectBid={setSelectedBid}
                />
              ))}
            {tab === "chat" && <ChatTranscript messages={chat} until={chatUntil} />}
            {tab === "details" && step && (
              <dl className="stv-details">
                <dt>URL</dt>
                <dd>{step.url ?? "—"}</dd>
                <dt>Action</dt>
                <dd>
                  <code>{step.action ?? "—"}</code>
                </dd>
                <dt>Reward</dt>
                <dd>{step.reward}</dd>
                <dt>Terminated / truncated</dt>
                <dd>
                  {String(step.terminated)} / {String(step.truncated)}
                </dd>
                <dt>Focused element</dt>
                <dd>{detail?.focused_element_bid ?? "—"}</dd>
                <dt>Timestamp</dt>
                <dd>{step.timestamp}</dd>
              </dl>
            )}
          </div>
        </section>
      </div>

      <footer className="stv-player__controls">
        <div className="stv-btn-group" role="group" aria-label="Playback">
          <button type="button" className="stv-btn" onClick={() => setIndex(index - 1)} disabled={index <= 0} aria-label="Previous step">
            ⏮
          </button>
          <button type="button" className="stv-btn stv-btn--primary" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"} disabled={!steps.length}>
            {playing ? "❚❚" : "▶"}
          </button>
          <button type="button" className="stv-btn" onClick={() => setIndex(index + 1)} disabled={index >= last} aria-label="Next step">
            ⏭
          </button>
          <label className="stv-speed">
            <span className="stv-visually-hidden">Playback speed</span>
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value) as PlaybackSpeed)}>
              {PLAYBACK_SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
        </div>
        <StepTimeline steps={timelineSteps} currentIndex={index} onChange={setIndex} />
      </footer>
    </div>
  );
}
