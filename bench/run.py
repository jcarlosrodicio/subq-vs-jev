"""Run every case against both models and append raw responses to a JSONL file.

Usage: python bench/run.py [--logs 0,1] [--out results/raw/answers.jsonl]
Already-recorded calls are skipped, so an interrupted run can be resumed.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import generate as g
from client import ask

ROOT = Path(__file__).resolve().parents[1]
JEV_LIMIT = 32_000  # Jev rejects requests above ~32.7K tokens (max_tokens_exceeded)
CHUNK_TOKENS = 29_000


def chunks(state):
    lines = state[len(g.HEADER):].splitlines(keepends=True)
    out, current = [], ""
    for line in lines:
        if current and len(current) + len(line) > CHUNK_TOKENS * g.CHARS_PER_TOKEN:
            out.append(g.HEADER + current)
            current = ""
        current += line
    return out + [g.HEADER + current]


def tasks(case):
    """Yield (task, chunk index, state, questions) for every call this case needs."""
    yield "main", None, case["state"], case["questions"]
    if case["length"] > JEV_LIMIT:
        for i, part in enumerate(chunks(case["state"])):
            yield "chunked", i, part, case["questions"]
    if case["length"] == g.ROBUSTNESS_LENGTH:
        # SubQ caps a request at 16 questions (since 2026-10-13), so the 36 robustness questions go in
        # three calls of 12 to both models.
        items = list(g.robustness(case)[0].items())
        for k in range(0, len(items), 12):
            yield "robust", k // 12, case["state"], dict(items[k:k + 12])
        for k in (1, 2):
            yield f"repeat{k}", None, case["state"], case["questions"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=",".join(map(str, range(g.LOGS_PER_LENGTH))))
    ap.add_argument("--lengths", default=",".join(map(str, g.LENGTHS)))
    ap.add_argument("--out", default=ROOT / "results/raw/answers.jsonl")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            done.add((r["case"], r["task"], r["chunk"], r["model"]))

    n = 0
    with out.open("a") as f:
        for length in map(int, args.lengths.split(",")):
            for log_idx in map(int, args.logs.split(",")):
                case = g.build_case(length, log_idx)
                for task, chunk, state, questions in tasks(case):
                    models = ["jev"] if task == "chunked" else ["jev", "subq"]
                    if n % 2:
                        models.reverse()
                    n += 1
                    for model in models:
                        if (case["id"], task, chunk, model) in done:
                            continue
                        r = ask(model, state, questions)
                        r.update(case=case["id"], length=length, log=log_idx, task=task, chunk=chunk, model=model,
                                 n_questions=len(questions), at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                        f.write(json.dumps(r) + "\n")
                        f.flush()
                        status = f"{r['usage']['input_tokens']} tok" if r["ok"] else r["error"]["body"][:80]
                        print(f"{case['id']} {task:<8} {'' if chunk is None else chunk:>2} {model:<4} {r['latency']:6.2f}s {status}", flush=True)


if __name__ == "__main__":
    main()
