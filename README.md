# SubQ Snap vs Jev

A reproducible test of two decision models, [SubQ Snap](https://docs.subq.ai/) and [Jev](https://docs.typesafe.ai/), on the same 3,840 questions about a fictional store's event log, from 2K to 360K tokens of context.

**Results page:** https://jcarlosrodicio.github.io/subq-vs-jev/ (English and Spanish)

## What it found (run on 13 October 2026)

| | SubQ Snap | Jev |
|---|---|---|
| Accuracy, logs up to 30K tokens | 93.9% | 94.7% |
| Accuracy, 360K-token logs | 58.8% | 77.1% (reading 29K chunks) |
| Calibration error up to 30K (ECE) | 0.028 | 0.038 |
| Calibration error, 64K and up | 0.163 | 0.117 (chunked) |
| Byte-identical output on repeat | 90.0% | 50.8% |
| Answers changed by shuffling options | 3 of 80 | 5 of 80 |
| Median latency, 8K tokens | 0.75 s | 0.31 s |

Jev rejects requests above about 32.7K tokens (`max_tokens_exceeded`), so on longer logs it also gets the log split into 29K pieces and its answers are combined. SubQ reads every log in one call, and since 13 October accepts at most 16 questions per request, so the robustness questions are sent in three calls of 12 to both models.

A first run on 10 October, during SubQ's private beta (10 logs per size), is kept in `results/run-2026-10-10`. SubQ kept the same model name between runs but changed: on the very same requests only 11% of its answers were byte-identical, its accuracy up to 30K went from 96.7% to 94.4%, and its median time at 8K went from 1.00 s to 0.75 s. Jev did not change.

## How it works

- `bench/generate.py` builds the logs of Kettle & Co., a store that doesn't exist, from a fixed seed. It writes six kinds of question (find, cross-check, count) and their correct answers.
- `tests/test_truth.py` re-derives every answer from the log text alone, so the ground truth doesn't depend on the generator's internals.
- `bench/run.py` sends byte-identical requests to both APIs (`POST /v1/systemone`), one at a time, alternating which model goes first. It appends raw responses to `results/raw/answers.jsonl` and can resume.
- `bench/analyze.py` grades everything and writes `site/data/results.json`, which the page reads.
- `docs/diseno-prueba.md` is the design written before the full run, with the changes made after the pilot (in Spanish).

## Reproduce

```sh
python3 -m unittest tests/test_truth.py
export SUBQ_API_KEY=... JEV_API_KEY=...
python3 bench/run.py
python3 bench/analyze.py
python3 -m http.server --directory site
```

Python 3.10+ with the standard library only. On macOS with the python.org build, set `SSL_CERT_FILE=/etc/ssl/cert.pem` if HTTPS calls fail certificate checks.

## Caveats

- SubQ Snap is a preview. Both models may have changed since the run.
- Latency was measured from Spain over a home connection and includes the network.
- Jev reports output tokens; its output price wasn't published, so cost figures use input tokens only (Jev $0.042, SubQ $0.05 per 1M on 13 October). SubQ doesn't charge for output.
- 20 logs per size, 40 questions per kind and size. The page shows 95% intervals.

## Disclosure

Independent test, not affiliated with Subquadratic or TypeSafe. SubQ access was free during its preview weekend.
