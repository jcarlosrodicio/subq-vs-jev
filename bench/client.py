"""Minimal client for the two System One APIs. Both share the same request and response contract."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request

MODELS = {
    "jev": {"url": "https://api.typesafe.ai/v1/systemone", "env": "JEV_API_KEY", "model": "jev-latest"},
    "subq": {"url": "https://api.subq.ai/v1/systemone", "env": "SUBQ_API_KEY", "model": "subq-snap-preview"},
}
CA = "/etc/ssl/cert.pem"
CONTEXT = ssl.create_default_context(cafile=CA) if os.path.exists(CA) else None
RETRY_STATUS = {429, 500, 502, 503, 504}


def ask(model, state, questions):
    m = MODELS[model]
    body = json.dumps({"model": m["model"], "state": state, "questions": questions}).encode()
    headers = {"Authorization": f"Bearer {os.environ[m['env']]}", "Content-Type": "application/json"}
    for attempt in range(1, 5):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(m["url"], body, headers), timeout=300, context=CONTEXT) as r:
                data = json.load(r)
            return {"ok": True, "latency": time.perf_counter() - t0, "attempts": attempt,
                    "model_version": data["model"], "usage": data["usage"], "answers": data["answers"]}
        except urllib.error.HTTPError as e:
            error = {"status": e.code, "body": e.read().decode(errors="replace")[:500]}
            if e.code not in RETRY_STATUS:
                break
        except (urllib.error.URLError, TimeoutError) as e:
            error = {"status": None, "body": str(e)}
        time.sleep(2 ** attempt)
    return {"ok": False, "latency": time.perf_counter() - t0, "attempts": attempt, "error": error}
