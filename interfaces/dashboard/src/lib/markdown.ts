/**
 * A small Markdown parser for the assistant's replies.
 *
 * The reply text has already been through `ai.numeric_guard`, so this parser
 * has one rule above all: it may drop Markdown syntax, but it never rewrites,
 * reorders or drops a character of the prose itself. In particular:
 *
 * - `[UNVERIFIED: …]` flags the guard inserted become their own `flag` node,
 *   wherever they sit (inside bold, a list item or a table cell), so they stay
 *   highlighted;
 * - an ordered list keeps the numbers the model wrote (each item carries its
 *   own `number`), rather than letting the browser renumber them;
 * - `_` only marks emphasis at a word boundary, so identifiers like
 *   `get_exposure` or `snapshot_id` are left alone;
 * - raw HTML is never interpreted — it renders as the text it is.
 *
 * Supported: headings, paragraphs (single newlines are line breaks, as in
 * chat), bold, italics, strikethrough, inline code, fenced code, links
 * (http/https/mailto only), bullet and numbered lists with nesting, GFM
 * tables with column alignment, blockquotes and horizontal rules.
 */

export type Inline =
  | { type: "text"; text: string }
  | { type: "flag"; text: string }
  | { type: "code"; text: string }
  | { type: "strong" | "em" | "del"; children: Inline[] }
  | { type: "link"; href: string; children: Inline[] }
  | { type: "br" };

export type Align = "left" | "center" | "right" | null;

export type Block =
  | { type: "heading"; level: number; children: Inline[] }
  | { type: "paragraph"; children: Inline[] }
  | { type: "code"; text: string }
  | { type: "hr" }
  | { type: "quote"; children: Block[] }
  | { type: "list"; ordered: boolean; items: ListItem[] }
  | { type: "table"; align: Align[]; header: Inline[][]; rows: Inline[][][]; numeric: boolean[] };

export interface ListItem {
  /** The number the model wrote, for an ordered list. */
  number?: number;
  children: Block[];
}

const FLAG = /\[UNVERIFIED: [^\]]*\]/y;
const FENCE = /^\s*(```|~~~)/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const HR = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const QUOTE = /^\s{0,3}>\s?/;
const LIST_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
const TABLE_DIVIDER = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
const NUMERIC_CELL = /^[+\-−~≈]?\s*(₹|Rs\.?|INR|\$)?\s*\d/i;

/** Parse a whole reply into blocks. */
export function parseMarkdown(source: string): Block[] {
  // A flag the guard wrapped around a claim that spanned a line break would
  // otherwise be split in two by block parsing and lose its highlight.
  const text = source
    .replace(/\r\n?/g, "\n")
    .replace(/\[UNVERIFIED: [^\]]*\]/g, (flag) => flag.replace(/\s*\n\s*/g, " "));
  return parseBlocks(text.split("\n"));
}

function indentOf(line: string): number {
  const match = /^\s*/.exec(line);
  return match ? match[0].replace(/\t/g, "    ").length : 0;
}

function isBlank(line: string): boolean {
  return line.trim() === "";
}

function isTableStart(lines: string[], index: number): boolean {
  return (
    index + 1 < lines.length &&
    lines[index].includes("|") &&
    TABLE_DIVIDER.test(lines[index + 1]) &&
    lines[index + 1].includes("-")
  );
}

/** Whether a line opens a block other than a paragraph (ends a paragraph). */
function startsBlock(lines: string[], index: number): boolean {
  const line = lines[index];
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    HR.test(line) ||
    QUOTE.test(line) ||
    LIST_ITEM.test(line) ||
    isTableStart(lines, index)
  );
}

function parseBlocks(lines: string[]): Block[] {
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (isBlank(line)) {
      i++;
      continue;
    }

    const fence = FENCE.exec(line);
    if (fence) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
      i++; // closing fence (or end of input)
      blocks.push({ type: "code", text: body.join("\n") });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, children: parseInline(heading[2]) });
      i++;
      continue;
    }

    if (HR.test(line)) {
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    if (QUOTE.test(line)) {
      const body: string[] = [];
      while (i < lines.length && !isBlank(lines[i]) && (QUOTE.test(lines[i]) || !startsBlock(lines, i))) {
        body.push(lines[i++].replace(QUOTE, ""));
      }
      blocks.push({ type: "quote", children: parseBlocks(body) });
      continue;
    }

    if (isTableStart(lines, i)) {
      const [table, next] = parseTable(lines, i);
      blocks.push(table);
      i = next;
      continue;
    }

    if (LIST_ITEM.test(line)) {
      const [list, next] = parseList(lines, i);
      blocks.push(list);
      i = next;
      continue;
    }

    const body: string[] = [line];
    i++;
    while (i < lines.length && !isBlank(lines[i]) && !startsBlock(lines, i)) body.push(lines[i++]);
    blocks.push({ type: "paragraph", children: parseInline(body.map((l) => l.trim()).join("\n")) });
  }
  return blocks;
}

/** A list starting at `start`: sibling items at its indent, deeper lines nested. */
function parseList(lines: string[], start: number): [Block, number] {
  const first = LIST_ITEM.exec(lines[start])!;
  const baseIndent = indentOf(first[1]);
  const ordered = /\d/.test(first[2]);
  const items: ListItem[] = [];
  let i = start;

  while (i < lines.length) {
    const marker = LIST_ITEM.exec(lines[i]);
    if (!marker || indentOf(marker[1]) !== baseIndent || /\d/.test(marker[2]) !== ordered) break;
    const contentIndent = baseIndent + marker[2].length + 1;
    const body: string[] = [marker[3]];
    i++;
    while (i < lines.length) {
      const line = lines[i];
      if (isBlank(line)) {
        // A blank line continues the item only if what follows is indented into it.
        const next = lines[i + 1];
        if (next !== undefined && !isBlank(next) && indentOf(next) > baseIndent) {
          body.push("");
          i++;
          continue;
        }
        break;
      }
      const indent = indentOf(line);
      if (indent > baseIndent) {
        body.push(line.slice(Math.min(indent, contentIndent)));
      } else if (!startsBlock(lines, i)) {
        body.push(line.trim()); // lazy continuation of the item's text
      } else {
        break;
      }
      i++;
    }
    items.push({
      number: ordered ? Number.parseInt(marker[2], 10) : undefined,
      children: parseBlocks(body),
    });
    // Blank lines between two items of the same list do not end it.
    let peek = i;
    while (peek < lines.length && isBlank(lines[peek])) peek++;
    const again = peek < lines.length ? LIST_ITEM.exec(lines[peek]) : null;
    if (again && indentOf(again[1]) === baseIndent && /\d/.test(again[2]) === ordered) i = peek;
  }
  return [{ type: "list", ordered, items }, i];
}

/** Split a table row on `|`, ignoring escaped pipes and pipes inside code spans. */
function splitRow(line: string): string[] {
  let row = line.trim();
  if (row.startsWith("|")) row = row.slice(1);
  if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
  const cells: string[] = [];
  let current = "";
  let inCode = false;
  for (let k = 0; k < row.length; k++) {
    const ch = row[k];
    if (ch === "\\" && row[k + 1] === "|") {
      current += "|";
      k++;
    } else if (ch === "`") {
      inCode = !inCode;
      current += ch;
    } else if (ch === "|" && !inCode) {
      cells.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  cells.push(current.trim());
  return cells;
}

function parseTable(lines: string[], start: number): [Block, number] {
  const headerCells = splitRow(lines[start]);
  const align: Align[] = splitRow(lines[start + 1]).map((cell) => {
    const left = cell.startsWith(":");
    const right = cell.endsWith(":");
    return left && right ? "center" : right ? "right" : left ? "left" : null;
  });
  const width = headerCells.length;
  const rawRows: string[][] = [];
  let i = start + 2;
  while (i < lines.length && !isBlank(lines[i]) && lines[i].includes("|")) {
    const cells = splitRow(lines[i++]);
    // Pad short rows; keep the extra cells of long ones rather than lose text.
    while (cells.length < width) cells.push("");
    rawRows.push(cells);
  }
  const columns = Math.max(width, ...rawRows.map((row) => row.length));
  while (headerCells.length < columns) headerCells.push("");
  const numeric = Array.from({ length: columns }, (_, column) => {
    const values = rawRows.map((row) => row[column] ?? "").filter((cell) => cell !== "");
    return (
      values.length > 0 &&
      values.every((cell) =>
        NUMERIC_CELL.test(cell.replace(/[*_~`]/g, "").replace(/^\[UNVERIFIED: /, "")),
      )
    );
  });
  return [
    {
      type: "table",
      align: Array.from({ length: columns }, (_, column) => align[column] ?? null),
      header: headerCells.map(parseInline),
      rows: rawRows.map((row) =>
        Array.from({ length: columns }, (_, column) => parseInline(row[column] ?? "")),
      ),
      numeric,
    },
    i,
  ];
}

const WORD = /[\p{L}\p{N}]/u;
const SAFE_HREF = /^(https?:\/\/|mailto:)/i;

/** Parse inline Markdown. Every character that is not syntax is kept. */
export function parseInline(source: string): Inline[] {
  const out: Inline[] = [];
  let text = "";
  const flush = () => {
    if (text) out.push({ type: "text", text });
    text = "";
  };
  let i = 0;

  while (i < source.length) {
    const ch = source[i];

    if (ch === "\\" && i + 1 < source.length && /[\\`*_~[\]()#|>!-]/.test(source[i + 1])) {
      text += source[i + 1];
      i += 2;
      continue;
    }

    if (ch === "\n") {
      flush();
      out.push({ type: "br" });
      i++;
      continue;
    }

    if (ch === "[") {
      FLAG.lastIndex = i;
      const flag = FLAG.exec(source);
      if (flag) {
        flush();
        out.push({ type: "flag", text: flag[0] });
        i += flag[0].length;
        continue;
      }
      const link = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(source.slice(i));
      if (link && SAFE_HREF.test(link[2])) {
        flush();
        out.push({ type: "link", href: link[2], children: parseInline(link[1]) });
        i += link[0].length;
        continue;
      }
    }

    if (ch === "`") {
      const run = /^`+/.exec(source.slice(i))![0];
      const close = source.indexOf(run, i + run.length);
      if (close !== -1) {
        flush();
        out.push({ type: "code", text: source.slice(i + run.length, close).trim() || " " });
        i = close + run.length;
        continue;
      }
      text += run;
      i += run.length;
      continue;
    }

    const emphasis = matchEmphasis(source, i);
    if (emphasis) {
      flush();
      out.push({ type: emphasis.type, children: parseInline(emphasis.inner) });
      i = emphasis.end;
      continue;
    }

    text += ch;
    i++;
  }
  flush();
  return out;
}

/**
 * Emphasis opening at `i`, if it has a matching closer. Openers must be
 * followed by a non-space and closers preceded by one; `_` delimiters must
 * also sit at word boundaries so snake_case identifiers stay intact.
 */
function matchEmphasis(
  source: string,
  i: number,
): { type: "strong" | "em" | "del"; inner: string; end: number } | null {
  const candidates: { delim: string; type: "strong" | "em" | "del" }[] = [
    { delim: "***", type: "strong" },
    { delim: "**", type: "strong" },
    { delim: "__", type: "strong" },
    { delim: "~~", type: "del" },
    { delim: "*", type: "em" },
    { delim: "_", type: "em" },
  ];
  for (const { delim, type } of candidates) {
    if (!source.startsWith(delim, i)) continue;
    const after = source[i + delim.length];
    if (after === undefined || /\s/.test(after)) continue;
    const underscore = delim[0] === "_";
    if (underscore && i > 0 && WORD.test(source[i - 1])) continue;

    let search = i + delim.length;
    while (search < source.length) {
      const close = source.indexOf(delim, search);
      if (close === -1) break;
      const before = source[close - 1];
      const next = source[close + delim.length];
      const validClose =
        close > i + delim.length &&
        !/\s/.test(before) &&
        before !== "\\" &&
        // A single `*` must not close on half of a `**`.
        !(delim === "*" && (next === "*" || before === "*")) &&
        !(underscore && next !== undefined && WORD.test(next));
      if (validClose) {
        const inner = source.slice(i + delim.length, close);
        if (inner.includes("\n\n")) break;
        // `***x***` is bold wrapping italics.
        if (delim === "***") {
          return { type, inner: `*${inner}*`, end: close + delim.length };
        }
        return { type, inner, end: close + delim.length };
      }
      search = close + 1;
    }
  }
  return null;
}
