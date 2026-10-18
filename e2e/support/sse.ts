export interface SseFrame {
  event: string;
  data: string;
  id?: string;
}

export interface SseResult {
  status: number;
  contentType: string | null;
  frames: SseFrame[];
  /** true if the server closed the stream (as opposed to us aborting after `timeoutMs`). */
  closedByServer: boolean;
}

/** Parses a text/event-stream body (https://html.spec.whatwg.org/multipage/server-sent-events.html). */
export function parseSse(text: string): SseFrame[] {
  const frames: SseFrame[] = [];
  for (const block of text.replace(/\r\n?/g, "\n").split("\n\n")) {
    let event = "message";
    let id: string | undefined;
    const data: string[] = [];
    let hasField = false;
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      const idx = line.indexOf(":");
      const field = idx === -1 ? line : line.slice(0, idx);
      const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
      hasField = true;
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
      else if (field === "id") id = value;
    }
    if (hasField && data.length) frames.push({ event, data: data.join("\n"), id });
  }
  return frames;
}

/** Reads an SSE endpoint until the server closes it or `timeoutMs` elapses. */
export async function readSse(url: string, timeoutMs = 20_000): Promise<SseResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let text = "";
  let closedByServer = false;
  const res = await fetch(url, { headers: { Accept: "text/event-stream" }, signal: controller.signal });
  try {
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        closedByServer = true;
        break;
      }
      text += decoder.decode(value, { stream: true });
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") throw err;
  } finally {
    clearTimeout(timer);
  }
  return { status: res.status, contentType: res.headers.get("content-type"), frames: parseSse(text), closedByServer };
}
