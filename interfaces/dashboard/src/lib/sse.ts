/**
 * A minimal Server-Sent Events frame parser for `POST /chat/stream`.
 *
 * `EventSource` cannot send a POST body, so the chat stream is read with
 * `fetch` and parsed here. Only what the API emits is supported: named events
 * (`event:`) with a single- or multi-line `data:` payload.
 */

export interface SseFrame {
  event: string;
  data: string;
}

/**
 * Split buffered stream text into complete frames.
 *
 * @returns The complete frames, and the unterminated tail to prepend to the
 *   next chunk.
 */
export function parseSseFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const normalized = buffer.replace(/\r\n?/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const frames: SseFrame[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length > 0) frames.push({ event, data: data.join("\n") });
  }
  return { frames, rest };
}
