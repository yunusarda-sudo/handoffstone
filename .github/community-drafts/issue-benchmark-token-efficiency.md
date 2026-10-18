---
labels: help wanted, performance, benchmark
---

# Improve token efficiency and independently review benchmark fairness

## Why

The compact wire format roughly halves token usage versus pretty-printed JSON
(~11.3k -> ~4.3k on the default scenario), and `critical_fact_preservation`
reaches ~0.90 at a 4k budget and ~0.99 at 8k. But at a **2k** budget we are
*behind* a history-aware chat summary (~0.65 vs ~0.71). We want outside
scrutiny of both the encoding and the benchmark itself.

## Goal

1. Better compression at tight budgets without losing critical facts.
2. An independent, adversarial review of whether the benchmark is fair.

## Tasks

- [ ] Propose/implement a tighter wire encoding (e.g. key interning, delta/columnar record layout) — must stay stdlib-only.
- [ ] Review `bench_tallystone.py` for fairness: matched *actual* token usage, model-agnostic scoring, seed variance, no fixture overfitting.
- [ ] Reconcile the 2k regression against the history-aware summary baseline.
- [ ] Keep `--profile` and `--holdout` honest; add negative controls where they are missing.

## Acceptance criteria

- Reproducible numbers via `python3 bench_tallystone.py --budgets 1000,2000,4000,8000,16000`.
- Any claimed improvement survives the held-out scenario shapes (`--holdout`), not just the default fixture.
- A short written fairness review, including counterexamples.

## How to run

```bash
python3 bench_tallystone.py --profile
python3 bench_tallystone.py --holdout
python3 test_bench_tallystone.py
```
