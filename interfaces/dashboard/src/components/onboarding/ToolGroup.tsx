"use client";

import { useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from "react";
import type { ChannelState } from "@/lib/coverage";
import { CATEGORY_INFO, type ToolCategory, type ToolOption } from "@/lib/tool-catalog";
import type { CustomTool } from "@/lib/tool-selection-state";

const STATE_LABEL: Record<ChannelState, string> = {
  off: "Not covered",
  declared: "Declared",
  connected: "Connects today",
};

/** DOM id of a category's section, for the telemetry map to scroll to. */
export function groupId(category: ToolCategory): string {
  return `grp-${category.toLowerCase().replace(/[^a-z]+/g, "-")}`;
}

/**
 * One kind of telemetry on the setup screen: what it feeds, its catalog
 * tools, the org's own tools, and a way to add one that isn't listed.
 */
export function ToolGroup({
  category,
  tools,
  customTools,
  state,
  selected,
  onToggle,
  onAdd,
  onRemove,
  freshId,
}: {
  category: ToolCategory;
  tools: ToolOption[];
  customTools: CustomTool[];
  state: ChannelState;
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onAdd: (category: ToolCategory, name: string) => void;
  onRemove: (id: string) => void;
  /** The custom tool just added, which animates in; saved ones appear without motion. */
  freshId: string | null;
}) {
  const picked =
    tools.filter((t) => selected.has(t.id)).length + customTools.filter((t) => selected.has(t.id)).length;
  const id = groupId(category);

  return (
    <section id={id} className="ob-group" data-state={state} aria-labelledby={`${id}-h`}>
      <div className="ob-group-head">
        <h2 id={`${id}-h`} tabIndex={-1}>
          <span className="ob-state-dot" aria-hidden="true" />
          {category}
        </h2>
        <span className="ob-group-count">
          {picked ? `${picked} picked, ${STATE_LABEL[state].toLowerCase()}` : STATE_LABEL[state]}
        </span>
        <p>{CATEGORY_INFO[category].feeds}</p>
      </div>
      <div className="ob-cards">
        {tools.map((tool) => (
          <ToolCard
            key={tool.id}
            id={tool.id}
            name={tool.name}
            blurb={tool.blurb}
            available={tool.available}
            logo={tool.logo}
            mark={tool.mark}
            tone={`var(--s${tool.tone})`}
            on={selected.has(tool.id)}
            onToggle={onToggle}
          />
        ))}
        {customTools.map((tool) => (
          <ToolCard
            key={tool.id}
            id={tool.id}
            name={tool.name}
            blurb="Added by you"
            available={false}
            mark={monogram(tool.name)}
            tone="var(--other)"
            on={selected.has(tool.id)}
            onToggle={onToggle}
            onRemove={onRemove}
            fresh={tool.id === freshId}
          />
        ))}
        <AddTool category={category} onAdd={onAdd} />
      </div>
    </section>
  );
}

function monogram(name: string): string {
  const words = name.trim().split(/\s+/);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : name.trim().slice(0, 2);
  return letters.toUpperCase() || "?";
}

function ToolCard({
  id,
  name,
  blurb,
  available,
  logo,
  mark,
  tone,
  on,
  onToggle,
  onRemove,
  fresh,
}: {
  id: string;
  name: string;
  blurb: string;
  available: boolean;
  logo?: string;
  mark: string;
  tone: string;
  on: boolean;
  onToggle: (id: string) => void;
  onRemove?: (id: string) => void;
  fresh?: boolean;
}) {
  const statusId = `${id}-status`;
  return (
    <div className={`ob-card-wrap${fresh ? " fresh" : ""}`}>
      <label className={`ob-card${on ? " on" : ""}${available ? " live" : ""}`} style={{ "--tone": tone } as CSSProperties}>
        <input
          type="checkbox"
          className="sr-only"
          checked={on}
          onChange={() => onToggle(id)}
          aria-describedby={statusId}
        />
        <span className={`ob-icon${logo ? " has-logo" : ""}`} aria-hidden="true">
          {logo ? (
            // Local, small, fixed-size logos: next/image's resizing buys nothing here.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logo} alt="" width={30} height={30} loading="lazy" />
          ) : (
            mark
          )}
        </span>
        <span className="ob-card-text">
          <b className="ob-card-name">{name}</b>
          <span className="ob-card-blurb">{blurb}</span>
          <span id={statusId} className="ob-badge">
            {available ? "Connects today" : "Declare only"}
          </span>
        </span>
        <span className="ob-check" aria-hidden="true">
          <svg viewBox="0 0 16 16">
            <path d="M3.5 8.5l3 3 6-7" pathLength={1} />
          </svg>
        </span>
      </label>
      {onRemove ? (
        <button type="button" className="ob-remove" onClick={() => onRemove(id)} aria-label={`Remove ${name}`}>
          Remove
        </button>
      ) : null}
    </div>
  );
}

/** "Add a tool": a button that opens an inline name field; Enter adds, Escape cancels. */
function AddTool({ category, onAdd }: { category: ToolCategory; onAdd: (category: ToolCategory, name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const opener = useRef<HTMLButtonElement>(null);

  function close() {
    setOpen(false);
    setValue("");
    requestAnimationFrame(() => opener.current?.focus());
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const name = value.trim();
    if (!name) return;
    onAdd(category, name);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  }

  if (!open) {
    return (
      <button ref={opener} type="button" className="ob-add" onClick={() => setOpen(true)}>
        <span className="ob-add-plus" aria-hidden="true">
          +
        </span>
        <span>
          <b>Add a tool</b>
          <span>Using something not listed here?</span>
        </span>
      </button>
    );
  }

  return (
    <form className="ob-add open" onSubmit={submit}>
      <label className="sr-only" htmlFor={`add-${groupId(category)}`}>
        Tool name ({category})
      </label>
      <input
        id={`add-${groupId(category)}`}
        type="text"
        value={value}
        maxLength={60}
        placeholder="Tool name"
        autoFocus
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="ob-add-actions">
        <button type="submit" className="btn" disabled={!value.trim()}>
          Add
        </button>
        <button type="button" className="linkbtn" onClick={close}>
          Done
        </button>
      </div>
    </form>
  );
}
