"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { deleteChatSession, sendChat, type ApiResult } from "@/lib/api";
import { shortSnapshotId } from "@/lib/format";
import type { ChatResponse } from "@/lib/types";

const PRESETS = [
  "What is our expected annual loss right now?",
  "Which scenarios contribute most to expected loss?",
  "What happens if MFA is enforced on every asset that lacks it?",
  "Where does the largest contributor's figure come from?",
  "What is our control posture across the estate?",
];

/** The guard's inline marker for a number it could not trace to a tool result. */
const UNVERIFIED_FLAG = /(\[UNVERIFIED: [^\]]*\])/;

type Turn =
  | { id: number; question: string; state: "pending" }
  | {
      id: number;
      question: string;
      state: "answered";
      reply: ChatResponse;
      /** The server had no record of the session we sent — history was lost. */
      sessionRestarted: boolean;
    }
  | {
      id: number;
      question: string;
      state: "failed";
      result: Extract<ApiResult<unknown>, { state: "unavailable" | "error" }>;
    };

/**
 * Ask Suraksha: the natural-language front door to the engine tools.
 *
 * Uses the non-streaming `POST /chat` on purpose. Its `text` has already been
 * through `ai.numeric_guard` on the server, so there is never a moment where
 * unverified model output is on screen (the streaming endpoint's
 * `text_delta` events are raw and must be repainted from `final` — see
 * interfaces/api/README.md). The text is rendered verbatim, and any
 * `[UNVERIFIED: …]` flag the guard inserted stays visible and highlighted.
 */
export function AskSuraksha() {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const nextId = useRef(0);
  const openerRef = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const [resetting, setResetting] = useState(false);
  const pending = resetting || turns.some((turn) => turn.state === "pending");

  useEffect(() => {
    if (!open) return;
    document.body.classList.add("modal-open");
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 30);
    return () => {
      document.body.classList.remove("modal-open");
      window.clearTimeout(focusTimer);
    };
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
    setTurns((current) => [...current, { id, question, state: "pending" }]);
    setDraft("");
    const result = await sendChat(question, sentSessionId);
    setTurns((current) =>
      current.map((turn) => {
        if (turn.id !== id) return turn;
        if (result.state !== "ok") return { id, question, state: "failed", result };
        return {
          id,
          question,
          state: "answered",
          reply: result.data,
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

  function close() {
    setOpen(false);
    openerRef.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab" || !sheetRef.current) return;
    const focusable = Array.from(
      sheetRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), summary, a[href]",
      ),
    ).filter((element) => element.offsetParent !== null);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <>
      <button
        ref={openerRef}
        className="btn askbtn"
        type="button"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 3l1.8 4.9L19 9.7l-4.2 3.2 1.4 5.1L12 15.2 7.8 18l1.4-5.1L5 9.7l5.2-1.8z" />
        </svg>
        Ask Suraksha
      </button>

      {open ? (
        <div className="modal" onKeyDown={onKeyDown}>
          <div className="scrim" onClick={close} />
          <div
            className="card sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="askTitle"
            ref={sheetRef}
          >
            <div className="card-h">
              <div>
                <h2 id="askTitle">Ask Suraksha</h2>
                <p>
                  The assistant picks which engine tool answers your question and
                  narrates what it returned; it never calculates a figure. Every
                  number is checked against engine output before it is shown.
                </p>
              </div>
              <div className="ctrls">
                {turns.length > 0 ? (
                  <button
                    className="btn ghost"
                    type="button"
                    disabled={pending}
                    onClick={startOver}
                  >
                    New conversation
                  </button>
                ) : null}
                <button className="iconbtn" type="button" aria-label="Close" onClick={close}>
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
      ) : null}
    </>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <>
      <div className="q">{turn.question}</div>
      {turn.state === "pending" ? (
        <div className="a pending">Routing to engine tools…</div>
      ) : turn.state === "failed" ? (
        <div className="a failed">
          <p className="body-text">
            {turn.result.state === "unavailable"
              ? `The assistant is not available: ${turn.result.reason}`
              : `The assistant could not answer: ${turn.result.reason}`}
          </p>
        </div>
      ) : (
        <Answer reply={turn.reply} sessionRestarted={turn.sessionRestarted} />
      )}
    </>
  );
}

function Answer({ reply, sessionRestarted }: { reply: ChatResponse; sessionRestarted: boolean }) {
  const parts = reply.text.split(UNVERIFIED_FLAG);
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
      <p className="body-text">
        {parts.map((part, index) =>
          index % 2 === 1 ? (
            <span key={index} className="flag" title="This number could not be traced to engine output">
              {part}
            </span>
          ) : (
            part
          ),
        )}
      </p>
      <details className="src">
        <summary>Source</summary>
        <div className="body">
          {reply.tool_calls.length === 0 ? (
            <span>No engine tool was called for this answer.</span>
          ) : (
            reply.tool_calls.map((call, index) => (
              <span key={`${call.tool_name}-${index}`}>
                tool: {call.tool_name} · {call.status}
                {call.status !== "ok" && call.detail ? ` — ${call.detail}` : ""}
              </span>
            ))
          )}
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
