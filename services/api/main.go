package main

import (
	"log"
	"net/http"
	"os"
)

func main() {
	env := getenv("ENV", "local")
	server := NewServer(Config{
		Env:              env,
		AgentsURL:        getenv("AGENTS_URL", "http://127.0.0.1:8090"),
		WebDir:           getenv("WEB_DIR", "apps/web"),
		WorkflowToken:    secret("WORKFLOW_TOKEN", env, "local-workflow"),
		CallbackToken:    secret("CALLBACK_TOKEN", env, "local-api"),
		SessionSecret:    secret("SESSION_SECRET", env, "local-dev-secret"),
		ProjectID:        os.Getenv("GOOGLE_CLOUD_PROJECT"),
		WorkflowName:     os.Getenv("WORKFLOW_NAME"),
		WorkflowLocation: getenv("WORKFLOW_LOCATION", "australia-southeast1"),
		HirerEmail:       os.Getenv("HIRER_EMAIL"),
		CandidateEmail:   os.Getenv("CANDIDATE_EMAIL"),
		GoogleClientID:   os.Getenv("GOOGLE_CLIENT_ID"),
	})
	addr := ":" + getenv("PORT", "8080")
	log.Printf("api listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, server.Handler()))
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func secret(key, env, localDefault string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	if env == "local" {
		return localDefault
	}
	return ""
}
