from __future__ import annotations

import argparse
import re
from typing import Dict, List, Optional, Sequence, Tuple

from . import run_stage as rs
from .agent_results import (
    deterministic_select,
    effective_violation,
    has_any_feasible,
    is_reference_seed_name,
    low_fidelity_limits,
    has_low_fidelity_optimization_evidence_for_nc,
    ranked_reference_indices,
    reference_probe_runs_completed,
    first_untried_reference_index,
)
from .agent_evidence import normalize_text_list


def env_or_default(name: str, default: str) -> str:
    import os
    value = os.environ.get(name)
    return value if value not in {None, ""} else default


def nc_key(nc: Sequence[int]) -> str:
    return ",".join(str(int(v)) for v in nc)


def nc_prior_score(nc: Sequence[int]) -> float:
    # Neutral structural prior: mild penalty for extreme column count asymmetry only.
    # Does NOT bias toward any specific layout (e.g., reference (1,2,3,2)).
    # The only structural preference is against layouts where one zone has all 8 columns
    # (physically degenerate) or where asymmetry is so extreme the zone functions break down.
    vals = [int(v) for v in nc]
    asymmetry = max(vals) - min(vals)
    return 100.0 - 1.5 * asymmetry


def sqlite_total_records_from_excerpt(text: str) -> int:
    match = re.search(r"total_records=(\d+)", text or "")
    return int(match.group(1)) if match else 0


def configure_stage_args(base: argparse.Namespace, args: argparse.Namespace) -> argparse.Namespace:
    stage_args = argparse.Namespace(**vars(base))
    stage_args.solver_name = args.solver_name
    stage_args.linear_solver = args.linear_solver
    stage_args.tee = args.tee
    stage_args.nc_library = args.nc_library
    stage_args.seed_library = args.seed_library
    stage_args.max_iter = int(env_or_default("SMB_IPOPT_MAX_ITER", "1000"))
    stage_args.tol = float(env_or_default("SMB_IPOPT_TOL", "1e-5"))
    stage_args.acceptable_tol = float(env_or_default("SMB_IPOPT_ACCEPTABLE_TOL", "1e-4"))
    stage_args.nfex = int(env_or_default("SMB_NFEX", str(stage_args.nfex)))
    stage_args.nfet = int(env_or_default("SMB_NFET", str(stage_args.nfet)))
    stage_args.ncp = int(env_or_default("SMB_NCP", str(stage_args.ncp)))
    stage_args.ffeed_bounds = env_or_default("SMB_FFEED_BOUNDS", stage_args.ffeed_bounds)
    stage_args.f1_bounds = env_or_default("SMB_F1_BOUNDS", stage_args.f1_bounds)
    stage_args.fdes_bounds = env_or_default("SMB_FDES_BOUNDS", stage_args.fdes_bounds)
    stage_args.fex_bounds = env_or_default("SMB_FEX_BOUNDS", stage_args.fex_bounds)
    stage_args.fraf_bounds = env_or_default("SMB_FRAF_BOUNDS", stage_args.fraf_bounds)
    stage_args.tstep_bounds = env_or_default("SMB_TSTEP_BOUNDS", stage_args.tstep_bounds)
    stage_args.max_pump_flow = float(env_or_default("SMB_MAX_PUMP_FLOW_ML_MIN", str(stage_args.max_pump_flow)))
    stage_args.max_pump_flow_raf = float(
        env_or_default("SMB_MAX_PUMP_FLOW_RAF_ML_MIN", str(getattr(stage_args, "max_pump_flow_raf", 5.0)))
    )
    stage_args.f1_max_flow = float(env_or_default("SMB_F1_MAX_FLOW", str(stage_args.f1_max_flow)))
    stage_args.f1_max = float(env_or_default("SMB_F1_MAX_FLOW", str(stage_args.f1_max_flow)))
    stage_args.fraf_guard_margin = float(
        env_or_default("SMB_FRAF_GUARD_MARGIN", str(getattr(stage_args, "fraf_guard_margin", 0.05)))
    )
    stage_args.purity_min = float(env_or_default("SMB_TARGET_PURITY_EX_MEOH_FREE", str(stage_args.purity_min)))
    stage_args.recovery_ga_min = float(env_or_default("SMB_TARGET_RECOVERY_GA", str(stage_args.recovery_ga_min)))
    stage_args.recovery_ma_min = float(env_or_default("SMB_TARGET_RECOVERY_MA", str(stage_args.recovery_ma_min)))
    stage_args.project_purity_min = float(
        env_or_default("SMB_PROJECT_TARGET_PURITY_EX_MEOH_FREE", str(getattr(args, "project_purity_min", stage_args.purity_min)))
    )
    stage_args.project_recovery_ga_min = float(
        env_or_default("SMB_PROJECT_TARGET_RECOVERY_GA", str(getattr(args, "project_recovery_ga_min", stage_args.recovery_ga_min)))
    )
    stage_args.project_recovery_ma_min = float(
        env_or_default("SMB_PROJECT_TARGET_RECOVERY_MA", str(getattr(args, "project_recovery_ma_min", stage_args.recovery_ma_min)))
    )
    stage_args.meoh_max_raff_wt = float(env_or_default("SMB_MEOH_MAX_RAFF_WT", str(stage_args.meoh_max_raff_wt)))
    stage_args.water_max_ex_wt = float(env_or_default("SMB_WATER_MAX_EX_WT", str(stage_args.water_max_ex_wt)))
    stage_args.water_max_zone1_entry_wt = float(
        env_or_default("SMB_WATER_MAX_ZONE1_ENTRY_WT", str(stage_args.water_max_zone1_entry_wt))
    )
    return stage_args


def build_search_tasks(args: argparse.Namespace) -> List[Dict[str, object]]:
    nc_library = rs.parse_nc_library(args.nc_library)
    nc_library = sorted(nc_library, key=nc_prior_score, reverse=True)
    seed_library = rs.parse_seed_library(args.seed_library)
    if not seed_library:
        return []

    reference_idx = 0
    for idx, seed in enumerate(seed_library):
        if str(seed.get("name", "")).strip().lower() == "reference":
            reference_idx = idx
            break
    reference_seed = seed_library[reference_idx]
    remaining_seeds = [seed for i, seed in enumerate(seed_library) if i != reference_idx]

    tasks: List[Dict[str, object]] = []
    # Pass 1: cover all layouts with the reference seed first.
    for nc in nc_library:
        tasks.append({"nc": list(nc), "seed_name": str(reference_seed["name"]), "seed": reference_seed})
    # Pass 2: deepen with non-reference seeds on the same ranked layout order.
    for seed in remaining_seeds:
        for nc in nc_library:
            tasks.append({"nc": list(nc), "seed_name": str(seed["name"]), "seed": seed})
    return tasks


def apply_probe_reference_gate(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    tried: set,
    search_results: List[Dict[str, object]],
    requested_idx: int,
) -> Tuple[int, Optional[Dict[str, object]]]:
    min_required = max(0, int(getattr(args, "min_probe_reference_runs", 0)))
    if min_required <= 0:
        return requested_idx, None

    total_reference_tasks = len(ranked_reference_indices(tasks))
    if total_reference_tasks <= 0:
        return requested_idx, None

    required = min(min_required, total_reference_tasks)
    completed = reference_probe_runs_completed(search_results)
    if completed >= required:
        return requested_idx, None

    requested_task = tasks[requested_idx]
    if is_reference_seed_name(requested_task.get("seed_name")):
        return requested_idx, None

    forced_idx = first_untried_reference_index(tasks, tried)
    if forced_idx is None:
        return requested_idx, {
            "applied": False,
            "reason": (
                f"Probe gate active ({completed}/{required}) but no untried reference task remains; "
                "cannot enforce further reference probing."
            ),
            "completed_reference_runs": completed,
            "required_reference_runs": required,
        }

    forced_task = tasks[forced_idx]
    return forced_idx, {
        "applied": True,
        "reason": (
            f"Probe gate enforced: completed_reference_runs={completed}/{required}. "
            f"Blocked non-reference seed '{requested_task.get('seed_name')}' and forced reference probe."
        ),
        "completed_reference_runs": completed,
        "required_reference_runs": required,
        "requested_task": requested_task,
        "forced_task": forced_task,
    }


def probe_reference_runs_required(args: argparse.Namespace, tasks: List[Dict[str, object]]) -> int:
    total_reference_tasks = len(ranked_reference_indices(tasks))
    if total_reference_tasks <= 0:
        return 0
    return min(max(0, int(getattr(args, "min_probe_reference_runs", 0))), total_reference_tasks)


def search_execution_policy(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    search_results: List[Dict[str, object]],
    task: Dict[str, object],
) -> Dict[str, object]:
    required = probe_reference_runs_required(args, tasks)
    completed = reference_probe_runs_completed(search_results)
    low_fidelity_enabled = bool(int(getattr(args, "probe_low_fidelity_enabled", 1)))
    probe_phase_active = required > 0 and completed < required

    policy: Dict[str, object] = {
        "probe_phase_active": probe_phase_active,
        "completed_reference_runs": completed,
        "required_reference_runs": required,
        "low_fidelity_enabled": low_fidelity_enabled,
    }
    if not probe_phase_active:
        if not bool(int(getattr(args, "finalization_hard_gate_enabled", 1))):
            return policy
        if is_reference_seed_name(task.get("seed_name")):
            return policy
        nc = tuple(task.get("nc", []))
        if has_low_fidelity_optimization_evidence_for_nc(args, search_results, nc):
            return policy
        limits = low_fidelity_limits(args)
        policy["fidelity_override"] = {
            "nfex": limits["nfex"],
            "nfet": limits["nfet"],
            "ncp": limits["ncp"],
        }
        policy["reason"] = (
            "Finalization hard gate precheck: forcing first non-reference optimization for this NC "
            f"to low-fidelity (nfex={limits['nfex']}, nfet={limits['nfet']}, ncp={limits['ncp']}) "
            "before expensive final optimization is allowed."
        )
        return policy
    if not low_fidelity_enabled:
        policy["reason"] = "Probe phase active, but low-fidelity override is disabled."
        return policy
    if not is_reference_seed_name(task.get("seed_name")):
        policy["reason"] = "Probe phase active, waiting for required reference runs before non-reference seeds."
        return policy

    policy["fidelity_override"] = {
        "nfex": max(1, int(getattr(args, "probe_nfex", 5))),
        "nfet": max(1, int(getattr(args, "probe_nfet", 2))),
        "ncp": max(1, int(getattr(args, "probe_ncp", 1))),
    }
    policy["reason"] = (
        f"Probe phase reference run {completed + 1}/{required}: forcing low-fidelity "
        f"(nfex={policy['fidelity_override']['nfex']}, "
        f"nfet={policy['fidelity_override']['nfet']}, "
        f"ncp={policy['fidelity_override']['ncp']})."
    )
    return policy


def executive_forced_index(
    tasks: List[Dict[str, object]],
    tried: set,
    top_k_lock: int,
) -> Tuple[int, str]:
    ref_idx = ranked_reference_indices(tasks)
    top_ref = ref_idx[: max(1, top_k_lock)]
    for idx in top_ref:
        task = tasks[idx]
        key = (tuple(task["nc"]), str(task["seed_name"]))
        if key not in tried:
            return idx, "first untried reference task inside executive top-k lock."
    for idx in ref_idx:
        task = tasks[idx]
        key = (tuple(task["nc"]), str(task["seed_name"]))
        if key not in tried:
            return idx, "first untried reference task after top-k lock exhausted."
    idx = deterministic_select(tasks, tried)
    return idx, "fallback to first untried task because all reference tasks are exhausted."


def executive_controller_decide(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    tried: set,
    candidate_idx: int,
    candidate_task: Dict[str, object],
    b_note: Dict[str, object],
    search_results: List[Dict[str, object]],
    consecutive_rejects: int,
    debate_round: int = 0,
) -> Dict[str, object]:
    """
    Enhanced Executive Controller with immediate decision-making and debate round limits.

    Args:
        debate_round: Current debate round (0 = initial decision, 1 = first debate, 2 = final round)

    Returns:
        Executive decision with immediate action or debate continuation directive
    """
    decision = str(b_note.get("decision", "")).lower()

    # Immediate decision after Scientist B judgment
    if decision == "approve":
        return {
            "decision": "not_needed",
            "reason": "Scientist_B approved candidate; executive override not needed.",
            "priority_updates": [],
            "immediate_action": True,
            "debate_round": debate_round,
        }

    if not bool(args.executive_controller_enabled):
        return {
            "decision": "disabled",
            "reason": "Executive controller disabled by configuration.",
            "priority_updates": [],
            "immediate_action": True,
            "debate_round": debate_round,
        }

    # Check if we've reached maximum debate rounds
    if debate_round >= 2:
        return {
            "decision": "final_decision",
            "reason": f"Maximum debate rounds ({debate_round}) reached. Making final executive decision.",
            "priority_updates": ["Maximum debate rounds exhausted - executive must decide now."],
            "immediate_action": True,
            "debate_round": debate_round,
            "max_debates_reached": True,
        }

    # If feasible baseline exists, respect Scientist B's rejection
    if has_any_feasible(search_results):
        return {
            "decision": "respect_reject",
            "reason": "Feasible baseline exists; keep scientist rejection in effect.",
            "priority_updates": [],
            "immediate_action": True,
            "debate_round": debate_round,
        }

    # Check consecutive rejection conditions
    if consecutive_rejects < int(args.executive_trigger_rejects):
        return {
            "decision": "respect_reject",
            "reason": f"Consecutive rejects={consecutive_rejects} below trigger={int(args.executive_trigger_rejects)}.",
            "priority_updates": [],
            "immediate_action": True,
            "debate_round": debate_round,
        }

    if consecutive_rejects < int(args.executive_force_after_rejects):
        return {
            "decision": "respect_reject",
            "reason": (
                f"Consecutive rejects reached trigger ({consecutive_rejects} >= {int(args.executive_trigger_rejects)}), "
                f"but below force_after={int(args.executive_force_after_rejects)}."
            ),
            "priority_updates": [
                "Executive warning: next reject may force top-priority diagnostic execution."
            ],
            "immediate_action": True,
            "debate_round": debate_round,
        }

    # Executive override conditions met - force execution
    forced_idx, forced_reason = executive_forced_index(tasks, tried, int(args.executive_top_k_lock))
    forced_task = tasks[forced_idx]
    forced_key = (tuple(forced_task["nc"]), str(forced_task["seed_name"]))

    if forced_key in tried:
        return {
            "decision": "respect_reject",
            "reason": "No untried executive-forced task available; respecting rejection.",
            "priority_updates": [],
            "immediate_action": True,
            "debate_round": debate_round,
        }

    return {
        "decision": "override_execute",
        "reason": (
            f"Hard controller override: no feasible baseline and consecutive rejects={consecutive_rejects} "
            f"(trigger={int(args.executive_trigger_rejects)}). Force execution of top-priority reference candidate."
        ),
        "forced_candidate_index": forced_idx,
        "forced_task": forced_task,
        "forced_reason": forced_reason,
        "priority_updates": [
            "Executive override executed to break reject loop and establish feasibility baseline.",
            "Run top-ranked reference candidates before additional NC rotation.",
        ],
        "immediate_action": True,
        "debate_round": debate_round,
        "executive_override_executed": True,
    }


def deterministic_review(candidate: Dict[str, object], best_result: Optional[Dict[str, object]]) -> Dict[str, object]:
    if best_result and candidate["nc"] == best_result.get("nc") and candidate["seed_name"] == best_result.get("seed_name"):
        return {
            "decision": "reject",
            "reason": "Already evaluated this layout and seed.",
            "comparison_assessment": [
                f"Compared against best prior run {best_result.get('run_name')} with same nc/seed; this would be a duplicate."
            ],
            "nc_strategy_assessment": [
                "Candidate does not improve NC coverage because this nc/seed pair is already evaluated."
            ],
            "compute_assessment": "Reject duplicate to preserve budget for unexplored NC layouts and seeds.",
            "priority_updates": ["Avoid duplicate nc/seed evaluations unless bounds or fidelity changed."],
            "counterarguments": ["No new evidence is provided for a duplicate nc/seed attempt."],
            "risk_flags": ["Wasted budget on duplicate search point."],
            "required_checks": ["Only retry duplicates when bounds/fidelity or solver stack changed."],
        }
    return {
        "decision": "approve",
        "reason": "Candidate is within current bounds and still untested.",
        "comparison_assessment": [
            "Compared candidate against tried set and current best run; this nc/seed has not been executed yet."
        ],
        "nc_strategy_assessment": [
            "Candidate expands NC/seed evidence coverage and can improve ranking confidence across layout alternatives."
        ],
        "compute_assessment": "Approve as a bounded, untried point with acceptable incremental budget impact.",
        "priority_updates": ["Continue feasibility-first screening, then rank by productivity among low-violation runs."],
        "counterarguments": ["Approval is provisional until solver status and post-check metrics are reviewed."],
        "risk_flags": ["Potential local infeasibility despite bounded flows."],
        "required_checks": ["Confirm effective post-bounds flow vector and solver termination condition."],
    }


def single_scientist_policy_review(candidate: Dict[str, object], best_result: Optional[Dict[str, object]]) -> Dict[str, object]:
    review = deterministic_review(candidate, best_result)
    review = dict(review)
    review["mode"] = "single_scientist_policy"
    review["reason"] = (
        "Scientist_B bypassed by single-scientist mode. "
        + str(review.get("reason", "")).strip()
    ).strip()
    updates = normalize_text_list(review.get("priority_updates"), max_items=8)
    updates.append("Single-scientist mode active: using deterministic policy gate instead of LLM review.")
    review["priority_updates"] = normalize_text_list(updates, max_items=8)
    return review


def check_systematic_infeasibility(results: List[Dict[str, object]], k: int) -> Dict[str, object]:
    window = max(1, int(k))
    recent = results[-window:]
    if len(recent) < window:
        return {
            "triggered": False,
            "window": window,
            "recent_count": len(recent),
            "bad_count": 0,
            "reason": "Not enough recent results to assess systematic infeasibility.",
        }
    bad_entries: List[str] = []
    for item in recent:
        status = str(item.get("status", "")).strip().lower()
        feasible = bool(item.get("feasible"))
        bad_status = status in {"solver_error", "infeasible", "failed", "error", "other"}
        high_violation = effective_violation(item) >= 1e-3
        if (not feasible) or bad_status or high_violation:
            bad_entries.append(
                f"run={item.get('run_name')} status={item.get('status')} feasible={item.get('feasible')} viol={effective_violation(item):.6g}"
            )
    triggered = len(bad_entries) >= window
    return {
        "triggered": triggered,
        "window": window,
        "recent_count": len(recent),
        "bad_count": len(bad_entries),
        "bad_entries": bad_entries,
        "reason": (
            f"Systematic infeasibility trigger fired across the last {window} results."
            if triggered
            else f"Systematic infeasibility trigger not met ({len(bad_entries)}/{window} bad results in the rolling window)."
        ),
    }


def physics_informed_select(
    tasks: List[Dict[str, object]],
    tried: set,
    results: List[Dict[str, object]],
    *,
    best_result: Optional[Dict[str, object]] = None,
    preferred_nc: Optional[Sequence[int]] = None,
    preferred_seed_name: Optional[str] = None,
    reason: str = "",
) -> Tuple[int, Dict[str, object]]:
    remaining: List[Tuple[int, Dict[str, object]]] = []
    for idx, task in enumerate(tasks):
        key = (tuple(task["nc"]), str(task["seed_name"]))
        if key not in tried:
            remaining.append((idx, task))
    if not remaining:
        idx = deterministic_select(tasks, tried)
        return idx, {
            "mode": "physics_informed_fallback",
            "reason": "No untried task remains; falling back to deterministic selection.",
        }

    preferred_nc_tuple = tuple(int(v) for v in preferred_nc) if preferred_nc is not None else None
    best_nc_tuple = tuple(best_result.get("nc", [])) if isinstance(best_result, dict) else None
    recent_bad_ncs = [
        tuple(item.get("nc", []))
        for item in results[-3:]
        if isinstance(item, dict) and (
            not bool(item.get("feasible"))
            or str(item.get("status", "")).strip().lower() in {"solver_error", "infeasible", "failed", "error", "other"}
        )
    ]

    def score(item: Dict[str, object]) -> float:
        nc = tuple(item.get("nc", []))
        score_value = nc_prior_score(nc)
        if preferred_nc_tuple is not None and nc == preferred_nc_tuple:
            score_value += 250.0
        if best_nc_tuple is not None and nc == best_nc_tuple:
            score_value += 125.0
        if nc in recent_bad_ncs:
            score_value += 90.0
        if is_reference_seed_name(item.get("seed_name")):
            score_value += 60.0
        if preferred_seed_name and str(item.get("seed_name", "")) == str(preferred_seed_name):
            score_value += 35.0
        if any(
            tuple(result.get("nc", [])) == nc and str(result.get("seed_name", "")) == str(item.get("seed_name", ""))
            for result in results
        ):
            score_value -= 10.0
        return score_value

    ranked = sorted(remaining, key=lambda entry: score(entry[1]), reverse=True)
    idx, task = ranked[0]
    selected_score = score(task)
    return idx, {
        "mode": "physics_informed",
        "reason": reason or "Physics-informed selection chose the highest-scoring untried diagnostic task.",
        "selected_nc": list(task.get("nc", [])),
        "selected_seed_name": str(task.get("seed_name", "")),
        "score": selected_score,
        "recent_bad_ncs": [list(nc) for nc in recent_bad_ncs],
    }
