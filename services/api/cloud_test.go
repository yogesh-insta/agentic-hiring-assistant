package main

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestIdentityPlatformTokenSignsIn(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	previous := fetchCerts
	fetchCerts = func() (map[string]*rsa.PublicKey, error) {
		return map[string]*rsa.PublicKey{"test": &key.PublicKey}, nil
	}
	t.Cleanup(func() { fetchCerts = previous })

	token := signToken(t, key, map[string]any{
		"iss":            "https://securetoken.google.com/demo",
		"aud":            "demo",
		"email":          "hirer@example.com",
		"email_verified": true,
		"exp":            time.Now().Add(time.Hour).Unix(),
	})
	api := NewServer(Config{
		Env:           "cloud",
		ProjectID:     "demo",
		SessionSecret: "test-secret",
		HirerEmail:    "hirer@example.com",
	})
	request := httptest.NewRequest(http.MethodPost, "/sessions", strings.NewReader(`{"idToken":"`+token+`"}`))
	response := httptest.NewRecorder()
	api.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("login %d %s", response.Code, response.Body.String())
	}
	var body map[string]string
	if json.Unmarshal(response.Body.Bytes(), &body) != nil || body["role"] != "hirer" {
		t.Fatalf("body %s", response.Body.String())
	}

	forged := signToken(t, key, map[string]any{
		"iss":            "https://securetoken.google.com/demo",
		"aud":            "demo",
		"email":          "avery@example.com",
		"email_verified": true,
		"role":           "hirer",
		"exp":            time.Now().Add(time.Hour).Unix(),
	})
	api.cfg.CandidateEmail = "avery@example.com"
	request = httptest.NewRequest(http.MethodPost, "/sessions", strings.NewReader(`{"idToken":"`+forged+`"}`))
	response = httptest.NewRecorder()
	api.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("claimed role %d", response.Code)
	}
}

func TestCloudStartPollsAndApproveSendsTheCallback(t *testing.T) {
	var mu sync.Mutex
	phase := "before"
	var executeHits int
	var started string
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer id-token" {
			t.Errorf("agent auth %s", r.Header.Get("Authorization"))
		}
		if strings.Contains(r.URL.Path, "/v1/execute/") {
			executeHits++
		}
		if strings.Contains(r.URL.Path, "/v1/internal/callback-target") {
			_, _ = w.Write([]byte(`{"purpose":"ad_approval","url":"https://workflow.example/callback"}`))
			return
		}
		id := strings.TrimPrefix(r.URL.Path, "/v1/workflows/")
		mu.Lock()
		status := "proposed"
		if phase == "after" {
			status = "approved"
		}
		mu.Unlock()
		body, _ := json.Marshal(map[string]any{
			"id": id, "step": "ad_reviewed", "approvalId": "ap1",
			"artifact": map[string]any{"status": status},
		})
		_, _ = w.Write(body)
	}))
	defer upstream.Close()

	previous := fetchIDToken
	fetchIDToken = func(string) (string, error) { return "id-token", nil }
	t.Cleanup(func() { fetchIDToken = previous })

	api := NewServer(Config{
		Env:              "cloud",
		AgentsURL:        upstream.URL,
		WorkflowName:     "hiring",
		SessionSecret:    "test-secret",
		ProjectID:        "demo",
		HirerEmail:       "hirer@example.com",
		WorkflowLocation: "australia-southeast1",
	})
	api.startExecutionFn = func(workflowID string, brief map[string]any) error {
		started = workflowID
		if brief["role"] != "barista" {
			t.Fatalf("brief %#v", brief)
		}
		return nil
	}
	api.postCallbackFn = func(callbackURL string, body []byte) error {
		if callbackURL != "https://workflow.example/callback" {
			t.Fatalf("callback %s", callbackURL)
		}
		if !strings.Contains(string(body), `"decision":"approve"`) {
			t.Fatalf("payload %s", body)
		}
		mu.Lock()
		phase = "after"
		mu.Unlock()
		return nil
	}

	recorder := httptest.NewRecorder()
	api.issueSession(recorder, principal{Email: "hirer@example.com", Role: "hirer"})
	session, csrf := sessionFrom(t, recorder)

	start := post(t, api, "/workflows", session, csrf, `{"brief":{"role":"barista"}}`)
	startBody := readBody(t, start)
	if start.StatusCode != http.StatusOK || !strings.Contains(startBody, started) {
		t.Fatalf("start %d %s", start.StatusCode, startBody)
	}

	approved := post(t, api, "/approvals/ap1/approve", session, csrf, `{"workflowId":"`+started+`","candidateIds":[]}`)
	approvedBody := readBody(t, approved)
	if approved.StatusCode != http.StatusOK {
		t.Fatalf("approve %d %s", approved.StatusCode, approvedBody)
	}
	if strings.Contains(approvedBody, "workflow.example") {
		t.Fatalf("callback url leaked %s", approvedBody)
	}
	if !strings.Contains(approvedBody, `"status":"approved"`) {
		t.Fatalf("view %s", approvedBody)
	}
	if executeHits != 0 {
		t.Fatalf("cloud approve called execute %d", executeHits)
	}
}

func signToken(t *testing.T, key *rsa.PrivateKey, claims map[string]any) string {
	t.Helper()
	header, _ := json.Marshal(map[string]string{"alg": "RS256", "kid": "test"})
	payload, _ := json.Marshal(claims)
	signing := base64.RawURLEncoding.EncodeToString(header) + "." + base64.RawURLEncoding.EncodeToString(payload)
	sum := sha256.Sum256([]byte(signing))
	signature, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, sum[:])
	if err != nil {
		t.Fatal(err)
	}
	return signing + "." + base64.RawURLEncoding.EncodeToString(signature)
}

func sessionFrom(t *testing.T, recorder *httptest.ResponseRecorder) (string, string) {
	t.Helper()
	var session, csrf string
	for _, cookie := range recorder.Result().Cookies() {
		if cookie.Name == "session" {
			session = cookie.Value
		}
		if cookie.Name == "csrf" {
			csrf = cookie.Value
		}
	}
	if session == "" || csrf == "" {
		t.Fatal("missing session")
	}
	return session, csrf
}
