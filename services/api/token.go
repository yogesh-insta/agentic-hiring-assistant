package main

import (
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"io"
	"net/http"
	"strings"
	"time"
)

var fetchCerts = func() (map[string]*rsa.PublicKey, error) {
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get("https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var certs map[string]string
	if json.Unmarshal(raw, &certs) != nil {
		return nil, errDenied
	}
	keys := map[string]*rsa.PublicKey{}
	for kid, certPEM := range certs {
		block, _ := pem.Decode([]byte(certPEM))
		if block == nil {
			continue
		}
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			continue
		}
		key, ok := cert.PublicKey.(*rsa.PublicKey)
		if ok {
			keys[kid] = key
		}
	}
	return keys, nil
}

func verifyIDToken(token, projectID string, now int64) (idClaims, error) {
	keys, err := fetchCerts()
	if err != nil {
		return idClaims{}, err
	}
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return idClaims{}, errDenied
	}
	headerJSON, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return idClaims{}, errDenied
	}
	var header struct {
		Alg string `json:"alg"`
		Kid string `json:"kid"`
	}
	if json.Unmarshal(headerJSON, &header) != nil || header.Alg != "RS256" {
		return idClaims{}, errDenied
	}
	key := keys[header.Kid]
	if key == nil {
		return idClaims{}, errDenied
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return idClaims{}, errDenied
	}
	sum := sha256.Sum256([]byte(parts[0] + "." + parts[1]))
	if rsa.VerifyPKCS1v15(key, crypto.SHA256, sum[:], signature) != nil {
		return idClaims{}, errDenied
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return idClaims{}, errDenied
	}
	var raw map[string]any
	if json.Unmarshal(payload, &raw) != nil {
		return idClaims{}, errDenied
	}
	claims := idClaims{
		Issuer:        stringField(raw, "iss"),
		Audience:      stringField(raw, "aud"),
		Email:         stringField(raw, "email"),
		EmailVerified: boolField(raw, "email_verified"),
		ClaimedRole:   stringField(raw, "role"),
		ExpiresAt:     int64Field(raw, "exp"),
	}
	return principalClaims(claims, now, projectID)
}

func principalClaims(claims idClaims, now int64, projectID string) (idClaims, error) {
	if claims.Issuer != "https://securetoken.google.com/"+projectID || claims.Audience != projectID {
		return idClaims{}, errDenied
	}
	if claims.ExpiresAt <= now || !claims.EmailVerified || claims.Email == "" {
		return idClaims{}, errDenied
	}
	return claims, nil
}

func stringField(raw map[string]any, key string) string {
	value, _ := raw[key].(string)
	return value
}

func boolField(raw map[string]any, key string) bool {
	value, _ := raw[key].(bool)
	return value
}

func int64Field(raw map[string]any, key string) int64 {
	switch value := raw[key].(type) {
	case float64:
		return int64(value)
	default:
		return 0
	}
}
