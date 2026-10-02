package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

func (s *Server) cloudWorkflows() bool {
	return s.cfg.Env != "local" && s.cfg.WorkflowName != ""
}

func (s *Server) handleCloudStart(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Brief map[string]any `json:"brief"`
	}
	if json.NewDecoder(r.Body).Decode(&body) != nil || body.Brief == nil {
		writeJSON(w, http.StatusBadRequest, failure("schema_invalid"))
		return
	}
	workflowID := randomID()
	if err := s.startExecution(workflowID, body.Brief); err != nil {
		writeJSON(w, http.StatusBadGateway, failure("tool_error"))
		return
	}
	raw, err := s.pollWorkflow(workflowID, func(view map[string]any) bool {
		id, _ := view["id"].(string)
		return id == workflowID
	})
	if err != nil {
		writeJSON(w, http.StatusGatewayTimeout, failure("timeout"))
		return
	}
	writeRaw(w, http.StatusOK, raw)
}

func (s *Server) signalWorkflow(w http.ResponseWriter, workflowID, purpose string, payload []byte) {
	if purpose == "" || workflowID == "" {
		writeJSON(w, http.StatusConflict, failure("policy_denied"))
		return
	}
	status, raw := s.call(http.MethodGet, "/v1/workflows/"+workflowID, nil, "")
	if status != http.StatusOK {
		writeRaw(w, status, raw)
		return
	}
	var before map[string]any
	if json.Unmarshal(raw, &before) != nil {
		writeJSON(w, http.StatusBadGateway, failure("tool_error"))
		return
	}
	mark := fingerprint(before)
	targetStatus, targetBody := s.call(
		http.MethodGet,
		"/v1/internal/callback-target?workflowId="+url.QueryEscape(workflowID)+"&purpose="+url.QueryEscape(purpose),
		nil,
		"",
	)
	if targetStatus != http.StatusOK {
		writeRaw(w, targetStatus, targetBody)
		return
	}
	var target struct {
		URL string `json:"url"`
	}
	if json.Unmarshal(targetBody, &target) != nil || target.URL == "" {
		writeJSON(w, http.StatusBadGateway, failure("tool_error"))
		return
	}
	if err := s.postCallback(target.URL, payload); err != nil {
		writeJSON(w, http.StatusBadGateway, failure("tool_error"))
		return
	}
	updated, err := s.pollWorkflow(workflowID, func(view map[string]any) bool {
		return fingerprint(view) != mark
	})
	if err != nil {
		writeJSON(w, http.StatusGatewayTimeout, failure("timeout"))
		return
	}
	writeRaw(w, http.StatusOK, updated)
}

func (s *Server) pollWorkflow(id string, ready func(map[string]any) bool) ([]byte, error) {
	deadline := time.Now().Add(45 * time.Second)
	for {
		status, raw := s.call(http.MethodGet, "/v1/workflows/"+id, nil, "")
		if status == http.StatusOK {
			var view map[string]any
			if json.Unmarshal(raw, &view) == nil && ready(view) {
				return raw, nil
			}
		}
		if time.Now().After(deadline) {
			return nil, errDenied
		}
		time.Sleep(200 * time.Millisecond)
	}
}

func fingerprint(view map[string]any) string {
	artifact, _ := view["artifact"].(map[string]any)
	return fmt.Sprint(view["step"], "|", view["approvalId"], "|", artifact["status"])
}

func purposeFor(view map[string]any) string {
	step, _ := view["step"].(string)
	artifact, _ := view["artifact"].(map[string]any)
	status, _ := artifact["status"].(string)
	switch step {
	case "ad_reviewed":
		if status == "approved" {
			return "publish"
		}
		return "ad_approval"
	case "published":
		return "shortlist_request"
	case "shortlist_proposed":
		return "shortlist_approval"
	case "schedule_proposed":
		return "schedule_approval"
	case "interviews_scheduled":
		return "record_hire"
	case "onboarding_proposed":
		return "onboarding_approval"
	default:
		return ""
	}
}

func readJSON(r io.Reader) map[string]any {
	var body map[string]any
	if json.NewDecoder(r).Decode(&body) != nil {
		return map[string]any{}
	}
	return body
}
