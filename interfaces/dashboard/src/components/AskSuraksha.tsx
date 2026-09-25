"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  AGENT_PANEL_MAX_WIDTH,
  AGENT_PANEL_MIN_WIDTH,
  closeAgentPanel,
  setAgentPanelWidth,
  toggleAgentPanel,
  useAgentPanelOpen,
  useAgentPanelWidth,
} from "@/lib/agent-panel-state";
import { deleteChatSession, streamChat, type ApiResult } from "@/lib/api";
import { humanize, shortSnapshotId } from "@/lib/format";
import type { ChatResponse, ChatToolCall } from "@/lib/types";
import { Markdown } from "./Markdown";

const PRESETS = [
  "What is our expected annual loss right now?",
  "Which scenarios contribute most to expected loss?",
  "What happens if MFA is enforced on every asset that lacks it?",
  "Where does the largest contributor's figure come from?",
  "What is our control posture across the estate?",
];

/** Short labels for the relay; an unknown tool falls back to its humanized name. */
const TOOL_LABELS: Record<string, string> = {
  get_exposure: "Current exposure",
  get_top_contributors: "Top loss drivers",
  get_control_posture: "Control posture",
  get_framework_status: "Framework status",
  optimize_investment: "Budget optimizer",
  simulate_scenario: "What-if simulation",
  explain_number: "Figure provenance",
};

function toolLabel(toolName: string): string {
  return TOOL_LABELS[toolName] ?? humanize(toolName);
}

/** One tool call as the relay shows it, live or after the turn. */
interface ToolStep {
  /** `tool_use_id` from the stream; unique within a turn. */
  key: string;
  toolName: string;
  arguments: Record<string, unknown>;
  /** Model/tool round trip, from 0. Absent when the stream did not say. */
  round?: number;
  status: "running" | ChatToolCall["status"];
  detail: string | null;
}

type Turn =
  | {
      id: number;
      question: string;
      state: "pending";
      steps: ToolStep[];
      /** The model is writing prose (never shown until the guard has run). */
      composing: boolean;
    }
  | {
      id: number;
      question: string;
      state: "answered";
      reply: ChatResponse;
      steps: ToolStep[];
      /** The server had no record of the session we sent — history was lost. */
      sessionRestarted: boolean;
    }
  | {
      id: number;
      question: string;
      state: "failed";
      steps: ToolStep[];
      result: Extract<ApiResult<unknown>, { state: "unavailable" | "error" }>;
    };

/**
 * The relay steps for a finished turn: the server's authoritative
 * `tool_calls`, keeping the live key and round where the stream agreed.
 */
function settledSteps(calls: ChatToolCall[], live: ToolStep[]): ToolStep[] {
  return calls.map((call, index) => {
    const seen = live[index]?.toolName === call.tool_name ? live[index] : undefined;
    return {
      key: seen?.key ?? `${call.tool_name}-${index}`,
      toolName: call.tool_name,
      arguments: call.arguments,
      round: seen?.round,
      status: call.status,
      detail: call.detail,
    };
  });
}

/**
 * The trigger that opens the docked Ask Suraksha panel — lives in the
 * topbar, separate from the panel itself (in `AppShell`) so the panel can
 * stay mounted (and its conversation alive) while the trigger toggles its
 * visibility from anywhere in the page chrome.
 */
export function AskSurakshaTrigger() {
  const open = useAgentPanelOpen();
  return (
    <button
      className="btn askbtn"
      type="button"
      aria-haspopup="true"
      aria-expanded={open}
      aria-controls="askPanel"
      onClick={toggleAgentPanel}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3l1.8 4.9L19 9.7l-4.2 3.2 1.4 5.1L12 15.2 7.8 18l1.4-5.1L5 9.7l5.2-1.8z" />
      </svg>
      Ask Suraksha
    </button>
  );
}

/**
 * Ask Suraksha: the natural-language front door to the engine tools,
 * docked to the right edge of the shell and compressing the main column
 * while open — the same shape as an editor's agent sidebar, not a modal
 * laid over the page. Always mounted (see `AppShell`), so opening and
 * closing it never loses the conversation; `useAgentPanelOpen` only
 * toggles its visibility and width.
 *
 * Uses `POST /chat/stream` for its tool events only: every tool the model
 * calls — several per round, over several rounds — appears in the relay as it
 * starts and settles as it finishes. The streamed `text_delta` prose is raw
 * and is never painted (`streamChat` drops it); the answer shown is the
 * `final` event's `text`, which has already been through
 * `ai.numeric_guard`. Its Markdown is formatted by `<Markdown>`, which
 * drops syntax but never rewrites the text, and any `[UNVERIFIED: …]` flag
 * the guard inserted stays visible and highlighted.
 */
export function AskSurakshaPanel() {
  const open = useAgentPanelOpen();
  const width = useAgentPanelWidth();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const nextId = useRef(0);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const [resetting, setResetting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const pending = resetting || turns.some((turn) => turn.state === "pending");

  useEffect(() => {
    if (!open) return;
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 220);
    return () => window.clearTimeout(focusTimer);
  }, [open]);

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [turns, open]);

  async function ask(raw: string) {
    const question = raw.trim();
    if (!question || pending) return;
    const id = nextId.current++;
    const sentSessionId = sessionId;
    setTurns((current) => [
      ...current,
      { id, question, state: "pending", steps: [], composing: false },
    ]);
    setDraft("");

    const updatePending = (change: (turn: Extract<Turn, { state: "pending" }>) => Turn) =>
      setTurns((current) =>
        current.map((turn) => (turn.id === id && turn.state === "pending" ? change(turn) : turn)),
      );

    const result = await streamChat(question, sentSessionId, {
      onToolCall: (event) =>
        updatePending((turn) => ({
          ...turn,
          composing: false,
          steps: [
            ...turn.steps,
            {
              key: event.tool_use_id || `${event.tool_name}-${turn.steps.length}`,
              toolName: event.tool_name,
              arguments: event.arguments ?? {},
              round: event.round,
              status: "running",
              detail: null,
            },
          ],
        })),
      onToolResult: (event) =>
        updatePending((turn) => {
          // Match by id; fall back to the oldest running call of that tool.
          let index = turn.steps.findIndex((step) => step.key === event.tool_use_id);
          if (index === -1) {
            index = turn.steps.findIndex(
              (step) => step.status === "running" && step.toolName === event.tool_name,
            );
          }
          if (index === -1) return turn;
          const steps = turn.steps.slice();
          steps[index] = { ...steps[index], status: event.status, detail: event.detail };
          return { ...turn, steps };
        }),
      onComposing: () =>
        updatePending((turn) => (turn.composing ? turn : { ...turn, composing: true })),
    });

    setTurns((current) =>
      current.map((turn) => {
        if (turn.id !== id) return turn;
        const live = turn.state === "pending" ? turn.steps : [];
        if (result.state !== "ok") {
          // Calls still marked running never reported back before the failure.
          const steps = live.map((step) =>
            step.status === "running"
              ? { ...step, status: "error", detail: "No result — the turn ended first." }
              : step,
          );
          return { id, question, state: "failed", steps, result };
        }
        return {
          id,
          question,
          state: "answered",
          reply: result.data,
          steps: settledSteps(result.data.tool_calls, live),
          sessionRestarted: sentSessionId !== null && sentSessionId !== result.data.session_id,
        };
      }),
    );
    if (result.state === "ok") setSessionId(result.data.session_id);
  }

  async function startOver() {
    setResetting(true);
    if (sessionId) await deleteChatSession(sessionId);
    setSessionId(null);
    setTurns([]);
    setResetting(false);
    inputRef.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeAgentPanel();
    }
  }

  function startResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    setDragging(true);
    function onMove(moveEvent: PointerEvent) {
      const next = startWidth + (startX - moveEvent.clientX);
      setAgentPanelWidth(next);
    }
    function onUp() {
      setDragging(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  return (
    <div
      id="askPanel"
      className={`agentpanel${open ? " is-open" : ""}${dragging ? " is-resizing" : ""}`}
      style={{ width: open ? width : 0, minWidth: open ? width : 0 }}
      role="complementary"
      aria-label="Ask Suraksha"
      aria-hidden={!open}
      inert={!open}
      ref={panelRef}
      onKeyDown={onKeyDown}
    >
      <div
        className="agentpanel-resize"
        onPointerDown={startResize}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize Ask Suraksha panel"
        aria-valuenow={width}
        aria-valuemin={AGENT_PANEL_MIN_WIDTH}
        aria-valuemax={AGENT_PANEL_MAX_WIDTH}
        tabIndex={open ? 0 : -1}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setAgentPanelWidth(width + 16);
          if (event.key === "ArrowRight") setAgentPanelWidth(width - 16);
        }}
      />
      <div className="agentpanel-inner" style={{ width }}>
        <div className="agentpanel-head">
          <div className="agentpanel-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3l1.8 4.9L19 9.7l-4.2 3.2 1.4 5.1L12 15.2 7.8 18l1.4-5.1L5 9.7l5.2-1.8z" />
            </svg>
          </div>
          <div className="agentpanel-title">
            <h2>Ask Suraksha</h2>
            <p>Picks the engine tool, narrates what it returned, never calculates a figure.</p>
          </div>
          <div className="ctrls">
            {turns.length > 0 ? (
              <button
                className="iconbtn"
                type="button"
                disabled={pending}
                title="New conversation"
                aria-label="New conversation"
                onClick={startOver}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 4v5h5M20 20v-5h-5" />
                  <path d="M19.5 9a8 8 0 00-14.9-2M4.5 15a8 8 0 0014.9 2" />
                </svg>
              </button>
            ) : null}
            <button
              className="iconbtn"
              type="button"
              aria-label="Close Ask Suraksha"
              onClick={closeAgentPanel}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
        </div>

        <div className="ask">
          <div className="presets">
            {PRESETS.map((preset) => (
              <button key={preset} type="button" disabled={pending} onClick={() => ask(preset)}>
                {preset}
              </button>
            ))}
          </div>

          <div className="thread" aria-live="polite" ref={threadRef}>
            {turns.length === 0 ? (
              <p className="small muted">
                Ask about current exposure, what drives it, control posture, a
                what-if, or where a figure came from. Any number the assistant
                cannot trace to a tool result in this conversation is flagged
                inline as unverified.
              </p>
            ) : (
              turns.map((turn) => <TurnView key={turn.id} turn={turn} />)
            )}
          </div>

          <form
            className="askform"
            onSubmit={(event) => {
              event.preventDefault();
              ask(draft);
            }}
          >
            <label htmlFor="askInput" className="sr-only">
              Question
            </label>
            <input
              id="askInput"
              ref={inputRef}
              value={draft}
              maxLength={8000}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="e.g. What is our highest financial risk today?"
              autoComplete="off"
            />
            <button className="btn" type="submit" disabled={pending || !draft.trim()}>
              {pending ? "Asking…" : "Ask"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <>
      <div className="q">{turn.question}</div>
      {turn.state === "pending" ? (
        <div className="a pending">
          {turn.steps.length > 0 ? <ToolRelay steps={turn.steps} live /> : null}
          <div className="phase" role="status">
            <span className="spin" aria-hidden="true" />
            {pendingPhase(turn)}
          </div>
        </div>
      ) : turn.state === "failed" ? (
        <div className="a failed">
          {turn.steps.length > 0 ? <ToolRelay steps={turn.steps} /> : null}
          <p className="body-text">
            {turn.result.state === "unavailable"
              ? `The assistant is not available: ${turn.result.reason}`
              : `The assistant could not answer: ${turn.result.reason}`}
          </p>
        </div>
      ) : (
        <Answer reply={turn.reply} steps={turn.steps} sessionRestarted={turn.sessionRestarted} />
      )}
    </>
  );
}

function pendingPhase(turn: Extract<Turn, { state: "pending" }>): string {
  const running = turn.steps.filter((step) => step.status === "running");
  if (running.length > 0) return `Calling ${running.map((step) => step.toolName).join(", ")}…`;
  if (turn.composing) return "Writing the answer — every number is checked against engine output first…";
  if (turn.steps.length > 0) return "Reading the tool results…";
  return "Choosing which engine tools to call…";
}

/**
 * The tool relay: every call the model made this turn, in order.
 *
 * Live, it lists each call as it runs. Settled, it collapses to one summary
 * line whose chips name each tool and its outcome; opening it shows the
 * arguments the model chose and why any call came back without a result.
 */
function ToolRelay({ steps, live = false }: { steps: ToolStep[]; live?: boolean }) {
  const rows = (
    <ol className="relay-list">
      {steps.map((step, index) => (
        <li key={step.key} className={`relay-step ${statusClass(step.status)}`}>
          {index > 0 && step.round !== undefined && step.round !== steps[index - 1].round ? (
            <span className="relay-round">then, using those results</span>
          ) : null}
          <div className="relay-row">
            <StatusIcon status={step.status} />
            <span className="relay-label">{toolLabel(step.toolName)}</span>
            <code className="relay-name">{step.toolName}</code>
            <span className="relay-status">{statusText(step.status)}</span>
          </div>
          {formatArguments(step.arguments) ? (
            <div className="relay-args">{formatArguments(step.arguments)}</div>
          ) : null}
          {step.status !== "ok" && step.status !== "running" && step.detail ? (
            <div className="relay-detail">{step.detail}</div>
          ) : null}
        </li>
      ))}
    </ol>
  );

  if (live) {
    return (
      <div className="relay" aria-label="Engine tools being called">
        {rows}
      </div>
    );
  }

  const problems = steps.filter((step) => step.status !== "ok").length;
  return (
    <details className="relay">
      <summary>
        <span className="relay-sum">
          Called {steps.length} engine tool{steps.length === 1 ? "" : "s"}
          {problems > 0 ? ` · ${problems} without a result` : ""}
        </span>
        <span className="relay-chips" aria-hidden="true">
          {steps.map((step) => (
            <span key={step.key} className={`relay-chip ${statusClass(step.status)}`}>
              <StatusIcon status={step.status} />
              {step.toolName}
            </span>
          ))}
        </span>
      </summary>
      {rows}
    </details>
  );
}

function statusClass(status: ToolStep["status"]): string {
  if (status === "running") return "is-running";
  if (status === "ok") return "is-ok";
  if (status === "unavailable") return "is-unavailable";
  return "is-error";
}

function statusText(status: ToolStep["status"]): string {
  if (status === "running") return "running";
  if (status === "ok") return "done";
  if (status === "unavailable") return "unavailable";
  return status === "error" ? "failed" : status;
}

function StatusIcon({ status }: { status: ToolStep["status"] }) {
  if (status === "running") return <span className="relay-ico spin" aria-hidden="true" />;
  return (
    <svg className="relay-ico" viewBox="0 0 16 16" aria-hidden="true">
      {status === "ok" ? (
        <path d="M3.5 8.5l3 3 6-7" />
      ) : status === "unavailable" ? (
        <path d="M8 3.5v5.5M8 11.5v1" />
      ) : (
        <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" />
      )}
    </svg>
  );
}

/** The arguments the model chose, compactly: `scope: crown-jewels · limit: 5`. */
function formatArguments(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${humanize(key).toLowerCase()}: ${formatArgument(value)}`)
    .join(" · ");
}

function formatArgument(value: unknown): string {
  if (Array.isArray(value)) {
    return value.every((item) => typeof item !== "object" || item === null)
      ? value.join(", ")
      : `${value.length} item${value.length === 1 ? "" : "s"}`;
  }
  if (typeof value === "object" && value !== null) {
    const text = JSON.stringify(value);
    return text.length > 60 ? `${text.slice(0, 57)}…` : text;
  }
  return String(value);
}

function Answer({
  reply,
  steps,
  sessionRestarted,
}: {
  reply: ChatResponse;
  steps: ToolStep[];
  sessionRestarted: boolean;
}) {
  const snapshotId = reply.tool_calls
    .map((call) => call.result?.snapshot_id)
    .find((id): id is string => typeof id === "string");

  return (
    <div className="a">
      {sessionRestarted ? (
        <p className="small muted" style={{ marginBottom: 6 }}>
          The previous conversation had expired on the server, so this answer
          started a new one without the earlier context.
        </p>
      ) : null}
      {steps.length > 0 ? <ToolRelay steps={steps} /> : null}
      <Markdown text={reply.text} />
      <details className="src">
        <summary>Source</summary>
        <div className="body">
          {reply.tool_calls.length === 0 ? (
            <span>No engine tool was called for this answer.</span>
          ) : null}
          {reply.all_claims_verified ? (
            <span className="ok">✓ Every number traced to engine output in this conversation</span>
          ) : (
            <span className="bad">
              ⚠ {reply.unverified_claims.length} number
              {reply.unverified_claims.length === 1 ? "" : "s"} could not be traced to engine output
              — flagged inline
            </span>
          )}
          {snapshotId ? <span>snapshot {shortSnapshotId(snapshotId)}</span> : null}
          {reply.stop_reason === "max_tool_iterations" ? (
            <span className="bad">Stopped after the maximum number of tool calls for one turn.</span>
          ) : null}
          {reply.model ? <span>model: {reply.model}</span> : null}
        </div>
      </details>
    </div>
  );
}
