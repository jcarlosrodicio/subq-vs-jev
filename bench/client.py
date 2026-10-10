"""Minimal client for the two System One APIs. Both share the same request and response contract."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

MODELS = {
    "jev": {"url": "https://api.typesafe.ai/v1/systemone", "env": "JEV_API_KEY", "model": "jev-latest"},
    "subq": {"url": "https://api.subq.ai/v1/systemone", "env": "SUBQ_API_KEY", "model": "subq-snap-preview"},
}
CA = "/etc/ssl/cert.pem"
CONTEXT = ssl.create_default_context(cafile=CA) if os.path.exists(CA) else None
RETRY_STATUS = {429, 500, 502, 503, 504}
# Response headers that carry a server-side request id. Jev sends x-typesafe-request-id; SubQ sent none on 2026-10-10.
SERVER_ID_HEADERS = ["x-typesafe-request-id", "x-request-id", "request-id", "x-amzn-requestid", "cf-ray"]


def server_ids(headers):
    return {h: headers[h] for h in SERVER_ID_HEADERS if headers and headers.get(h)}


def ask(model, state, questions):
    m = MODELS[model]
    body = json.dumps({"model": m["model"], "state": state, "questions": questions}).encode()
    calls = []  # one entry per attempt, so retried requests stay traceable too
    for attempt in range(1, 5):
        rid = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {os.environ[m['env']]}", "Content-Type": "application/json", "X-Request-ID": rid}
        sent = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(m["url"], body, headers), timeout=300, context=CONTEXT) as r:
                data = json.load(r)
                calls.append({"client_request_id": rid, "sent_at": sent, "server_ids": server_ids(r.headers), "status": r.status})
            return {"ok": True, "latency": time.perf_counter() - t0, "attempts": attempt, "calls": calls,
                    "model_version": data["model"], "usage": data["usage"], "answers": data["answers"]}
        except urllib.error.HTTPError as e:
            error = {"status": e.code, "body": e.read().decode(errors="replace")[:500]}
            calls.append({"client_request_id": rid, "sent_at": sent, "server_ids": server_ids(e.headers), "status": e.code})
            if e.code not in RETRY_STATUS:
                break
        except (urllib.error.URLError, TimeoutError) as e:
            error = {"status": None, "body": str(e)}
            calls.append({"client_request_id": rid, "sent_at": sent, "server_ids": {}, "status": None})
        time.sleep(2 ** attempt)
    return {"ok": False, "latency": time.perf_counter() - t0, "attempts": attempt, "calls": calls, "error": error}
