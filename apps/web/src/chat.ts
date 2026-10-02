import { briefFromDone, emptyView, parseSSE, reduce, type Brief, type View } from "./stream.js";

const live = document.querySelector("#live") as HTMLElement;
const transcript = document.querySelector("#transcript") as HTMLOListElement;
const form = document.querySelector("#composer") as HTMLFormElement;
const field = document.querySelector("#message") as HTMLTextAreaElement;
const send = document.querySelector("#send") as HTMLButtonElement;
const signIn = document.querySelector("#sign-hirer") as HTMLButtonElement;
const panelStatus = document.querySelector("#panel-status") as HTMLElement;
const panelActions = document.querySelector("#panel-actions") as HTMLElement;
const panelAd = document.querySelector("#panel-ad") as HTMLElement;

let sessionId = "";
let csrfToken = "";
let streaming = false;
let authMode = "local";
let googleClientId = "";

try {
  const configResponse = await fetch("/config");
  if (configResponse.ok) {
    const config = (await configResponse.json()) as { mode?: string; googleClientId?: string };
    authMode = config.mode || "local";
    googleClientId = config.googleClientId || "";
  }
} catch {
  authMode = "local";
}
if (authMode !== "local") {
  signIn.textContent = "Sign in with Google";
}

signIn.addEventListener("click", async () => {
  if (authMode !== "local") {
    await signInWithGoogle(googleClientId);
    return;
  }
  const response = await fetch("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "hirer@example.com" }),
  });
  if (!response.ok) {
    live.textContent = "Sign-in failed";
    return;
  }
  const body = (await response.json()) as { sessionId: string; csrfToken: string };
  sessionId = body.sessionId;
  csrfToken = body.csrfToken;
  field.disabled = false;
  send.disabled = false;
  live.textContent = "Signed in as hirer";
});

field.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = field.value.trim();
  if (!text || !sessionId || streaming) {
    return;
  }
  field.value = "";
  streaming = true;
  send.disabled = true;
  field.disabled = true;
  append("hirer", text);
  const pending = append("assistant", "");
  let view: View = emptyView();
  live.textContent = "Receiving reply";
  try {
    const response = await fetch("/sessions/" + sessionId + "/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({ messageId: crypto.randomUUID(), text }),
    });
    if (!response.ok || !response.body) {
      live.textContent = "The reply failed";
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let rest = "";
    while (true) {
      const chunk = await reader.read();
      rest += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
      const parsed = parseSSE(rest + (chunk.done ? "\n\n" : ""));
      rest = parsed.rest;
      for (const item of parsed.events) {
        view = reduce(view, item);
        pending.textContent = view.draft;
        if (item.event === "token") {
          await nextFrame();
        }
        if (item.event === "error") {
          live.textContent = item.failureClass;
        }
        const brief = briefFromDone(item);
        if (brief) {
          showConfirm(brief);
        }
      }
      if (chunk.done) {
        break;
      }
    }
    if (view.committed !== null) {
      pending.textContent = view.committed;
      live.textContent = "Reply ready";
    }
  } finally {
    streaming = false;
    send.disabled = false;
    field.disabled = false;
    field.focus();
  }
});

function append(role: string, text: string): HTMLElement {
  const item = document.createElement("li");
  item.dataset.role = role;
  item.textContent = text;
  transcript.append(item);
  return item;
}

function showConfirm(brief: Brief): void {
  panelStatus.textContent = "Confirm the brief to draft an ad. This button starts the hire. The chat message did not.";
  panelActions.replaceChildren();
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Confirm brief";
  button.addEventListener("click", () => startHire(brief, button));
  panelActions.append(button);
}

async function startHire(brief: Brief, button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  const response = await fetch("/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ brief }),
  });
  if (!response.ok) {
    panelStatus.textContent = "The hire did not start";
    button.disabled = false;
    return;
  }
  renderWorkflow(await response.json());
}

function renderWorkflow(workflow: WorkflowView): void {
  panelActions.replaceChildren();
  panelAd.hidden = false;
  panelAd.textContent = describe(workflow);
  if (workflow.step === "completed") {
    panelStatus.textContent = "Hire recorded. The welcome email was sent.";
    return;
  }
  if (workflow.step === "onboarding_proposed") {
    panelStatus.textContent = "Approve the welcome email. Nothing is sent until you do.";
    addDecision(workflow, "Approve welcome email");
    return;
  }
  if (workflow.step === "interviews_scheduled") {
    panelStatus.textContent = "One interview is scheduled. The other approved candidates are not. Avery accepts on the candidate page.";
    const record = document.createElement("button");
    record.type = "button";
    record.textContent = "Record hire";
    record.addEventListener("click", () => continueHire(workflow.id, "record_hire", record));
    panelActions.append(record);
    return;
  }
  if (workflow.step === "schedule_proposed") {
    panelStatus.textContent = "Approve the invite for one candidate. The others stay approved and unscheduled. Nothing is sent until you approve.";
    addDecision(workflow, "Approve invites");
    return;
  }
  if (workflow.step === "shortlist_proposed") {
    panelStatus.textContent = workflow.disclaimer;
    addDecision(workflow, "Approve three", candidateIds(workflow));
    return;
  }
  if (workflow.step === "published") {
    panelStatus.textContent = workflow.applicationCount > 0 ? workflow.disclaimer : "Published. Load the synthetic CVs next.";
    const load = document.createElement("button");
    load.type = "button";
    load.textContent = "Load synthetic CVs";
    load.addEventListener("click", () => seed(workflow.id, load));
    panelActions.append(load);
    if (workflow.applicationCount > 0) {
      const shortlist = document.createElement("button");
      shortlist.type = "button";
      shortlist.textContent = "Shortlist";
      shortlist.addEventListener("click", () => continueHire(workflow.id, "shortlist", shortlist));
      panelActions.append(shortlist);
    }
    return;
  }
  if (workflow.artifact.kind === "job_ad" && workflow.artifact.status === "approved") {
    panelStatus.textContent = "Ad approved. Nothing was sent.";
    const publish = document.createElement("button");
    publish.type = "button";
    publish.textContent = "Publish ad";
    publish.addEventListener("click", () => continueHire(workflow.id, "publish", publish));
    panelActions.append(publish);
    return;
  }
  if (workflow.manualEdit) {
    panelStatus.textContent = "Three revisions are used. Edit the ad by hand, or accept this draft. Nothing was sent.";
  } else {
    panelStatus.textContent = "Draft is ready. Accept or reject it here. Typed text does not decide.";
  }
  addDecision(workflow, "Accept ad");
}

function describe(workflow: WorkflowView): string {
  const draft = workflow.artifact.draft;
  if (workflow.artifact.kind === "shortlist") {
    return (draft.candidates ?? [])
      .map((candidate) => candidate.id + " band " + candidate.band + " (" + candidate.evidence + ")")
      .join("\n");
  }
  if (workflow.artifact.kind === "schedule") {
    return "Scheduled: " + draft.scheduled + "\nNot scheduled: " + (draft.unscheduled ?? []).join(", ") + "\n" + draft.emailDraft;
  }
  if (workflow.artifact.kind === "onboarding") {
    return draft.emailDraft ?? "";
  }
  const issues = workflow.artifact.review.issues.map((issue) => issue.phrase || issue.kind).filter((item) => item !== "");
  return [draft.title, draft.location, draft.pay, draft.hours, draft.body, issues.join("; ")].filter((item): item is string => Boolean(item)).join("\n");
}

function candidateIds(workflow: WorkflowView): string[] {
  return (workflow.artifact.draft.candidates ?? []).map((candidate) => candidate.id);
}

function addDecision(workflow: WorkflowView, label: string, ids?: string[]): void {
  const accept = document.createElement("button");
  accept.type = "button";
  accept.textContent = label;
  accept.addEventListener("click", () => decide(workflow.id, workflow.approvalId, "approve", accept, "", ids));
  const note = document.createElement("input");
  note.type = "text";
  note.placeholder = "Reject note";
  note.setAttribute("aria-label", "Reject note");
  const reject = document.createElement("button");
  reject.type = "button";
  reject.textContent = "Reject";
  reject.addEventListener("click", () => decide(workflow.id, workflow.approvalId, "reject", reject, note.value));
  panelActions.append(accept, note, reject);
}

async function continueHire(workflowId: string, action: string, button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  const response = await fetch("/workflows/" + workflowId + "/continue", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ action }),
  });
  if (!response.ok) {
    panelStatus.textContent = "That step was not taken";
    button.disabled = false;
    return;
  }
  renderWorkflow(await response.json());
}

async function seed(workflowId: string, button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  const response = await fetch("/workflows/" + workflowId + "/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: "{}",
  });
  if (!response.ok) {
    panelStatus.textContent = "The CVs were not loaded";
    button.disabled = false;
    return;
  }
  renderWorkflow(await response.json());
}

async function decide(workflowId: string, approvalId: string, action: "approve" | "reject", button: HTMLButtonElement, note = "", ids?: string[]): Promise<void> {
  button.disabled = true;
  const payload = action === "reject" ? { note, workflowId } : { candidateIds: ids ?? [], workflowId };
  const response = await fetch("/approvals/" + approvalId + "/" + action, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    panelStatus.textContent = "The decision was not recorded";
    button.disabled = false;
    return;
  }
  renderWorkflow(await response.json());
}

interface WorkflowView {
  id: string;
  step: string;
  approvalId: string;
  manualEdit: boolean;
  applicationCount: number;
  disclaimer: string;
  artifact: {
    kind: string;
    status: string;
    draft: {
      title?: string;
      location?: string;
      pay?: string;
      hours?: string;
      body?: string;
      emailDraft?: string;
      scheduled?: string;
      unscheduled?: string[];
      candidates?: { id: string; band: number; evidence: string }[];
    };
    review: { issues: { phrase: string; kind: string; blocking: boolean }[] };
  };
}

async function signInWithGoogle(clientId: string): Promise<void> {
  if (!clientId) {
    live.textContent = "Google sign-in is not configured";
    return;
  }
  await loadGoogleScript();
  const google = (window as unknown as { google: GoogleIdentity }).google;
  google.accounts.id.initialize({
    client_id: clientId,
    callback: async (response) => {
      const result = await fetch("/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idToken: response.credential }),
      });
      if (!result.ok) {
        live.textContent = "Sign-in failed";
        return;
      }
      const body = (await result.json()) as { sessionId: string; csrfToken: string };
      sessionId = body.sessionId;
      csrfToken = body.csrfToken;
      field.disabled = false;
      send.disabled = false;
      live.textContent = "Signed in";
    },
  });
  google.accounts.id.prompt();
}

function loadGoogleScript(): Promise<void> {
  return new Promise((resolve) => {
    if ((window as unknown as { google?: GoogleIdentity }).google) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => resolve();
    document.head.append(script);
  });
}

interface GoogleIdentity {
  accounts: { id: { initialize: (config: { client_id: string; callback: (response: { credential: string }) => void }) => void; prompt: () => void } };
}

function nextFrame(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}
