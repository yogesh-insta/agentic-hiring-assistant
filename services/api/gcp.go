package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

var fetchIDToken = metadataIDToken
var fetchAccessToken = metadataAccessToken

func metadataIDToken(audience string) (string, error) {
	endpoint := "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=" + url.QueryEscape(audience) + "&format=full"
	return metadataGet(endpoint)
}

func metadataAccessToken() (string, error) {
	endpoint := "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
	raw, err := metadataGet(endpoint)
	if err != nil {
		return "", err
	}
	var body struct {
		AccessToken string `json:"access_token"`
	}
	if json.Unmarshal([]byte(raw), &body) != nil || body.AccessToken == "" {
		return "", errDenied
	}
	return body.AccessToken, nil
}

func metadataGet(endpoint string) (string, error) {
	req, err := http.NewRequest(http.MethodGet, endpoint, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Metadata-Flavor", "Google")
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("metadata status %d", resp.StatusCode)
	}
	return strings.TrimSpace(string(raw)), nil
}

func (s *Server) startExecution(workflowID string, brief map[string]any) error {
	if s.startExecutionFn != nil {
		return s.startExecutionFn(workflowID, brief)
	}
	token, err := fetchAccessToken()
	if err != nil {
		return err
	}
	argument, err := json.Marshal(map[string]any{
		"agents_url":  strings.TrimRight(s.cfg.AgentsURL, "/"),
		"workflow_id": workflowID,
		"brief":       brief,
	})
	if err != nil {
		return err
	}
	body, err := json.Marshal(map[string]string{"argument": string(argument)})
	if err != nil {
		return err
	}
	endpoint := fmt.Sprintf(
		"https://workflowexecutions.googleapis.com/v1/projects/%s/locations/%s/workflows/%s/executions",
		s.cfg.ProjectID, s.cfg.WorkflowLocation, s.cfg.WorkflowName,
	)
	req, err := http.NewRequest(http.MethodPost, endpoint, strings.NewReader(string(body)))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.pipelineClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode >= 300 {
		return fmt.Errorf("workflow status %d", resp.StatusCode)
	}
	return nil
}

func (s *Server) postCallback(callbackURL string, payload []byte) error {
	if s.postCallbackFn != nil {
		return s.postCallbackFn(callbackURL, payload)
	}
	token, err := fetchAccessToken()
	if err != nil {
		return err
	}
	req, err := http.NewRequest(http.MethodPost, callbackURL, strings.NewReader(string(payload)))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.pipelineClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode >= 300 {
		return fmt.Errorf("callback status %d", resp.StatusCode)
	}
	return nil
}
