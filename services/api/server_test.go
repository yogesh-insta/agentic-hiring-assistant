package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

func TestCandidateCannotApprove(t *testing.T) {
	api := testAPI(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("candidate approval must not call the agent service")
	}))
	session, csrf := login(t, api, "avery@example.com")
	response := post(t, api, "/approvals/anything/approve", session, csrf, `{}`)
	if response.StatusCode != http.StatusForbidden {
		t.Fatalf("status %d", response.StatusCode)
	}
	body := readBody(t, response)
	if !strings.Contains(body, "policy_denied") {
		t.Fatalf("body %s", body)
	}
}

func TestHirerCookieCannotExecute(t *testing.T) {
	api := testAPI(t, nil)
	session, csrf := login(t, api, "hirer@example.com")
	request := httptest.NewRequest(http.MethodPost, "/execute/email.send", strings.NewReader(`{}`))
	request.AddCookie(&http.Cookie{Name: "session", Value: session})
	request.AddCookie(&http.Cookie{Name: "csrf", Value: csrf})
	request.Header.Set("X-CSRF-Token", csrf)
	response := httptest.NewRecorder()
	api.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("cookie status %d", response.Code)
	}

	workflow := httptest.NewRequest(http.MethodPost, "/execute/email.send", strings.NewReader(`{}`))
	workflow.Header.Set("Authorization", "Bearer local-workflow")
	workflowResponse := httptest.NewRecorder()
	api.Handler().ServeHTTP(workflowResponse, workflow)
	if workflowResponse.Code != http.StatusConflict {
		t.Fatalf("workflow status %d body %s", workflowResponse.Code, workflowResponse.Body.String())
	}
}

func TestChatDoesNotStartAHireAndReplacesTokens(t *testing.T) {
	var hits int
	var mu sync.Mutex
	var paths []string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		hits++
		paths = append(paths, r.URL.Path)
		mu.Unlock()
		if r.URL.Path == "/v1/workflows" {
			w.Header().Set("Content-Type", "application/json")
			_, _ = io.WriteString(w, `{"id":"w1","step":"ad_reviewed","sent":false}`)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = io.WriteString(w, "event: token\ndata: {\"text\":\"Hello \"}\n\n")
		_, _ = io.WriteString(w, "event: token\ndata: {\"functionCall\":{\"name\":\"email.send\"}}\n\n")
		_, _ = io.WriteString(w, "event: token\ndata: {\"text\":\"there\"}\n\n")
		_, _ = io.WriteString(w, "event: done\ndata: {\"messageId\":\"m1\",\"text\":\"Hello there\"}\n\n")
	}))
	defer upstream.Close()
	api := NewServer(Config{Env: "local", AgentsURL: upstream.URL, WebDir: t.TempDir(), WorkflowToken: "local-workflow"})
	session, csrf := login(t, api, "hirer@example.com")

	first := post(t, api, "/sessions/"+session+"/messages", session, csrf, `{"messageId":"m1","text":"I need a barista"}`)
	if first.StatusCode != http.StatusOK {
		t.Fatalf("status %d", first.StatusCode)
	}
	stream := readBody(t, first)
	if strings.Contains(stream, "functionCall") || strings.Contains(stream, "email.send") {
		t.Fatalf("function call leaked: %s", stream)
	}
	if !strings.Contains(stream, "event: token") || !strings.Contains(stream, "event: done") {
		t.Fatalf("stream %s", stream)
	}
	if !strings.Contains(stream, "Hello there") {
		t.Fatalf("done text missing: %s", stream)
	}

	second := post(t, api, "/sessions/"+session+"/messages", session, csrf, `{"messageId":"m1","text":"I need a barista"}`)
	retry := readBody(t, second)
	if strings.Contains(retry, "event: token") {
		t.Fatalf("retry streamed tokens again: %s", retry)
	}
	mu.Lock()
	if hits != 1 {
		t.Fatalf("upstream hits %d", hits)
	}
	for _, path := range paths {
		if path != "/v1/turns" {
			t.Fatalf("chat called %s", path)
		}
	}
	mu.Unlock()

	start := post(t, api, "/workflows", session, csrf, `{"brief":{"role":"barista","location":"Fitzroy","hours":"weekends, part-time","pay":"about $32 an hour"}}`)
	startBody := readBody(t, start)
	if start.StatusCode != http.StatusOK {
		t.Fatalf("workflow status %d body %s", start.StatusCode, startBody)
	}
	if !strings.Contains(startBody, "ad_reviewed") {
		t.Fatalf("confirm did not return the waiting step: %s", startBody)
	}
}

func TestApproveUsesTheWorkflowTokenToSend(t *testing.T) {
	var executeAuth string
	api := testAPI(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/v1/approvals/a1/approve":
			_, _ = io.WriteString(w, `{"id":"w1","pendingExecute":["email.send"]}`)
		case "/v1/execute/email.send":
			executeAuth = r.Header.Get("Authorization")
			_, _ = io.WriteString(w, `{"ok":true}`)
		case "/v1/workflows/w1":
			_, _ = io.WriteString(w, `{"id":"w1","step":"completed","pendingExecute":[]}`)
		default:
			t.Fatalf("path %s", r.URL.Path)
		}
	}))
	session, csrf := login(t, api, "hirer@example.com")
	response := post(t, api, "/approvals/a1/approve", session, csrf, `{}`)
	body := readBody(t, response)
	if response.StatusCode != http.StatusOK {
		t.Fatalf("status %d body %s", response.StatusCode, body)
	}
	if executeAuth != "Bearer local-workflow" {
		t.Fatalf("execute auth %q", executeAuth)
	}
	if !strings.Contains(body, "completed") {
		t.Fatalf("body %s", body)
	}
}

func TestForgedCallbackDoesNotReachTheAgent(t *testing.T) {
	api := testAPI(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("forged callback must not call the agent service")
	}))
	api.cfg.CallbackToken = "local-api"
	session, csrf := login(t, api, "hirer@example.com")
	response := post(t, api, "/callbacks/secret", session, csrf, `{"decision":"approve"}`)
	if response.StatusCode != http.StatusForbidden {
		t.Fatalf("cookie status %d", response.StatusCode)
	}

	forged := httptest.NewRequest(http.MethodPost, "/callbacks/secret", strings.NewReader(`{}`))
	forged.Header.Set("Authorization", "Bearer wrong")
	forgedResponse := httptest.NewRecorder()
	api.Handler().ServeHTTP(forgedResponse, forged)
	if forgedResponse.Code != http.StatusForbidden {
		t.Fatalf("bearer status %d", forgedResponse.Code)
	}
}

func TestApiServiceAccountCanSendTheCallback(t *testing.T) {
	var auth string
	api := testAPI(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"accepted":true,"workflowId":"w1"}`)
	}))
	api.cfg.CallbackToken = "local-api"
	request := httptest.NewRequest(http.MethodPost, "/callbacks/secret", strings.NewReader(`{"decision":"approve"}`))
	request.Header.Set("Authorization", "Bearer local-api")
	response := httptest.NewRecorder()
	api.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status %d body %s", response.Code, response.Body.String())
	}
	if auth != "Bearer local-api" {
		t.Fatalf("auth %q", auth)
	}
	if strings.Contains(response.Body.String(), "http://") || strings.Contains(response.Body.String(), "https://") {
		t.Fatalf("callback url returned %s", response.Body.String())
	}
}

func TestSeedLoginIsAbsentOutsideLocal(t *testing.T) {
	api := NewServer(Config{Env: "cloud", AgentsURL: "http://127.0.0.1:9", WebDir: t.TempDir(), WorkflowToken: "local-workflow"})
	request := httptest.NewRequest(http.MethodPost, "/sessions", strings.NewReader(`{"email":"hirer@example.com"}`))
	response := httptest.NewRecorder()
	api.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusNotFound {
		t.Fatalf("status %d", response.Code)
	}
}

func TestClaimedRoleCannotGrantHirer(t *testing.T) {
	allow := map[string]string{"avery@example.com": "candidate"}
	_, err := principalFromClaims(idClaims{
		Issuer:        "https://securetoken.google.com/demo",
		Audience:      "demo",
		ExpiresAt:     200,
		Email:         "avery@example.com",
		EmailVerified: true,
		ClaimedRole:   "hirer",
	}, 100, "demo", allow)
	if err == nil {
		t.Fatal("client role claim was accepted")
	}
	person, err := principalFromClaims(idClaims{
		Issuer:        "https://securetoken.google.com/demo",
		Audience:      "demo",
		ExpiresAt:     200,
		Email:         "hirer@example.com",
		EmailVerified: true,
	}, 100, "demo", map[string]string{"hirer@example.com": "hirer"})
	if err != nil || person.Role != "hirer" {
		t.Fatalf("allowlist principal %v %v", person, err)
	}
}

func TestCandidateCannotSendChat(t *testing.T) {
	api := testAPI(t, nil)
	session, csrf := login(t, api, "avery@example.com")
	response := post(t, api, "/sessions/"+session+"/messages", session, csrf, `{"messageId":"m1","text":"hello"}`)
	if response.StatusCode != http.StatusForbidden {
		t.Fatalf("status %d", response.StatusCode)
	}
}

func testAPI(t *testing.T, upstream http.Handler) *Server {
	t.Helper()
	if upstream == nil {
		upstream = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			t.Fatal("unexpected upstream call")
		})
	}
	backend := httptest.NewServer(upstream)
	t.Cleanup(backend.Close)
	return NewServer(Config{Env: "local", AgentsURL: backend.URL, WebDir: t.TempDir(), WorkflowToken: "local-workflow"})
}

func login(t *testing.T, api *Server, email string) (string, string) {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, "/sessions", strings.NewReader(`{"email":"`+email+`"}`))
	response := httptest.NewRecorder()
	api.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("login %d %s", response.Code, response.Body.String())
	}
	var sessionCookie, csrfCookie string
	for _, cookie := range response.Result().Cookies() {
		if cookie.Name == "session" {
			sessionCookie = cookie.Value
			if !cookie.HttpOnly {
				t.Fatal("session cookie must be httpOnly")
			}
		}
		if cookie.Name == "csrf" {
			csrfCookie = cookie.Value
		}
	}
	if sessionCookie == "" || csrfCookie == "" {
		t.Fatal("missing cookies")
	}
	return sessionCookie, csrfCookie
}

func post(t *testing.T, api *Server, path, session, csrf, body string) *http.Response {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
	request.AddCookie(&http.Cookie{Name: "session", Value: session})
	request.AddCookie(&http.Cookie{Name: "csrf", Value: csrf})
	request.Header.Set("X-CSRF-Token", csrf)
	response := httptest.NewRecorder()
	api.Handler().ServeHTTP(response, request)
	return response.Result()
}

func readBody(t *testing.T, response *http.Response) string {
	t.Helper()
	defer response.Body.Close()
	raw, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}
