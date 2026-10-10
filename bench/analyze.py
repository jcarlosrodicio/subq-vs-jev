"""Score the raw answers against the generator's ground truth and write the site's results.json.

Usage: python bench/analyze.py [--raw results/raw/answers.jsonl] [--out site/data/results.json]
"""
import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import generate as g

ROOT = Path(__file__).resolve().parents[1]

PRICE_PER_M_INPUT = {"jev": 0.042, "subq": 0.09}  # USD, public list prices; neither charges output in our usage
FAMILIES = ["L1", "L2", "X1", "X2", "A1", "A2"]


def wilson(k, n, z=1.96):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def grade(q, truth, a):
    """Return (correct, confidence in the model's own answer, extra) for one answer."""
    if q["type"] == "noul":
        p = a["noul"]
        return (p >= 0.5) == truth, max(p, 1 - p), {"p": p}
    if q["type"] == "choice":
        return a["choice"] == truth, a["probabilities"][a["choice"]], {"choice": a["choice"]}
    probs = {int(k): v for k, v in a["probabilities"].items()}
    level = max(probs, key=probs.get)
    return level == truth, probs[level], {"level": level, "score": a["score"]}


def combine_chunks(q, answers):
    """Merge per-chunk answers for Jev on logs longer than its window."""
    if q["type"] == "noul":
        return max(answers, key=lambda a: a["noul"])
    if q["type"] == "choice":
        return max(answers, key=lambda a: a["probabilities"][a["choice"]])
    return max(answers, key=lambda a: a["score"])


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=ROOT / "results/raw/answers.jsonl")
    ap.add_argument("--out", default=ROOT / "site/data/results.json")
    args = ap.parse_args()
    rows = [json.loads(l) for l in Path(args.raw).read_text().splitlines()]
    cases = {}
    for r in rows:
        if r["case"] not in cases:
            cases[r["case"]] = g.build_case(r["length"], r["log"])

    graded = []  # one entry per (series, case, question)
    calls = defaultdict(list)
    errors = defaultdict(int)
    versions = defaultdict(set)
    chunked = defaultdict(list)
    robust, repeats = {}, defaultdict(dict)

    for r in rows:
        case = cases[r["case"]]
        if not r["ok"]:
            errors[(r["model"], r["task"], r["length"], json.loads(r["error"]["body"]).get("detail", {}).get("error_type", "?")
                    if r["error"]["body"].startswith("{") else "network")] += 1
            continue
        versions[r["model"]].add(r["model_version"])
        if r["task"] == "chunked":
            chunked[r["case"]].append(r)
            continue
        if r["task"] == "robust":
            robust[(r["case"], r["model"])] = r["answers"]
            continue
        if r["task"].startswith("repeat"):
            repeats[(r["case"], r["model"])][r["task"]] = r["answers"]
            continue
        repeats[(r["case"], r["model"])]["main"] = r["answers"]
        calls[(r["model"], r["length"])].append(r)
        for name, q in case["questions"].items():
            t = case["truth"][name]
            ok, conf, extra = grade(q, t["answer"], r["answers"][name])
            graded.append({"series": r["model"], "case": r["case"], "length": r["length"], "q": name,
                           "family": t["family"], "depth": t["depth"], "correct": ok, "conf": conf, **extra})

    for case_id, parts in chunked.items():
        case = cases[case_id]
        if len(parts) != len({p["chunk"] for p in parts}) or any(not p["ok"] for p in parts):
            continue
        for name, q in case["questions"].items():
            t = case["truth"][name]
            a = combine_chunks(q, [p["answers"][name] for p in parts])
            ok, conf, extra = grade(q, t["answer"], a)
            graded.append({"series": "jev_chunked", "case": case_id, "length": case["length"], "q": name,
                           "family": t["family"], "depth": t["depth"], "correct": ok, "conf": conf, **extra})
        calls[("jev_chunked", case["length"])].append({"latency": sum(p["latency"] for p in parts),
                                                       "usage": {"input_tokens": sum(p["usage"]["input_tokens"] for p in parts),
                                                                 "output_tokens": sum(p["usage"]["output_tokens"] for p in parts)},
                                                       "n_questions": parts[0]["n_questions"], "chunks": len(parts)})

    series = ["subq", "jev", "jev_chunked"]

    def acc_block(items):
        k, n = sum(i["correct"] for i in items), len(items)
        lo, hi = wilson(k, n)
        return {"n": n, "correct": k, "acc": round(k / n, 4) if n else None, "ci": [lo, hi]}

    by_length = []
    for s in series:
        for length in g.LENGTHS:
            items = [i for i in graded if i["series"] == s and i["length"] == length]
            if not items:
                continue
            row = {"series": s, "length": length, **acc_block(items), "families": {}}
            for fam in FAMILIES:
                row["families"][fam] = acc_block([i for i in items if i["family"] == fam])
            by_length.append(row)

    shared = [l for l in g.LENGTHS if l <= 30_000]
    head_to_head = {s: {"overall": acc_block([i for i in graded if i["series"] == s and i["length"] in shared]),
                        "families": {f: acc_block([i for i in graded if i["series"] == s and i["length"] in shared and i["family"] == f])
                                     for f in FAMILIES}} for s in ["subq", "jev"]}

    depth = []
    for s in series:
        for d in [0.1, 0.5, 0.9]:
            items = [i for i in graded if i["series"] == s and i["depth"] == d]
            if items:
                depth.append({"series": s, "depth": d, **acc_block(items)})

    calibration = {}
    for s in series:
        items = [i for i in graded if i["series"] == s]
        if not items:
            continue
        bins = []
        for b in range(10):
            lo, hi = b / 10, (b + 1) / 10
            inb = [i for i in items if lo <= i["conf"] < hi or (b == 9 and i["conf"] == 1)]
            if inb:
                bins.append({"lo": lo, "hi": hi, "n": len(inb), "conf": round(statistics.mean(i["conf"] for i in inb), 4),
                             "acc": round(sum(i["correct"] for i in inb) / len(inb), 4)})
        ece = sum(b["n"] * abs(b["conf"] - b["acc"]) for b in bins) / len(items)
        brier = statistics.mean((i["conf"] - i["correct"]) ** 2 for i in items)
        calibration[s] = {"bins": bins, "ece": round(ece, 4), "brier": round(brier, 4), "n": len(items),
                          "mean_conf": round(statistics.mean(i["conf"] for i in items), 4)}

    latency = []
    for (s, length), cs in sorted(calls.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        lat = [c["latency"] for c in cs]
        tokens = statistics.mean(c["usage"]["input_tokens"] for c in cs)
        price = PRICE_PER_M_INPUT["jev" if s.startswith("jev") else "subq"]
        latency.append({"series": s, "length": length, "calls": len(cs), "p50": round(pct(lat, 0.5), 3), "p95": round(pct(lat, 0.95), 3),
                        "input_tokens": round(tokens), "output_tokens": round(statistics.mean(c["usage"]["output_tokens"] for c in cs)),
                        "usd_per_1k_decisions": round(tokens * price / 1e6 / cs[0]["n_questions"] * 1000, 4)})

    robustness = {}
    for model in ["subq", "jev"]:
        c1, c2_flip, c2_spread, c3_gap, c3_contra, c4_same, c4_identical = [], [], [], [], [], [], []
        for (case_id, m), answers in robust.items():
            if m != model:
                continue
            _, truth = g.robustness(cases[case_id])
            groups = defaultdict(list)
            for name, t in truth.items():
                groups[(t["test"], t["base"])].append((name, answers[name]))
            for (test, base), items in groups.items():
                if test == "C1":
                    c1.append(len({a["choice"] for _, a in items}) > 1)
                elif test == "C2":
                    ps = [a["noul"] for _, a in items]
                    c2_flip.append(len({p >= 0.5 for p in ps}) > 1)
                    c2_spread.append(max(ps) - min(ps))
                else:
                    p = answers[f"c2_{base}_v0"]["noul"]
                    pn = items[0][1]["noul"]
                    c3_gap.append(abs(p + pn - 1))
                    c3_contra.append((p >= 0.5) == (pn >= 0.5))
        for (case_id, m), reps in repeats.items():
            if m != model or len(reps) < 3:
                continue
            for name in cases[case_id]["questions"]:
                outs = [json.dumps(reps[k][name], sort_keys=True) for k in ("main", "repeat1", "repeat2")]
                c4_identical.append(len(set(outs)) == 1)
                q, t = cases[case_id]["questions"][name], cases[case_id]["truth"][name]["answer"]
                c4_same.append(len({grade(q, t, reps[k][name])[0] for k in ("main", "repeat1", "repeat2")}) == 1)

        def rate(xs):
            return round(sum(xs) / len(xs), 4) if xs else None

        robustness[model] = {
            "option_shuffle_flip_rate": rate(c1), "option_shuffle_n": len(c1),
            "paraphrase_flip_rate": rate(c2_flip), "paraphrase_mean_spread": round(statistics.mean(c2_spread), 4) if c2_spread else None,
            "paraphrase_n": len(c2_flip),
            "negation_mean_gap": round(statistics.mean(c3_gap), 4) if c3_gap else None, "negation_contradiction_rate": rate(c3_contra),
            "negation_n": len(c3_gap),
            "repeat_identical_rate": rate(c4_identical), "repeat_same_answer_rate": rate(c4_same), "repeat_n": len(c4_identical),
        }

    examples = []
    for case_id in sorted({i["case"] for i in graded if i["length"] == 2_000})[:1]:
        case = cases[case_id]
        examples.append({"case": case_id, "state_head": case["state"][:1400], "questions": case["questions"],
                         "truth": {k: v["answer"] for k, v in case["truth"].items()},
                         "answers": {i["series"]: {} for i in graded}})
        for i in graded:
            if i["case"] == case_id:
                examples[-1]["answers"][i["series"]][i["q"]] = {k: i[k] for k in ("correct", "conf", "p", "choice", "level") if k in i}

    out = {
        "meta": {"generated_from": str(Path(args.raw).resolve().relative_to(ROOT)), "first_call": min(r["at"] for r in rows), "last_call": max(r["at"] for r in rows),
                 "model_versions": {k: sorted(v) for k, v in versions.items()}, "cases": len(cases),
                 "answers_graded": len(graded), "lengths": g.LENGTHS, "logs_per_length": g.LOGS_PER_LENGTH,
                 "prices_usd_per_m_input": PRICE_PER_M_INPUT},
        "head_to_head": head_to_head, "by_length": by_length, "depth": depth, "calibration": calibration,
        "latency": latency, "robustness": robustness,
        "errors": [{"model": m, "task": t, "length": l, "type": e, "count": c} for (m, t, l, e), c in sorted(errors.items())],
        "examples": examples,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))

    print("accuracy by length")
    for row in by_length:
        fams = " ".join(f"{f}={row['families'][f]['acc']:.2f}" for f in FAMILIES if row["families"][f]["n"])
        print(f"  {row['series']:<12} {row['length']:>7}  {row['acc']:.3f} (n={row['n']})  {fams}")
    print("head to head <=30K", {s: v["overall"]["acc"] for s, v in head_to_head.items()})
    print("calibration", {s: (v["ece"], v["brier"]) for s, v in calibration.items()})
    print("latency", [(l["series"], l["length"], l["p50"]) for l in latency])
    print("robustness", json.dumps(robustness, indent=1))
    print("errors", out["errors"])


if __name__ == "__main__":
    main()
