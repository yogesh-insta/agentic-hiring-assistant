export interface TokenEvent {
  event: "token";
  text: string;
}

export interface Brief {
  role: string;
  location: string;
  hours: string;
  pay: string;
}

export interface DoneEvent {
  event: "done";
  text: string;
  messageId: string;
  brief?: Brief;
}

export interface ErrorEvent {
  event: "error";
  failureClass: string;
}

export type ChatEvent = TokenEvent | DoneEvent | ErrorEvent;

export interface View {
  draft: string;
  committed: string | null;
  error: string | null;
  streaming: boolean;
}

export function emptyView(): View {
  return { draft: "", committed: null, error: null, streaming: false };
}

export function reduce(view: View, event: ChatEvent): View {
  if (event.event === "token") {
    return { draft: view.draft + event.text, committed: null, error: null, streaming: true };
  }
  if (event.event === "done") {
    return { draft: event.text, committed: event.text, error: null, streaming: false };
  }
  return { draft: view.draft, committed: view.committed, error: event.failureClass, streaming: false };
}

export function parseSSE(buffer: string): { events: ChatEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: ChatEvent[] = [];
  for (const part of parts) {
    const parsed = parseBlock(part);
    if (parsed) {
      events.push(parsed);
    }
  }
  return { events, rest };
}

export function briefFromDone(event: ChatEvent): Brief | null {
  if (event.event !== "done" || !event.brief) {
    return null;
  }
  return event.brief;
}

function isBrief(value: unknown): value is Brief {
  if (!value || typeof value !== "object") {
    return false;
  }
  const brief = value as Record<string, unknown>;
  return ["role", "location", "hours", "pay"].every((key) => typeof brief[key] === "string" && brief[key] !== "");
}

function parseBlock(block: string): ChatEvent | null {
  let name = "";
  let dataLine = "";
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      name = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLine = line.slice("data:".length).trim();
    }
  }
  if (!name || !dataLine) {
    return null;
  }
  const data = JSON.parse(dataLine) as Record<string, unknown>;
  if ("functionCall" in data) {
    return null;
  }
  if (name === "token" && typeof data.text === "string") {
    return { event: "token", text: data.text };
  }
  if (name === "done" && typeof data.text === "string" && typeof data.messageId === "string") {
    const done: DoneEvent = { event: "done", text: data.text, messageId: data.messageId };
    if (isBrief(data.brief)) {
      done.brief = data.brief;
    }
    return done;
  }
  if (name === "error" && typeof data.failureClass === "string") {
    return { event: "error", failureClass: data.failureClass };
  }
  return null;
}
