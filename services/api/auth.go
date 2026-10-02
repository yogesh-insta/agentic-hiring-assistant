package main

import (
	"errors"
	"strings"
)

var errDenied = errors.New("policy_denied")

type idClaims struct {
	Issuer        string
	Audience      string
	ExpiresAt     int64
	Email         string
	EmailVerified bool
	ClaimedRole   string
}

func principalFromClaims(claims idClaims, now int64, projectID string, allowlist map[string]string) (principal, error) {
	if claims.Issuer != "https://securetoken.google.com/"+projectID {
		return principal{}, errDenied
	}
	if claims.Audience != projectID || claims.ExpiresAt <= now || !claims.EmailVerified {
		return principal{}, errDenied
	}
	role, ok := allowlist[strings.ToLower(strings.TrimSpace(claims.Email))]
	if !ok || (claims.ClaimedRole != "" && claims.ClaimedRole != role) {
		return principal{}, errDenied
	}
	return principal{Email: strings.ToLower(strings.TrimSpace(claims.Email)), Role: role}, nil
}
