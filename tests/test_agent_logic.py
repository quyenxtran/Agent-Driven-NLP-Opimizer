from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPO_ROOT / "Agent-Driven-NLP-Opimizer"
IMPORT_ROOT = PROJECT_ROOT if PROJECT_ROOT.exists() else REPO_ROOT
if str(IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPORT_ROOT))

from benchmarks import agent_runner as ar


class StubClient:
    def __init__(self, payload: dict[str, object], raw: str = "{}") -> None:
        self.payload = payload
        self.raw = raw
        self.last_backend = "stub"

    def chat(self, *args: object, **kwargs: object) -> str:
        return self.raw

    def extract_json(self, raw: str) -> dict[str, object]:
        return self.payload


def make_args(**overrides: object) -> argparse.Namespace:
    base = {
        "run_name": "unit",
        "benchmark_hours": 12.0,
        "search_hours": 10.0,
        "validation_hours": 2.0,
        "min_probe_reference_runs": 0,
        "probe_low_fidelity_enabled": 1,
        "probe_nfex": 5,
        "probe_nfet": 2,
        "probe_ncp": 1,
        "finalization_hard_gate_enabled": 1,
        "executive_controller_enabled": True,
        "executive_trigger_rejects": 2,
        "executive_force_after_rejects": 3,
        "executive_top_k_lock": 1,
        "single_scientist_mode": 0,
        "nc_library": "1,2,3,2;2,2,2,2",
        "seed_library": "notebook",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def balanced_counterproposal() -> dict[str, object]:
    return {
        "nc": [2, 2, 2, 2],
        "flow_adjustments": {
            "Ffeed": 0.10,
            "F1": 0.08,
            "Fdes": 0.06,
            "Fex": 0.02,
            "Fraf": -0.02,
            "tstep": 0.0,
        },
        "expected_metric_effect": {
            "delta_productivity": 0.05,
            "delta_purity": 0.01,
            "delta_recovery_ga": 0.02,
            "delta_recovery_ma": 0.01,
            "delta_violation": -0.02,
        },
        "physics_justification": "Mass balance and flow split remain consistent.",
    }


def assert_balanced_flow(flow: dict[str, object]) -> None:
    required = {"Ffeed", "F1", "Fdes", "Fex", "Fraf", "tstep"}
    assert set(flow) == required
    assert flow["F1"] == pytest.approx(float(flow["Ffeed"]) + float(flow["Fraf"]))
    assert flow["F1"] == pytest.approx(float(flow["Fdes"]) + float(flow["Fex"]))


def make_heuristics_repo(root: Path) -> None:
    write_json(
        root / "agents" / "hypotheses.json",
        {
            "_schema_version": "1.0",
            "hypotheses": [
                {
                    "id": "H1",
                    "title": "Fdes Purity Impact is Non-Linear",
                    "status": "active_testing",
                    "confidence": "low_medium",
                    "statement": "Increasing Fdes has diminishing returns and can amplify purity loss at higher flow rates.",
                    "simulation_results": [
                        {
                            "run_name": "run_01",
                            "verdict": "inconclusive",
                            "notes": "solver_error after an infeasible sweep",
                        },
                        {
                            "run_name": "run_02",
                            "verdict": "inconclusive",
                            "notes": "solver_error again after a second infeasible sweep",
                        },
                    ],
                }
            ],
        },
    )
    write_json(
        root / "agents" / "failures.json",
        {
            "_schema_version": "1.0",
            "failures": [
                {
                    "id": "F1",
                    "title": "Solver Error Due to Constraint Infeasibility",
                    "severity": "critical",
                    "symptoms": ["termination_status == 'solver_error'"],
                    "prevention": [
                        "Check flow consistency: F1 == Ffeed + Fraf (within 1%) before retrying.",
                        "Reduce Ffeed by 10-20% if feasibility remains weak.",
                    ],
                    "occurrences": [],
                }
            ],
        },
    )


def test_scientist_b_review_routes_acquisition_taxonomy() -> None:
    candidate_task = {"nc": [2, 2, 2, 2], "seed_name": "reference"}
    effective_task = {
        "nc": [2, 2, 2, 2],
        "seed_name": "reference",
        "flow": {"Ffeed": 1.3, "F1": 2.0, "Fdes": 1.2, "Fex": 0.8, "Fraf": 0.7, "tstep": 9.4},
    }
    base_payload = {
        "decision": "reject",
        "reason": "Narrow the search to a better supported near-feasible region.",
        "comparison_assessment": [
            "Compared against prior run_name=run_01 status=ok viol=0.12 productivity=0.91."
        ],
        "evidence": ["Low violation signal.", "Reasonable productivity signal."],
        "nc_strategy_assessment": [
            "Candidate A is weaker because it has less supporting evidence.",
            "Candidate B is weaker because it is less balanced on violation and productivity.",
        ],
        "information_target": "Learn whether a nearby layout improves feasibility without losing productivity.",
        "alternatives_considered": [
            "Alternative A rejected because its violation stayed high.",
            "Alternative B rejected because it did not improve the balance of metrics.",
        ],
        "coverage_gap": "underexplored flow region",
        "hypothesis_connection": "H1",
        "convergence_assessment": "Stagnating but still informative.",
    }

    cases = [
        ("EXPLORE", "llm"),
        ("EXPLOIT", "llm"),
        ("VERIFY", "llm"),
    ]
    for acquisition_type, expected_mode in cases:
        payload = dict(base_payload)
        payload["acquisition_type"] = acquisition_type
        client = StubClient(payload)
        note = ar.scientist_b_review(
            client,
            candidate_task,
            effective_task,
            best_result=None,
            results=[],
            args=make_args(),
            codebase_context_excerpt="",
            compute_context_excerpt="",
            constraint_context_excerpt="",
            nc_strategy_excerpt="",
            research_excerpt="",
            current_priorities=[],
            sqlite_context_excerpt="SQLite context: total_records=0, feasible_records=0",
            iteration=1,
        )

        assert note["mode"] == expected_mode
        assert note["acquisition_type"] == acquisition_type
        assert note["information_target"] == base_payload["information_target"]
        assert len(note["alternatives_considered"]) == 2


def test_scientist_b_review_preserves_balanced_counterproposal_flow() -> None:
    candidate_task = {"nc": [2, 2, 2, 2], "seed_name": "reference"}
    effective_task = {
        "nc": [2, 2, 2, 2],
        "seed_name": "reference",
        "flow": {"Ffeed": 1.3, "F1": 2.0, "Fdes": 1.2, "Fex": 0.8, "Fraf": 0.7, "tstep": 9.4},
    }
    payload = {
        "decision": "approve",
        "reason": "The candidate is balanced enough to execute.",
        "acquisition_type": "EXPLOIT",
        "information_target": "Confirm whether the same layout improves near-feasible points.",
        "alternatives_considered": [
            "Alternative A rejected because it lacks flow consistency evidence.",
            "Alternative B rejected because it does not improve the violation trend.",
        ],
        "comparison_assessment": [
            "Compared run_name=run_01 status=solver_error viol=0.18 productivity=0.74 against the proposed candidate."
        ],
        "last_two_run_audit": [],
        "flowrate_audit": [
            "Flow audit: Ffeed=1.30, F1=2.00, Fdes=1.20, Fex=0.80, Fraf=0.70, tstep=9.40; the reference flow is balanced."
        ],
        "delta_audit": [],
        "column_topology_audit": [],
        "physics_audit": "Mass balance and flow-split reasoning support the proposal.",
        "counterproposal_run": balanced_counterproposal(),
        "nc_strategy_assessment": [
            "The candidate nc is stronger than the main alternative because it is more balanced.",
            "The competitor layout is weaker because its evidence is thinner.",
        ],
        "compute_assessment": "The proposal stays within the same compute envelope.",
        "counterarguments": ["The point is still close to the infeasible boundary."],
        "required_checks": ["Recheck solver termination and post-solve flow consistency."],
        "priority_updates": ["Keep the flow-balanced candidate in the queue."],
        "risk_flags": ["Close to the infeasible boundary."],
    }
    client = StubClient(payload)

    note = ar.scientist_b_review(
        client,
        candidate_task,
        effective_task,
        best_result=None,
        results=[],
        args=make_args(),
        codebase_context_excerpt="",
        compute_context_excerpt="",
        constraint_context_excerpt="",
        nc_strategy_excerpt="",
        research_excerpt="",
        current_priorities=[],
        sqlite_context_excerpt="SQLite context: total_records=1, feasible_records=0",
        iteration=1,
    )

    assert note["mode"] == "llm"
    assert note["decision"] == "approve"
    assert note["acquisition_type"] == "EXPLOIT"
    assert_balanced_flow(note["counterproposal_run"]["flow_adjustments"])
    assert note["counterproposal_run"] == balanced_counterproposal()


def test_hypothesis_matcher_emits_h1_guidance_for_consecutive_infeasible_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_heuristics_repo(tmp_path)
    monkeypatch.setattr(ar, "REPO_ROOT", tmp_path)

    context = ar.build_heuristics_context(max_chars=4000)
    assert "H1" in context
    assert "Fdes Purity Impact is Non-Linear" in context
    assert "solver_error after an infeasible sweep" in context
    assert "solver_error again after a second infeasible sweep" in context


def test_failure_recovery_context_emits_f1_flow_consistency_recovery_on_solver_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_heuristics_repo(tmp_path)
    monkeypatch.setattr(ar, "REPO_ROOT", tmp_path)

    context = ar.build_heuristics_context(max_chars=4000)
    assert "F1" in context
    assert "Solver Error Due to Constraint Infeasibility" in context
    assert "termination_status == 'solver_error'" in context
    assert "Check flow consistency: F1 == Ffeed + Fraf (within 1%)" in context


def test_physics_informed_select_prefers_near_feasible_over_untried(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    conn = ar.open_sqlite_db(str(db_path))

    feasible_result = {
        "run_name": "near_feasible_probe",
        "nc": [2, 2, 2, 2],
        "seed_name": "reference",
        "status": "solver_error",
        "feasible": False,
        "J_validated": None,
        "metrics": {
            "productivity_ex_ga_ma": 1.10,
            "purity_ex_meoh_free": 0.63,
            "recovery_ex_GA": 0.77,
            "recovery_ex_MA": 0.78,
        },
        "constraint_slacks": {"normalized_total_violation": 0.01},
        "solver": {
            "solver_name": "ipopt",
            "termination_condition": "solver_error",
            "solver_options": {"linear_solver": "mumps"},
        },
        "timing": {"wall_seconds": 1.0, "cpu_hours_accounted": 0.0003},
        "flow": {"Ffeed": 1.2, "F1": 2.0, "Fdes": 1.1, "Fex": 0.9, "Fraf": 0.8, "tstep": 9.2},
    }
    ar.persist_result_to_sqlite(conn, "agent_run", "search", feasible_result)

    board = ar.nc_strategy_board(conn, [[1, 2, 3, 2], [2, 2, 2, 2]])
    ranked = [line for line in board.splitlines() if line.startswith("- rank=")]
    assert len(ranked) == 2
    assert "[2, 2, 2, 2]" in ranked[0]
    assert "[1, 2, 3, 2]" in ranked[1]
    assert "solver_error=1" in ranked[0]


@pytest.mark.parametrize(
    "consecutive_rejects, expected",
    [
        (1, "respect_reject"),
        (2, "respect_reject"),
        (3, "override_execute"),
    ],
)
def test_check_systematic_infeasibility_detects_k_consecutive_failures(
    consecutive_rejects: int, expected: str
) -> None:
    args = make_args()
    tasks = ar.build_search_tasks(args)
    result = ar.executive_controller_decide(
        args,
        tasks,
        tried=set(),
        candidate_idx=0,
        candidate_task=tasks[0],
        b_note={"decision": "reject"},
        search_results=[],
        consecutive_rejects=consecutive_rejects,
    )

    assert result["decision"] == expected
    assert "consecutive rejects" in result["reason"].lower()
    if expected == "override_execute":
        assert result["executive_override_executed"] is True
        assert result["forced_task"]["seed_name"] == "reference"


def test_random_search_mode_selection_function_avoids_duplicates() -> None:
    args = make_args(nc_library="1,2,3,2;2,2,2,2", seed_library="notebook")
    tasks = ar.build_search_tasks(args)
    keys = [(tuple(task["nc"]), str(task["seed_name"])) for task in tasks]

    assert len(keys) == len(set(keys))
    assert all(task["seed_name"] == "reference" for task in tasks[:2])

    manual_tasks = [
        {"nc": [1, 2, 3, 2], "seed_name": "reference"},
        {"nc": [2, 2, 2, 2], "seed_name": "reference"},
        {"nc": [1, 2, 3, 2], "seed_name": "seed_02"},
    ]
    tried = {(tuple(manual_tasks[0]["nc"]), "reference")}
    assert ar.deterministic_select(manual_tasks, tried) == 1


def test_wasted_reject_acquisition_is_logged_through_convergence_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite"
    conn = ar.open_sqlite_db(str(db_path))

    feasible_result = {
        "run_name": "feasible_top",
        "nc": [2, 2, 2, 2],
        "seed_name": "reference",
        "status": "ok",
        "feasible": True,
        "J_validated": 1.25,
        "metrics": {
            "productivity_ex_ga_ma": 1.50,
            "purity_ex_meoh_free": 0.82,
            "recovery_ex_GA": 0.88,
            "recovery_ex_MA": 0.86,
        },
        "constraint_slacks": {"normalized_total_violation": 0.0},
        "solver": {
            "solver_name": "ipopt",
            "termination_condition": "optimal",
            "solver_options": {"linear_solver": "mumps"},
        },
        "timing": {"wall_seconds": 1.0, "cpu_hours_accounted": 0.0003},
        "flow": {"Ffeed": 1.2, "F1": 2.0, "Fdes": 1.1, "Fex": 0.9, "Fraf": 0.8, "tstep": 9.2},
    }
    wasted_reject_result = {
        "run_name": "wasted_reject",
        "nc": [1, 2, 3, 2],
        "seed_name": "reference",
        "status": "solver_error",
        "feasible": False,
        "J_validated": 0.72,
        "metrics": {
            "productivity_ex_ga_ma": 1.05,
            "purity_ex_meoh_free": 0.64,
            "recovery_ex_GA": 0.78,
            "recovery_ex_MA": 0.76,
        },
        "constraint_slacks": {"normalized_total_violation": 0.04},
        "solver": {
            "solver_name": "ipopt",
            "termination_condition": "solver_error",
            "solver_options": {"linear_solver": "mumps"},
        },
        "timing": {"wall_seconds": 1.5, "cpu_hours_accounted": 0.0004},
        "flow": {"Ffeed": 1.1, "F1": 1.9, "Fdes": 1.0, "Fex": 0.9, "Fraf": 0.8, "tstep": 9.0},
    }
    ar.persist_result_to_sqlite(conn, "agent_run", "search", feasible_result)
    ar.persist_result_to_sqlite(conn, "agent_run", "search", wasted_reject_result)

    ar.record_convergence_snapshot(
        conn,
        "agent_run",
        "agent",
        2,
        wasted_reject_result,
        cumulative_wall_seconds=2.5,
        cumulative_cpu_hours=0.0007,
        acquisition_type="WASTED_REJECT",
    )

    row = conn.execute(
        """
        SELECT candidate_run_name, best_feasible_run_name, total_feasible, total_runs,
               nc_layouts_tested, acquisition_type
        FROM convergence_tracker
        WHERE agent_run_name = ?
        ORDER BY sim_number DESC
        LIMIT 1
        """,
        ("agent_run",),
    ).fetchone()

    assert row is not None
    candidate_run_name, best_run_name, total_feasible, total_runs, nc_layouts_tested, acquisition_type = row
    assert candidate_run_name == "wasted_reject"
    assert best_run_name == "feasible_top"
    assert total_feasible == 1
    assert total_runs == 2
    assert nc_layouts_tested == 2
    assert acquisition_type == "WASTED_REJECT"
