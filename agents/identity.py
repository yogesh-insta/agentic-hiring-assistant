"""Bearer checks for local secrets and Cloud Run OIDC tokens."""

import os


def caller_email(authorization, env, shared_secret, verify):
    """Return local, an OIDC email, or an empty string.

    A shared secret is accepted only when env is local. A cloud process
    does not fall back to the demo bearer.
    """
    if not authorization.startswith("Bearer "):
        return ""
    token = authorization[len("Bearer "):]
    if token.count(".") != 2:
        if env == "local" and shared_secret and token == shared_secret:
            return "local"
        return ""
    return verify(token) or ""


def verify_google_oidc(token):
    from google.auth.transport import requests
    from google.oauth2 import id_token

    audience = os.environ.get("OIDC_AUDIENCE", "")
    info = id_token.verify_oauth2_token(token, requests.Request(), audience or None)
    if not audience:
        service = os.environ.get("K_SERVICE", "")
        if service and service not in str(info.get("aud", "")):
            return ""
    return info.get("email", "")


def actor(authorization, kind):
    env = os.environ.get("ENV", "local")
    settings = {
        "workflow": ("WORKFLOW_TOKEN", "WORKFLOW_SERVICE_ACCOUNT", "local-workflow"),
        "api": ("CALLBACK_TOKEN", "API_SERVICE_ACCOUNT", "local-api"),
        "worker": ("WORKER_TOKEN", "WORKER_SERVICE_ACCOUNT", "local-worker"),
    }
    secret_name, email_name, default = settings[kind]
    secret = os.environ.get(secret_name, default if env == "local" else "")
    email = caller_email(authorization, env, secret, verify_google_oidc)
    if email == "local":
        return kind
    expected = os.environ.get(email_name, "")
    if email and expected and email == expected:
        return kind
    return ""
