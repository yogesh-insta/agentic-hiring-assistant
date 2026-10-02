package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"time"
)

func (s *Server) sessionSecret() string {
	if s.cfg.SessionSecret != "" {
		return s.cfg.SessionSecret
	}
	if s.cfg.Env == "local" {
		return "local-dev-secret"
	}
	return ""
}

func (s *Server) seal(person principal, csrf string) (string, error) {
	secret := s.sessionSecret()
	if secret == "" {
		return "", errDenied
	}
	body, err := json.Marshal(map[string]any{
		"email":         person.Email,
		"role":          person.Role,
		"applicationId": person.ApplicationID,
		"csrf":          csrf,
		"exp":           time.Now().Add(12 * time.Hour).Unix(),
	})
	if err != nil {
		return "", err
	}
	payload := base64.RawURLEncoding.EncodeToString(body)
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(payload))
	return payload + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil)), nil
}

func (s *Server) openSession(token string) (principal, string, bool) {
	secret := s.sessionSecret()
	parts := splitTwo(token)
	if secret == "" || parts[0] == "" || parts[1] == "" {
		return principal{}, "", false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(parts[0]))
	expected := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(expected), []byte(parts[1])) {
		return principal{}, "", false
	}
	raw, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return principal{}, "", false
	}
	var body struct {
		Email         string `json:"email"`
		Role          string `json:"role"`
		ApplicationID string `json:"applicationId"`
		CSRF          string `json:"csrf"`
		Exp           int64  `json:"exp"`
	}
	if json.Unmarshal(raw, &body) != nil || body.Exp <= time.Now().Unix() {
		return principal{}, "", false
	}
	return principal{Email: body.Email, Role: body.Role, ApplicationID: body.ApplicationID}, body.CSRF, true
}

func splitTwo(token string) [2]string {
	for i := 0; i < len(token); i++ {
		if token[i] == '.' {
			return [2]string{token[:i], token[i+1:]}
		}
	}
	return [2]string{}
}
