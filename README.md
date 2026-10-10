# SubQ Snap vs Jev

A reproducible test of two decision models, [SubQ Snap](https://docs.subq.ai/) and [Jev](https://docs.typesafe.ai/), on the same 1,920 questions about a fictional store's event log, from 2K to 360K tokens of context.

**Results page:** https://jcarlosrodicio.github.io/subq-vs-jev/ (English and Spanish)

## What it found (run on 10 October 2026)

| | SubQ Snap | Jev |
|---|---|---|
| Accuracy, logs up to 30K tokens | 96.7% | 94.8% |
| Accuracy, 360K-token logs | 57.5% | 76.7% (reading 29K chunks) |
| Calibration error up to 30K (ECE) | 0.030 | 0.038 |
| Calibration error, 64K and up | 0.178 | 0.110 (chunked) |
| Byte-identical output on repeat | 100% | 50% (97.5% same answer) |
| Answers changed by shuffling options | 0 of 40 | 3 of 40 |
| Median latency, 8K tokens | 1.00 s | 0.30 s |

Jev rejects requests above about 32.7K tokens (`max_tokens_exceeded`), so on longer logs it also gets the log split into 29K pieces and its answers are combined. SubQ reads every log in one call.

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
- Jev reports output tokens; its output price wasn't published, so cost figures use input tokens only. SubQ doesn't charge for output.
- 10 logs per size, 20 questions per kind and size. The page shows 95% intervals.

## Disclosure

Independent test, not affiliated with Subquadratic or TypeSafe. SubQ access was free during its preview weekend.
