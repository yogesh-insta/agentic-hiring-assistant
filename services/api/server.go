package main

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type Config struct {
	Env              string
	AgentsURL        string
	WebDir           string
	WorkflowToken    string
	CallbackToken    string
	SessionSecret    string
	ProjectID        string
	WorkflowName     string
	WorkflowLocation string
	HirerEmail       string
	CandidateEmail   string
	GoogleClientID   string
}

type principal struct {
	Email         string `json:"email"`
	Role          string `json:"role"`
	ApplicationID string `json:"applicationId,omitempty"`
}

type chatMessage struct {
	ID   string `json:"id"`
	Role string `json:"role"`
	Text string `json:"text"`
}

type Server struct {
	cfg              Config
	turnClient       *http.Client
	pipelineClient   *http.Client
	mu               sync.Mutex
	sessions         map[string]principal
	csrf             map[string]string
	messages         map[string][]chatMessage
	replies          map[string]map[string]any
	localUsers       map[string]principal
	startExecutionFn func(workflowID string, brief map[string]any) error
	postCallbackFn   func(url string, body []byte) error
}

func NewServer(cfg Config) *Server {
	return &Server{
		cfg:            cfg,
		turnClient:     &http.Client{Timeout: 60 * time.Second},
		pipelineClient: &http.Client{Timeout: 200 * time.Second},
		sessions:       map[string]principal{},
		csrf:           map[string]string{},
		messages:       map[string][]chatMessage{},
		replies:        map[string]map[string]any{},
		localUsers: map[string]principal{
			"hirer@example.com": {Email: "hirer@example.com", Role: "hirer"},
			"avery@example.com": {Email: "avery@example.com", Role: "candidate", ApplicationID: "app-avery"},
		},
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
	})
	mux.HandleFunc("GET /config", s.handleConfig)
	mux.HandleFunc("POST /sessions", s.handleLogin)
	mux.HandleFunc("POST /sessions/{id}/messages", s.handlePostMessage)
	mux.HandleFunc("GET /sessions/{id}/messages", s.handleGetMessages)
	mux.HandleFunc("POST /workflows", s.handleStartWorkflow)
	mux.HandleFunc("GET /workflows/{id}", s.handleGetWorkflow)
	mux.HandleFunc("POST /workflows/{id}/continue", s.handleContinue)
	mux.HandleFunc("POST /workflows/{id}/applications", s.handleSeed)
	mux.HandleFunc("POST /approvals/{id}/approve", s.handleApprove)
	mux.HandleFunc("POST /approvals/{id}/reject", s.handleReject)
	mux.HandleFunc("GET /interviews/mine", s.handleMyInterview)
	mux.HandleFunc("POST /interviews/{id}/respond", s.handleRespond)
	mux.HandleFunc("POST /execute/{name}", s.handleExecute)
	mux.HandleFunc("POST /callbacks/{id}", s.handleCallback)
	mux.HandleFunc("GET /{$}", s.handleIndex)
	mux.HandleFunc("GET /interview", s.handleInterview)
	mux.Handle("GET /dist/", http.StripPrefix("/dist/", http.FileServer(http.Dir(filepath.Join(s.cfg.WebDir, "dist")))))
	return mux
}

func (s *Server) handleConfig(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"mode":           s.cfg.Env,
		"googleClientId": s.cfg.GoogleClientID,
	})
}

func (s *Server) handleLogin(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email   string `json:"email"`
		IDToken string `json:"idToken"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, failure("schema_invalid"))
		return
	}
	var person principal
	if s.cfg.Env == "local" {
		found, ok := s.localUsers[strings.ToLower(strings.TrimSpace(body.Email))]
		if !ok {
			writeJSON(w, http.StatusForbidden, failure("policy_denied"))
			return
		}
		person = found
	} else {
		if body.IDToken == "" {
			http.NotFound(w, r)
			return
		}
		claims, err := verifyIDToken(body.IDToken, s.cfg.ProjectID, time.Now().Unix())
		if err != nil {
			writeJSON(w, http.StatusForbidden, failure("policy_denied"))
			return
		}
		person, err = principalFromClaims(claims, time.Now().Unix(), s.cfg.ProjectID, s.allowlist())
		if err != nil {
			writeJSON(w, http.StatusForbidden, failure("policy_denied"))
			return
		}
		if person.Role == "candidate" {
			person.ApplicationID = "app-avery"
		}
	}
	s.issueSession(w, person)
}

func (s *Server) allowlist() map[string]string {
	out := map[string]string{}
	if s.cfg.HirerEmail != "" {
		out[strings.ToLower(s.cfg.HirerEmail)] = "hirer"
	}
	if s.cfg.CandidateEmail != "" {
		out[strings.ToLower(s.cfg.CandidateEmail)] = "candidate"
	}
	return out
}

func (s *Server) issueSession(w http.ResponseWriter, person principal) {
	csrf := randomID()
	sealed, err := s.seal(person, csrf)
	if err != nil {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return
	}
	secure := s.cfg.Env != "local"
	http.SetCookie(w, &http.Cookie{Name: "session", Value: sealed, Path: "/", HttpOnly: true, Secure: secure, SameSite: http.SameSiteLaxMode})
	http.SetCookie(w, &http.Cookie{Name: "csrf", Value: csrf, Path: "/", HttpOnly: false, Secure: secure, SameSite: http.SameSiteLaxMode})
	writeJSON(w, http.StatusOK, map[string]string{
		"sessionId": sealed,
		"role":      person.Role,
		"email":     person.Email,
		"csrfToken": csrf,
	})
}

func (s *Server) handlePostMessage(w http.ResponseWriter, r *http.Request) {
	_, sessionID, ok := s.authorized(w, r, "hirer")
	if !ok {
		return
	}
	if r.PathValue("id") != sessionID {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return
	}
	var body struct {
		MessageID string `json:"messageId"`
		Text      string `json:"text"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.MessageID) == "" {
		writeJSON(w, http.StatusBadRequest, failure("schema_invalid"))
		return
	}
	key := sessionID + "/" + body.MessageID
	s.mu.Lock()
	if done, found := s.replies[key]; found {
		s.mu.Unlock()
		writeEventStream(w, []sseEvent{{Name: "done", Data: done}})
		return
	}
	s.messages[sessionID] = append(s.messages[sessionID], chatMessage{ID: body.MessageID, Role: "hirer", Text: body.Text})
	s.mu.Unlock()

	events, err := s.upstreamTurn(body.MessageID, body.Text, r.Header.Get("traceparent"))
	if err != nil {
		log.Printf("turn message_id=%s outcome=tool_error", body.MessageID)
		writeEventStream(w, []sseEvent{{Name: "error", Data: map[string]any{"failureClass": "tool_error"}}})
		return
	}
	forward := make([]sseEvent, 0, len(events))
	for _, event := range events {
		if _, isCall := event.Data["functionCall"]; isCall {
			continue
		}
		forward = append(forward, event)
		if event.Name == "done" {
			if text, isString := event.Data["text"].(string); isString {
				s.mu.Lock()
				s.replies[key] = event.Data
				s.messages[sessionID] = append(s.messages[sessionID], chatMessage{ID: body.MessageID + ":assistant", Role: "assistant", Text: text})
				s.mu.Unlock()
			}
		}
	}
	log.Printf("turn message_id=%s outcome=ok", body.MessageID)
	writeEventStream(w, forward)
}

func (s *Server) handleGetMessages(w http.ResponseWriter, r *http.Request) {
	_, sessionID, ok := s.authorized(w, r, "hirer")
	if !ok {
		return
	}
	if r.PathValue("id") != sessionID {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return
	}
	s.mu.Lock()
	messages := append([]chatMessage(nil), s.messages[sessionID]...)
	s.mu.Unlock()
	writeJSON(w, http.StatusOK, map[string]any{"messages": messages})
}

func (s *Server) handleStartWorkflow(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := s.authorized(w, r, "hirer"); !ok {
		return
	}
	if s.cloudWorkflows() {
		s.handleCloudStart(w, r)
		return
	}
	s.forward(w, r, http.MethodPost, "/v1/workflows")
}

func (s *Server) handleGetWorkflow(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := s.authorized(w, r, "hirer"); !ok {
		return
	}
	s.forward(w, r, http.MethodGet, "/v1/workflows/"+r.PathValue("id"))
}

func (s *Server) handleApprove(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := s.authorized(w, r, "hirer"); !ok {
		return
	}
	if s.cloudWorkflows() {
		s.signalButton(w, r, "approve")
		return
	}
	status, raw := s.call(http.MethodPost, "/v1/approvals/"+r.PathValue("id")+"/approve", r.Body, "")
	if status == http.StatusOK {
		var view struct {
			ID             string   `json:"id"`
			PendingExecute []string `json:"pendingExecute"`
		}
		if json.Unmarshal(raw, &view) == nil && len(view.PendingExecute) > 0 {
			for _, name := range view.PendingExecute {
				payload, _ := json.Marshal(map[string]string{"workflowId": view.ID})
				s.call(http.MethodPost, "/v1/execute/"+name, bytes.NewReader(payload), "Bearer "+s.cfg.WorkflowToken)
			}
			status, raw = s.call(http.MethodGet, "/v1/workflows/"+view.ID, nil, "")
		}
	}
	writeRaw(w, status, raw)
}

func (s *Server) handleContinue(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := s.authorized(w, r, "hirer"); !ok {
		return
	}
	if s.cloudWorkflows() {
		s.signalButton(w, r, "continue")
		return
	}
	s.forward(w, r, http.MethodPost, "/v1/workflows/"+r.PathValue("id")+"/continue")
}

func (s *Server) handleSeed(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := s.authorized(w, r, "hirer"); !ok {
		return
	}
	s.forward(w, r, http.MethodPost, "/v1/workflows/"+r.PathValue("id")+"/applications")
}

func (s *Server) handleMyInterview(w http.ResponseWriter, r *http.Request) {
	person, _, ok := s.authorized(w, r, "candidate")
	if !ok {
		return
	}
	status, raw := s.call(http.MethodGet, "/v1/interviews/mine", nil, person.Email)
	writeRaw(w, status, raw)
}

func (s *Server) handleRespond(w http.ResponseWriter, r *http.Request) {
	person, _, ok := s.authorized(w, r, "candidate")
	if !ok {
		return
	}
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, failure("schema_invalid"))
		return
	}
	body := map[string]any{}
	if len(bytes.TrimSpace(raw)) > 0 && json.Unmarshal(raw, &body) != nil {
		writeJSON(w, http.StatusBadRequest, failure("schema_invalid"))
		return
	}
	body["interviewId"] = r.PathValue("id")
	payload, err := json.Marshal(body)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, failure("schema_invalid"))
		return
	}
	status, response := s.call(http.MethodPost, "/v1/interviews/respond", bytes.NewReader(payload), person.Email)
	writeRaw(w, status, response)
}

func (s *Server) handleReject(w http.ResponseWriter, r *http.Request) {
	if _, _, ok := s.authorized(w, r, "hirer"); !ok {
		return
	}
	if s.cloudWorkflows() {
		s.signalButton(w, r, "reject")
		return
	}
	s.forward(w, r, http.MethodPost, "/v1/approvals/"+r.PathValue("id")+"/reject")
}

func (s *Server) signalButton(w http.ResponseWriter, r *http.Request, kind string) {
	body := readJSON(r.Body)
	workflowID, _ := body["workflowId"].(string)
	if workflowID == "" {
		workflowID = r.PathValue("id")
	}
	status, raw := s.call(http.MethodGet, "/v1/workflows/"+workflowID, nil, "")
	if status != http.StatusOK {
		writeRaw(w, status, raw)
		return
	}
	var view map[string]any
	if json.Unmarshal(raw, &view) != nil {
		writeJSON(w, http.StatusBadGateway, failure("tool_error"))
		return
	}
	payload := map[string]any{"decision": kind}
	if kind == "continue" {
		payload = map[string]any{"action": body["action"], "decision": "approve"}
	}
	if ids, ok := body["candidateIds"]; ok {
		payload["candidateIds"] = ids
	}
	if note, ok := body["note"]; ok {
		payload["note"] = note
	}
	encoded, _ := json.Marshal(payload)
	s.signalWorkflow(w, workflowID, purposeFor(view), encoded)
}

func (s *Server) forward(w http.ResponseWriter, r *http.Request, method, path string) {
	status, raw := s.call(method, path, r.Body, "")
	if status == http.StatusBadGateway && raw == nil {
		writeJSON(w, status, failure("tool_error"))
		return
	}
	writeRaw(w, status, raw)
}

func (s *Server) call(method, path string, body io.Reader, actorEmail string) (int, []byte) {
	var payload io.Reader
	if method != http.MethodGet && body != nil {
		raw, err := io.ReadAll(body)
		if err != nil {
			return http.StatusBadRequest, []byte(`{"failureClass":"schema_invalid"}`)
		}
		payload = bytes.NewReader(raw)
	}
	req, err := http.NewRequest(method, strings.TrimRight(s.cfg.AgentsURL, "/")+path, payload)
	if err != nil {
		return http.StatusBadGateway, nil
	}
	if method != http.MethodGet {
		req.Header.Set("Content-Type", "application/json")
	}
	if s.cfg.Env != "local" {
		token, err := fetchIDToken(strings.TrimRight(s.cfg.AgentsURL, "/"))
		if err != nil {
			return http.StatusBadGateway, nil
		}
		req.Header.Set("Authorization", "Bearer "+token)
	}
	if strings.HasPrefix(actorEmail, "Bearer ") && (strings.Contains(path, "/v1/execute/") || strings.Contains(path, "/v1/callbacks/")) {
		req.Header.Set("Authorization", actorEmail)
	}
	if actorEmail != "" && !strings.HasPrefix(actorEmail, "Bearer ") {
		req.Header.Set("X-Actor-Email", actorEmail)
	}
	resp, err := s.pipelineClient.Do(req)
	if err != nil {
		return http.StatusBadGateway, nil
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return http.StatusBadGateway, nil
	}
	return resp.StatusCode, raw
}

func writeRaw(w http.ResponseWriter, status int, raw []byte) {
	if raw == nil {
		writeJSON(w, http.StatusBadGateway, failure("tool_error"))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(raw)
}

func (s *Server) handleCallback(w http.ResponseWriter, r *http.Request) {
	if _, err := r.Cookie("session"); err == nil {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return
	}
	if r.Header.Get("Authorization") != "Bearer "+s.cfg.CallbackToken || s.cfg.CallbackToken == "" {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return
	}
	status, raw := s.call(http.MethodPost, "/v1/callbacks/"+r.PathValue("id"), r.Body, "Bearer "+s.cfg.CallbackToken)
	writeRaw(w, status, raw)
}

func (s *Server) handleExecute(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("Authorization") != "Bearer "+s.cfg.WorkflowToken {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return
	}
	writeJSON(w, http.StatusConflict, map[string]string{
		"failureClass": "policy_denied",
		"detail":       "no execute step is waiting",
	})
}

func (s *Server) handleIndex(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, filepath.Join(s.cfg.WebDir, "index.html"))
}

func (s *Server) handleInterview(w http.ResponseWriter, r *http.Request) {
	http.ServeFile(w, r, filepath.Join(s.cfg.WebDir, "interview.html"))
}

func (s *Server) authorized(w http.ResponseWriter, r *http.Request, role string) (principal, string, bool) {
	cookie, err := r.Cookie("session")
	if err != nil || cookie.Value == "" {
		writeJSON(w, http.StatusUnauthorized, failure("policy_denied"))
		return principal{}, "", false
	}
	csrfCookie, csrfErr := r.Cookie("csrf")
	if csrfErr != nil || csrfCookie.Value == "" || r.Header.Get("X-CSRF-Token") != csrfCookie.Value {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return principal{}, "", false
	}
	person, expected, ok := s.openSession(cookie.Value)
	if !ok || expected != csrfCookie.Value {
		writeJSON(w, http.StatusUnauthorized, failure("policy_denied"))
		return principal{}, "", false
	}
	if person.Role != role {
		writeJSON(w, http.StatusForbidden, failure("policy_denied"))
		return principal{}, "", false
	}
	return person, cookie.Value, true
}

func (s *Server) upstreamTurn(messageID, text, traceparent string) ([]sseEvent, error) {
	payload, err := json.Marshal(map[string]string{"messageId": messageID, "text": text})
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequest(http.MethodPost, strings.TrimRight(s.cfg.AgentsURL, "/")+"/v1/turns", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if traceparent != "" {
		req.Header.Set("traceparent", traceparent)
	}
	resp, err := s.turnClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, io.ErrUnexpectedEOF
	}
	return parseSSE(string(raw)), nil
}

type sseEvent struct {
	Name string
	Data map[string]any
}

func parseSSE(raw string) []sseEvent {
	var events []sseEvent
	for _, block := range strings.Split(raw, "\n\n") {
		block = strings.TrimSpace(block)
		if block == "" || strings.HasPrefix(block, ":") {
			continue
		}
		var name string
		var dataLine string
		for _, line := range strings.Split(block, "\n") {
			if strings.HasPrefix(line, "event:") {
				name = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
			}
			if strings.HasPrefix(line, "data:") {
				dataLine = strings.TrimSpace(strings.TrimPrefix(line, "data:"))
			}
		}
		if name == "" || dataLine == "" {
			continue
		}
		var data map[string]any
		if err := json.Unmarshal([]byte(dataLine), &data); err != nil {
			continue
		}
		events = append(events, sseEvent{Name: name, Data: data})
	}
	return events
}

func writeEventStream(w http.ResponseWriter, events []sseEvent) {
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.WriteHeader(http.StatusOK)
	flusher, _ := w.(http.Flusher)
	for _, event := range events {
		raw, err := json.Marshal(event.Data)
		if err != nil {
			continue
		}
		_, _ = w.Write([]byte("event: " + event.Name + "\ndata: " + string(raw) + "\n\n"))
		if flusher != nil {
			flusher.Flush()
		}
	}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	raw, err := json.Marshal(payload)
	if err != nil {
		http.Error(w, "schema_invalid", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(raw)
}

func failure(class string) map[string]string {
	return map[string]string{"failureClass": class}
}

func randomID() string {
	buf := make([]byte, 16)
	if _, err := rand.Read(buf); err != nil {
		panic(err)
	}
	return hex.EncodeToString(buf)
}
