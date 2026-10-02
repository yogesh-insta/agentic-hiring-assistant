const live = document.querySelector("#live") as HTMLElement;
const accept = document.querySelector("#accept") as HTMLButtonElement;
const decline = document.querySelector("#decline") as HTMLButtonElement;
const signIn = document.querySelector("#sign-candidate") as HTMLButtonElement;

let csrfToken = "";
let interviewId = "";

let mode = "local";
let clientId = "";
try {
  const config = await fetch("/config");
  if (config.ok) {
    const body = (await config.json()) as { mode?: string; googleClientId?: string };
    mode = body.mode || "local";
    clientId = body.googleClientId || "";
  }
} catch {
  mode = "local";
}

if (mode === "local") {
  await signInAs("avery@example.com");
} else {
  signIn.hidden = false;
  live.textContent = "Sign in with Google to open your interview.";
  signIn.addEventListener("click", () => {
    void signInWithGoogle(clientId);
  });
}

accept.addEventListener("click", () => respond("accept"));
decline.addEventListener("click", () => respond("decline"));

async function signInAs(email: string): Promise<void> {
  const response = await fetch("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!response.ok) {
    live.textContent = "Sign-in failed";
    return;
  }
  const body = (await response.json()) as { csrfToken: string };
  csrfToken = body.csrfToken;
  await loadInterview();
}

async function loadInterview(): Promise<void> {
  const mine = await fetch("/interviews/mine", { headers: { "X-CSRF-Token": csrfToken } });
  if (!mine.ok) {
    live.textContent = "Signed in. No interview is scheduled yet.";
    return;
  }
  const interview = (await mine.json()) as { id: string; when: string };
  interviewId = interview.id;
  live.textContent = "Signed in. Interview " + interview.when;
  accept.disabled = false;
  decline.disabled = false;
}

async function signInWithGoogle(googleClientId: string): Promise<void> {
  if (!googleClientId) {
    live.textContent = "Google sign-in is not configured";
    return;
  }
  await loadGoogleScript();
  const google = (window as unknown as { google: GoogleIdentity }).google;
  google.accounts.id.initialize({
    client_id: googleClientId,
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
      const body = (await result.json()) as { csrfToken: string };
      csrfToken = body.csrfToken;
      await loadInterview();
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

async function respond(decision: string): Promise<void> {
  const result = await fetch("/interviews/" + interviewId + "/respond", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ decision }),
  });
  const payload = (await result.json()) as { status?: string; failureClass?: string };
  live.textContent = payload.status || payload.failureClass || "Interview update failed";
}
