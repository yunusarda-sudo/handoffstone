# Benchmark Fairness and Token Efficiency Review

Tracks [issue #2](https://github.com/yunusarda-sudo/handoffstone/issues/2).

## Executive Summary

An adversarial examination of `bench_handoffstone.py`, the token allocation profiler (`--profile`), and the equal-budget sweep across five seeds was conducted on Python 3.14.

Key findings:
1. **The benchmark is methodologically fair and has teeth**: Negative controls prevent gaming, scoring is model-agnostic, seeds produce high variance, and metrics are sensitive to planted omissions.
2. **The 2k token deficit is explained by payload asymmetry**: `sum_history` caps out at 1,199 total tokens because it drops all evidence provenance, conflict tags, and alternatives. At a 2,000 token budget, `sum_history` has zero trimming pressure (100% of its decisions fit), whereas `ts_compact_wire` (4,323 total tokens) is forced to discard ~45% of its decision records.
3. **Primary token sink in decisions is attached evidence and alternatives**: In `ts_compact_wire`, decisions account for 3,316 out of 4,318 tokens (76.8%). Within each decision, attached evidence (`ev`) consumes 37% and alternatives (`a`) consume 19% of the bytes.
4. **Greedy fitter order starves constraints under tight budgets**: `fit_package_to_budget` attempts to fit decisions one-by-one before evaluating constraints. Once decision records fill the 2,000 token limit, constraint recall drops to zero.

---

## 1. Empirical Measurements

### 1.1 Equal-Budget Sweep (Mean over seeds `[42, 7, 13, 101, 2024]`)

Command:
```bash
python3 bench_handoffstone.py --budgets 1000,2000,4000,8000,16000
```

#### `critical_fact_preservation`
| Method | 1,000 | 2,000 | 4,000 | 8,000 | 16,000 |
|---|---|---|---|---|---|
| `ts_compact` (pretty JSON) | 0.335 | 0.527 | 0.641 | 0.855 | 0.986 |
| **`ts_compact_wire`** | **0.527** | **0.654** | **0.901** | **0.986** | **0.986** |
| `ts_audit_wire` | 0.213 | 0.474 | 0.874 | 1.000 | 1.000 |
| `ts_current_wire` | 0.384 | 0.511 | 0.826 | 0.844 | 0.844 |
| `sum_terse` | 0.429 | 0.429 | 0.429 | 0.429 | 0.429 |
| `sum_verbose` | 0.446 | 0.571 | 0.571 | 0.571 | 0.571 |
| `sum_history` (strongest baseline) | 0.471 | **0.714** | 0.714 | 0.714 | 0.714 |

#### Breakdown of 2,000 Budget Performance
| Axis | `ts_compact_wire` (2k) | `sum_history` (2k) | Root Cause |
|---|---|---|---|
| `change_history` | **1.000** | **1.000** | Both preserve supersession / reversals |
| `decision_recall` | 0.550 | **1.000** | `sum_history` fits all 20 decisions; wire format fits only ~11 |
| `rationale_preservation` | 0.550 | **1.000** | Correlated with decision recall |
| `constraint_recall` | 0.000 | **1.000** | Wire fitter starves constraints after decisions fill budget |
| `evidence_provenance` | **0.536** | 0.000 | Summary has zero provenance locators |
| `conflict_visibility` | **0.950** | 0.000 | Summary strips machine-detectable conflict tags |
| `pending_task_recall` | **1.000** | **1.000** | Both preserve next steps |
| **Total Tokens** | 1,995 | 1,199 | Summary cannot consume more than 1,199 tokens |

---

### 1.2 Token Profile (`--profile`)

Command:
```bash
python3 bench_handoffstone.py --profile
```

```
==============================================================
  TOKEN PROFILE — where the tokens go
==============================================================
  full = 11,352 tokens
  wire =  4,318 tokens (reduction x2.629)
  serialization overhead: full=808  wire=22

  --- wire, by top-level field ---
    d  (decisions)             3,316 tokens  (76.8%)
    c  (constraints)             494 tokens  (11.4%)
    ch (supersession_history)    222 tokens   (5.1%)
    ws (working_state)           128 tokens   (3.0%)
    pc (project_context)          79 tokens   (1.8%)
    oq (open_questions)           24 tokens   (0.6%)
    un (uncertainty)              22 tokens   (0.5%)
    at (created_at)                8 tokens
    cb (created_by)                3 tokens
==============================================================
```

### 1.3 Per-Decision Byte Breakdown (Average ~660 bytes / ~165 tokens)

Inspecting a typical decision record in `ts_compact_wire`:
* `ev` (Attached evidence references): **247 bytes (37.3%)**
  - Contains IDs, full ISO-8601 captured timestamps, locator paths, description strings, and booleans.
* `a` (Alternatives considered & rejected): **129 bytes (19.5%)**
  - Contains option descriptions and rejection reasons.
* `r` (Rationale): 67 bytes (10.1%)
* `c` (Decision statement): 53 bytes (8.0%)
* `g` (Tags): 37 bytes (5.6%)
* `at` (Created at timestamp): 34 bytes (5.1%)
* `i` (Record ID): 29 bytes (4.4%)
* `t` (Title): 16 bytes (2.4%)
* `o` (Outcome): 10 bytes (1.5%)
* `st` (Status): 10 bytes (1.5%)

---

## 2. Structural Root Causes for the 2k Regression

### 2.1 Asymmetric Information Scope
The benchmark correctly asks: *under equal token constraints, how much critical context survives?*
However:
* `sum_history` is an unconstrained prose summary that hits an intrinsic size ceiling at **1,199 tokens**. Because it omits evidence locators, verification hashes, and structured tags, its entire content fits within 2,000 tokens without any trimming. It scores 5/7 = 0.714 purely because 5 of its axes are 1.0 and 2 are 0.0.
* `ts_compact_wire` carries full machine-verifiable context (4,318 tokens). At 2,000 tokens, it must cut over 50% of its payload.

### 2.2 Decision Record Weight Starves Constraints
In `fit_package_to_budget`:
```python
_PACKAGE_FIT_PRIORITY = (
    "project_context",
    "working_state",
    "supersession_history",
    "decisions",
    "constraints",
    "evidence",
    "open_questions",
    "uncertainty",
)
```
Because all decisions are added sequentially before any constraints, and each decision consumes ~165 tokens:
1. `project_context` + `working_state` + `supersession_history` consume ~430 tokens.
2. The remaining ~1,560 tokens fit exactly 9–10 decisions (out of 20).
3. The budget is exhausted. Constraints (which only cost ~50 tokens each) are never reached, dropping `constraint_recall` to 0.0.

### 2.3 Sub-millisecond Timestamp Noise
In `_enc_common`, `rec.created_at` is compared to `pkg.created_at`. When packages are constructed after records are captured, the timestamps differ by milliseconds. This causes every single record to serialize a redundant 34-byte ISO timestamp (`"at":"2026-11-23T22:32:16.525505+00:00"`), wasting ~250–350 tokens across the package.

---

## 3. Review of Benchmark Fairness & Negative Controls

The test suite in `test_bench_handoffstone.py` verifies the benchmark's rigor:
1. **Deterministic Scenario Generation**: Fixed seeds yield bit-for-bit identical fixtures across machines.
2. **Negative Controls Have Real Teeth**:
   - Empty transport (`""`) scores `0.000` across all axes.
   - Garbage transport (`"lorem ipsum..."`) scores strictly below a real summary.
   - Sabotaging rationale in a transport measurably lowers the `rationale_preservation` metric.
3. **No Fixture Overfitting**:
   - `test_scenario_seed_changes_output` verifies that seed changes alter the decision pool, planted conflict keys, and supersession chains.
   - `HOLDOUT_CONFIGS` with varying shapes ((12, 6, 3) and (28, 14, 8)) confirm that findings are not an artifact of the (20, 10, 5) default.

---

## 4. Architectural Recommendations for Wire v3

To beat `sum_history` at 2,000 tokens while preserving strict stdlib-only compatibility:

1. **Balanced / Interleaved Fitter Allocation**:
   Instead of exhausting the budget on decision tail records, allocate budget proportionally across decisions and constraints (e.g. reserving a minimum quota for constraints or interleaving high-priority constraints). Fitting all 10 constraints costs only ~490 tokens and instantly recovers `constraint_recall` from 0.0 to 1.0.
2. **Tiered Decision Pruning Under Tight Budgets**:
   When fitting under a tight budget (<2,000 tokens), allow decisions to be included in a "core" form (statement + rationale + tags) before adding optional heavy fields (nested evidence arrays and alternative rejection prose).
3. **Interning Redundant Kind Prefixes & Common Enums**:
   Omitting `"decisionrecord-"` from IDs when already inside the `"d"` list and omitting default outcome `"accepted"` saves ~25 tokens per decision.
4. **Timestamp Prefix Sharing**:
   When record timestamps fall on the same date/hour as `pkg.created_at`, serialize only the delta or time component.
