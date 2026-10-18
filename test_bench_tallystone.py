#!/usr/bin/env python3
"""
Tests for the tallystone benchmark.

The point of these tests is NOT to re-assert "tallystone wins" (that would be a
self-congratulatory green suite). It is to prove the benchmark has teeth:

  * the scenario is deterministic
  * the transports are what they claim to be
  * every metric moves when the underlying information moves (sensitivity)
  * negative controls (empty / garbage / sabotaged transports) score LOW

If a future change made the metric blind — e.g. always returned 1.0 — the
negative-control tests would fail.
"""

import json

import bench_tallystone as B


class TestBench:
    def setup_method(self):
        self.scenario = B.generate_scenario(seed=42, n_decisions=20, n_constraints=10, n_pending=5)
        self.records = B.build_records(self.scenario)
        self.ts_compact = B.transport_tallystone(self.scenario, mode="compact")
        self.ts_current = B.transport_tallystone(self.scenario, mode="current")
        self.ts_audit = B.transport_tallystone(self.scenario, mode="audit")
        self.summary_terse = B.transport_chat_summary(self.scenario, summary_mode="terse")
        self.summary_verbose = B.transport_chat_summary(self.scenario, summary_mode="verbose")
        self.summary_history = B.transport_chat_summary(self.scenario, summary_mode="history")

    # ------------------------------------------------------------------ scenario
    def test_scenario_is_deterministic(self):
        a = B.generate_scenario(seed=42, n_decisions=20, n_constraints=10, n_pending=5)
        b = B.generate_scenario(seed=42, n_decisions=20, n_constraints=10, n_pending=5)
        assert a.to_dict() == b.to_dict()

    def test_scenario_seed_changes_output(self):
        assert B.generate_scenario(seed=42).decisions != B.generate_scenario(seed=7).decisions

    def test_scenario_shape(self):
        active = [d for d in self.scenario.decisions if not d["superseded"]]
        superseded = [d for d in self.scenario.decisions if d["superseded"]]
        assert len(active) == 20
        assert len(superseded) == 2
        assert len(self.scenario.constraints) == 10
        assert len(self.scenario.pending) == 5
        assert len(self.scenario.planted_conflicts) == 1
        for d in superseded:
            assert any(x["key"] == d["superseded_by"] for x in self.scenario.decisions)

    # ---------------------------------------------------------------- transports
    def test_cb_transport_is_valid_package(self):
        assert self.ts_compact.lstrip().startswith("{")
        pkg = B.cb.ContextPackage.from_json(self.ts_compact)
        assert pkg.project_context is not None
        assert len(pkg.decisions) == 20                      # current decisions
        assert len(pkg.supersession_history) == 2            # compact change history
        assert pkg.working_state is not None

    def test_summary_transport_is_not_a_package(self):
        assert not self.summary_terse.lstrip().startswith("{")
        try:
            B.cb.ContextPackage.from_json(self.summary_terse)
            raised = False
        except Exception:
            raised = True
        assert raised, "a naive summary must not parse as a structured package"

    # ------------------------------------------------------------------- metrics
    def test_decision_recall_kept_by_both(self):
        ts_m = B.evaluate(self.scenario, self.ts_compact, self.records)
        sm_m = B.evaluate(self.scenario, self.summary_terse, self.records)
        assert ts_m.decision_recall == 1.0
        assert sm_m.decision_recall == 1.0

    def test_rationale_lost_by_terse_summary(self):
        assert B.evaluate(self.scenario, self.ts_compact, self.records).rationale_preservation == 1.0
        assert B.evaluate(self.scenario, self.summary_terse, self.records).rationale_preservation == 0.0

    def test_verbose_summary_recovers_rationale_but_not_evidence(self):
        sm = B.evaluate(self.scenario, self.summary_verbose, self.records)
        assert sm.rationale_preservation == 1.0
        assert sm.evidence_provenance == 0.0
        assert sm.change_history == 0.0
        assert sm.conflict_visibility == 0.0

    def test_conflict_visibility_separates_transports(self):
        assert B.evaluate(self.scenario, self.ts_compact, self.records).conflict_visibility == 1.0
        assert B.evaluate(self.scenario, self.summary_terse, self.records).conflict_visibility == 0.0

    # ---------------------------------------------- change history (the product fix)
    def test_default_compact_preserves_change_history(self):
        # The product decision: the DEFAULT handoff keeps the change history.
        assert B.evaluate(self.scenario, self.ts_compact, self.records).change_history == 1.0
        # ...while the OLD default (current decisions only) dropped it.
        assert B.evaluate(self.scenario, self.ts_current, self.records).change_history == 0.0

    def test_compact_dominates_current_overall(self):
        compact = B.evaluate(self.scenario, self.ts_compact, self.records)
        current = B.evaluate(self.scenario, self.ts_current, self.records)
        assert compact.critical_fact_preservation > current.critical_fact_preservation

    def test_audit_carries_full_records(self):
        pkg = B.cb.ContextPackage.from_json(self.ts_audit)
        titles = [d.title for d in pkg.decisions]
        assert len(titles) == 22  # 20 active + 2 superseded, full fidelity
        assert B.evaluate(self.scenario, self.ts_audit, self.records).change_history == 1.0

    def test_history_summary_is_a_real_baseline(self):
        # The strongest rival: a summary that narrates reversals too.
        assert B.evaluate(self.scenario, self.summary_history, self.records).change_history == 1.0

    def test_evidence_provenance_penalized_by_filtering(self):
        compact = B.evaluate(self.scenario, self.ts_compact, self.records)
        audit = B.evaluate(self.scenario, self.ts_audit, self.records)
        assert compact.evidence_provenance < 1.0   # superseded decision's evidence dropped
        assert audit.evidence_provenance == 1.0

    # --------------------------------------------------------------- budget caps
    def test_cb_respects_budget(self):
        for budget in (2000, 4000, 8000):
            text = B.transport_tallystone(self.scenario, mode="compact", budget=budget)
            assert len(text) // 4 <= budget

    def test_summary_respects_budget(self):
        for budget in (1000, 2000, 4000):
            for mode in ("terse", "verbose", "history"):
                text = B.transport_chat_summary(self.scenario, mode, budget=budget)
                assert len(text) // 4 <= budget

    def test_fit_never_grows_package(self):
        full = B.build_context_package(self.scenario, self.records, mode="compact")
        import tallystone as cb
        for budget in (1000, 3000, 6000, 12000):
            fitted = cb.fit_package_to_budget(full, budget)
            assert len(fitted.to_json()) <= len(full.to_json())

    def test_history_prioritized_under_tight_budget(self):
        # The product guarantee must survive a tight budget.
        text = B.transport_tallystone(self.scenario, mode="compact", budget=1200)
        assert B.evaluate(self.scenario, text, self.records).change_history == 1.0

    # ------------------------------------------------- negative controls (teeth)
    def test_empty_transport_scores_zero(self):
        m = B.evaluate(self.scenario, "", self.records)
        assert m.decision_recall == 0.0
        assert m.rationale_preservation == 0.0
        assert m.constraint_recall == 0.0
        assert m.evidence_provenance == 0.0
        assert m.critical_fact_preservation == 0.0

    def test_garbage_transport_scores_below_real_summary(self):
        garbage = "lorem ipsum dolor sit amet " * 50
        g = B.evaluate(self.scenario, garbage, self.records)
        s = B.evaluate(self.scenario, self.summary_terse, self.records)
        assert g.critical_fact_preservation < s.critical_fact_preservation

    def test_metric_is_sensitive_to_sabotage(self):
        pkg = B.cb.ContextPackage.from_json(self.ts_compact)
        baseline = B.evaluate(self.scenario, self.ts_compact, self.records)
        pkg.decisions[0].rationale = ""
        after = B.evaluate(self.scenario, pkg.to_json(), self.records)
        assert after.rationale_preservation < baseline.rationale_preservation

    # -------------------------------------------------------------------- report
    def test_run_benchmark_shape_and_deltas(self):
        r = B.run_benchmark(seed=42, n_decisions=20, n_constraints=10, n_pending=5)
        assert set(r["metrics"].keys()) == {"tallystone", "chat_summary"}
        assert r["deltas_tallystone_minus_summary"]["critical_fact_preservation"] > 0

    def test_run_sweep_shape(self):
        r = B.run_sweep(seeds=[42, 7], budgets=[2000, 8000],
                        methods=["ts_compact", "ts_current", "sum_terse"])
        assert r["budgets"] == [2000, 8000]
        for b in r["budgets"]:
            for name in r["methods"]:
                assert set(B._SWEEP_AXES) <= set(r["agg"][b][name].keys())

    def test_compact_beats_current_at_high_budget(self):
        r = B.run_sweep(seeds=[42], budgets=[8000], methods=["ts_compact", "ts_current"])
        assert (r["agg"][8000]["ts_compact"]["critical_fact_preservation"]
                > r["agg"][8000]["ts_current"]["critical_fact_preservation"])

    def test_token_tradeoff_is_real(self):
        r = B.run_benchmark(seed=42)
        assert r["metrics"]["tallystone"]["tokens"] > r["metrics"]["chat_summary"]["tokens"]


def run_all_tests():
    suite = TestBench()
    tests = [
        ("Scenario deterministic", suite.test_scenario_is_deterministic),
        ("Scenario seed sensitivity", suite.test_scenario_seed_changes_output),
        ("Scenario shape", suite.test_scenario_shape),
        ("tallystone transport is valid package", suite.test_cb_transport_is_valid_package),
        ("Summary is not a package", suite.test_summary_transport_is_not_a_package),
        ("Decision recall kept by both", suite.test_decision_recall_kept_by_both),
        ("Rationale lost by terse summary", suite.test_rationale_lost_by_terse_summary),
        ("Verbose summary: rationale yes, evidence no", suite.test_verbose_summary_recovers_rationale_but_not_evidence),
        ("Conflict visibility separates transports", suite.test_conflict_visibility_separates_transports),
        ("DEFAULT compact preserves change history", suite.test_default_compact_preserves_change_history),
        ("Compact dominates current", suite.test_compact_dominates_current_overall),
        ("Audit carries full records", suite.test_audit_carries_full_records),
        ("History summary is a real baseline", suite.test_history_summary_is_a_real_baseline),
        ("Evidence penalized by filtering", suite.test_evidence_provenance_penalized_by_filtering),
        ("tallystone respects budget", suite.test_cb_respects_budget),
        ("Summary respects budget", suite.test_summary_respects_budget),
        ("Fit never grows package", suite.test_fit_never_grows_package),
        ("History prioritized under tight budget", suite.test_history_prioritized_under_tight_budget),
        ("NEG: empty transport scores zero", suite.test_empty_transport_scores_zero),
        ("NEG: garbage < real summary", suite.test_garbage_transport_scores_below_real_summary),
        ("NEG: metric sensitive to sabotage", suite.test_metric_is_sensitive_to_sabotage),
        ("Benchmark shape and deltas", suite.test_run_benchmark_shape_and_deltas),
        ("Sweep shape", suite.test_run_sweep_shape),
        ("Compact beats current at high budget", suite.test_compact_beats_current_at_high_budget),
        ("Token tradeoff is real", suite.test_token_tradeoff_is_real),
    ]

    passed = failed = 0
    for name, fn in tests:
        suite.setup_method()
        try:
            fn()
            print(f"  \u2705 {name}")
            passed += 1
        except Exception as e:
            print(f"  \u274c {name}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 50}")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_all_tests() else 1)
