from __future__ import annotations

import argparse
import re
from typing import Dict, List, Optional, Sequence, Tuple

from . import run_stage as rs
from .agent_results import (
    deterministic_select,
    effective_violation,
    has_metric_evidence,
    has_any_feasible,
    is_reference_seed_name,
    low_fidelity_limits,
    has_low_fidelity_optimization_evidence_for_nc,
    ranked_reference_indices,
    reference_probe_runs_completed,
    first_untried_reference_index,
    safe_result_metric,
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


def screening_run_bounds(args: argparse.Namespace, seed_count: int) -> Tuple[int, int]:
    requested_max = int(
        getattr(
            args,
            "screening_runs_max_per_nc",
            getattr(args, "screening_runs_per_nc", 4),
        )
    )
    requested_min = int(
        getattr(
            args,
            "screening_runs_min_per_nc",
            max(3, min(int(getattr(args, "min_probe_reference_runs", 3) or 3), requested_max or 4)),
        )
    )
    requested_max = max(1, min(requested_max if requested_max > 0 else 4, max(1, seed_count)))
    requested_min = max(1, min(requested_min if requested_min > 0 else min(3, requested_max), requested_max))
    return requested_min, requested_max


def _seed_priority(seed_name: object) -> int:
    name = str(seed_name or "").strip().lower()
    order = {
        "reference": 0,
        "optimized_a_minus": 1,
        "optimized_c": 2,
        "optimized_a": 3,
        "optimized_b": 4,
        "optimized_a_plus": 5,
        "optimized_2f1": 6,
        "optimized_2f2": 7,
    }
    return order.get(name, 100)


def screening_seed_names(tasks: List[Dict[str, object]]) -> List[str]:
    names: List[str] = []
    seen: set[str] = set()
    for task in tasks:
        if not bool(task.get("screening_seed")):
            continue
        name = str(task.get("seed_name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def task_is_screening_seed(task: Dict[str, object]) -> bool:
    return bool(task.get("screening_seed"))


def screening_targets_by_nc(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    results: Optional[List[Dict[str, object]]] = None,
) -> Dict[Tuple[int, ...], int]:
    grouped: Dict[Tuple[int, ...], int] = {}
    for task in tasks:
        if not task_is_screening_seed(task):
            continue
        nc = tuple(int(v) for v in task.get("nc", []))
        grouped[nc] = grouped.get(nc, 0) + 1
    required: Dict[Tuple[int, ...], int] = {}
    screening_names = screening_seed_names(tasks)
    for nc, count in grouped.items():
        min_runs, max_runs = screening_run_bounds(args, count)
        if not results:
            required[nc] = min_runs
            continue
        nc_results = [
            item
            for item in results
            if tuple(int(v) for v in item.get("nc", [])) == nc
            and str(item.get("seed_name", "")).strip() in set(screening_names)
        ]
        established_promising_anchor = any(bool(item.get("feasible")) or result_is_near_feasible(args, item) for item in nc_results)
        required[nc] = min_runs if established_promising_anchor else max_runs
    return required


def screening_runs_completed_for_nc(
    results: List[Dict[str, object]],
    nc: Sequence[int],
    screening_names: Sequence[str],
) -> int:
    nc_tuple = tuple(int(v) for v in nc)
    screening_lookup = {str(name).strip() for name in screening_names}
    return sum(
        1
        for item in results
        if tuple(int(v) for v in item.get("nc", [])) == nc_tuple
        and str(item.get("seed_name", "")).strip() in screening_lookup
    )


def first_untried_screening_index(
    tasks: List[Dict[str, object]],
    tried: set,
    *,
    nc: Optional[Sequence[int]] = None,
) -> Optional[int]:
    target_nc = tuple(int(v) for v in nc) if nc is not None else None
    for idx, task in enumerate(tasks):
        if not task_is_screening_seed(task):
            continue
        task_nc = tuple(int(v) for v in task.get("nc", []))
        if target_nc is not None and task_nc != target_nc:
            continue
        key = (task_nc, str(task.get("seed_name", "")))
        if key not in tried:
            return idx
    return None


def screening_phase_state(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    results: List[Dict[str, object]],
) -> Dict[str, object]:
    required_by_nc = screening_targets_by_nc(args, tasks, results)
    names = screening_seed_names(tasks)
    progress: Dict[Tuple[int, ...], Dict[str, int]] = {}
    incomplete: List[Tuple[int, ...]] = []
    for nc, required in required_by_nc.items():
        completed = screening_runs_completed_for_nc(results, nc, names)
        progress[nc] = {"completed": completed, "required": required}
        if completed < required:
            incomplete.append(nc)
    return {
        "screening_seed_names": names,
        "required_by_nc": required_by_nc,
        "progress": progress,
        "incomplete_ncs": incomplete,
        "active": bool(incomplete),
    }


def result_is_near_feasible(args: argparse.Namespace, result: Dict[str, object]) -> bool:
    if not has_metric_evidence(result):
        return False
    violation = effective_violation(result)
    if violation > float(getattr(args, "near_feasible_violation_threshold", 1e-5)):
        return False
    purity = safe_result_metric(result, "purity_ex_meoh_free")
    rga = safe_result_metric(result, "recovery_ex_GA")
    rma = safe_result_metric(result, "recovery_ex_MA")
    purity_slack = float(getattr(args, "near_feasible_purity_slack", 5e-3))
    recovery_slack = float(getattr(args, "near_feasible_recovery_slack", 5e-3))
    if purity is not None and purity + purity_slack < float(getattr(args, "purity_min", 0.6)):
        return False
    if rga is not None and rga + recovery_slack < float(getattr(args, "recovery_ga_min", 0.75)):
        return False
    if rma is not None and rma + recovery_slack < float(getattr(args, "recovery_ma_min", 0.75)):
        return False
    return True


def near_feasible_continuation_select(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    tried: set,
    results: List[Dict[str, object]],
) -> Tuple[Optional[int], Optional[Dict[str, object]]]:
    if has_any_feasible(results):
        return None, None
    phase_state = screening_phase_state(args, tasks, results)
    if bool(phase_state.get("active")):
        return None, None
    candidates = [item for item in results if result_is_near_feasible(args, item)]
    if not candidates:
        return None, None
    candidates.sort(
        key=lambda item: (
            float(safe_result_metric(item, "productivity_ex_ga_ma") or float("-inf")),
            float(safe_result_metric(item, "purity_ex_meoh_free") or float("-inf")),
            float(safe_result_metric(item, "recovery_ex_GA") or float("-inf")),
            float(safe_result_metric(item, "recovery_ex_MA") or float("-inf")),
            -effective_violation(item),
        ),
        reverse=True,
    )
    anchor = candidates[0]
    anchor_nc = tuple(int(v) for v in anchor.get("nc", []))
    same_nc_remaining: List[Tuple[int, Dict[str, object]]] = []
    for idx, task in enumerate(tasks):
        task_nc = tuple(int(v) for v in task.get("nc", []))
        key = (task_nc, str(task.get("seed_name", "")))
        if key in tried or task_nc != anchor_nc:
            continue
        same_nc_remaining.append((idx, task))
    if not same_nc_remaining:
        return None, None
    same_nc_remaining.sort(
        key=lambda entry: (
            0 if not bool(entry[1].get("screening_seed")) else 1,
            _seed_priority(entry[1].get("seed_name")),
            entry[0],
        )
    )
    idx, task = same_nc_remaining[0]
    note = {
        "mode": "near_feasible_continuation",
        "decision": "near_feasible_continue",
        "reason": (
            f"Near-feasible continuation selected for nc={list(anchor_nc)} after "
            f"violation={effective_violation(anchor):.6g} with no feasible result yet."
        ),
        "anchor_run_name": str(anchor.get("run_name", "")),
        "anchor_nc": list(anchor_nc),
        "anchor_seed_name": str(anchor.get("seed_name", "")),
        "selected_seed_name": str(task.get("seed_name", "")),
        "acquisition_type": "VERIFY",
        "priority_updates": [
            "Hold topology constant and continue around the best near-feasible basin before switching NC."
        ],
    }
    return idx, note


def solver_override_from_env(
    prefix: str,
    *,
    default_max_iter: int,
    default_tol: float,
    default_acceptable_tol: float,
    default_max_solve_seconds: float,
) -> Dict[str, object]:
    return {
        "max_iter": int(env_or_default(f"{prefix}_MAX_ITER", str(default_max_iter))),
        "tol": float(env_or_default(f"{prefix}_TOL", str(default_tol))),
        "acceptable_tol": float(env_or_default(f"{prefix}_ACCEPTABLE_TOL", str(default_acceptable_tol))),
        "max_solve_seconds": float(
            env_or_default(f"{prefix}_MAX_SOLVE_SECONDS", str(default_max_solve_seconds))
        ),
    }


def screening_bundle_indices(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    tried: set,
    search_results: List[Dict[str, object]],
    selected_idx: int,
) -> List[int]:
    if selected_idx < 0 or selected_idx >= len(tasks):
        return []
    selected_task = tasks[selected_idx]
    if not task_is_screening_seed(selected_task):
        return []
    phase_state = screening_phase_state(args, tasks, search_results)
    if not bool(phase_state.get("active")):
        return []
    selected_nc = tuple(int(v) for v in selected_task.get("nc", []))
    progress = dict(phase_state.get("progress", {}))
    required = int(dict(phase_state.get("required_by_nc", {})).get(selected_nc, 0))
    completed = int(progress.get(selected_nc, {}).get("completed", 0))
    remaining = max(0, required - completed)
    if remaining <= 0:
        return []

    candidates: List[Tuple[int, int, int]] = []
    for idx, task in enumerate(tasks):
        if not task_is_screening_seed(task):
            continue
        task_nc = tuple(int(v) for v in task.get("nc", []))
        if task_nc != selected_nc:
            continue
        key = (task_nc, str(task.get("seed_name", "")))
        if key in tried:
            continue
        screening_rank = task.get("screening_rank")
        candidates.append(
            (
                int(screening_rank) if screening_rank is not None else 999,
                _seed_priority(task.get("seed_name")),
                idx,
            )
        )
    candidates.sort()
    bundle = [idx for _, _, idx in candidates[:remaining]]
    if selected_idx in bundle:
        return bundle
    return ([selected_idx] + bundle)[:remaining]


def build_search_tasks(args: argparse.Namespace) -> List[Dict[str, object]]:
    nc_library = rs.parse_nc_library(args.nc_library)
    nc_library = sorted(nc_library, key=nc_prior_score, reverse=True)
    seed_library = rs.parse_seed_library(args.seed_library)
    if not seed_library:
        return []

    ordered_seeds = sorted(
        [dict(seed) for seed in seed_library],
        key=lambda seed: (_seed_priority(seed.get("name")), str(seed.get("name", ""))),
    )
    _min_runs, screening_count = screening_run_bounds(args, len(ordered_seeds))
    screening_seeds = ordered_seeds[:screening_count]
    remaining_seeds = ordered_seeds[screening_count:]
    tasks: List[Dict[str, object]] = []
    # Pass 1: screen each NC with 3-4 deterministic seeds before deeper optimization.
    for rank, seed in enumerate(screening_seeds):
        for nc in nc_library:
            tasks.append(
                {
                    "nc": list(nc),
                    "seed_name": str(seed["name"]),
                    "seed": seed,
                    "screening_seed": True,
                    "screening_rank": rank,
                }
            )
    # Pass 2: deepen only after each NC has enough screening evidence.
    for seed in remaining_seeds:
        for nc in nc_library:
            tasks.append(
                {
                    "nc": list(nc),
                    "seed_name": str(seed["name"]),
                    "seed": seed,
                    "screening_seed": False,
                    "screening_rank": None,
                }
            )
    return tasks


def apply_probe_reference_gate(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    tried: set,
    search_results: List[Dict[str, object]],
    requested_idx: int,
) -> Tuple[int, Optional[Dict[str, object]]]:
    phase_state = screening_phase_state(args, tasks, search_results)
    if not bool(phase_state.get("active")):
        return requested_idx, None
    requested_task = tasks[requested_idx]
    requested_nc = tuple(int(v) for v in requested_task.get("nc", []))
    progress = dict(phase_state.get("progress", {}))
    required_by_nc = dict(phase_state.get("required_by_nc", {}))
    if task_is_screening_seed(requested_task):
        return requested_idx, None
    preferred_nc = requested_nc if requested_nc in set(phase_state.get("incomplete_ncs", [])) else None
    forced_idx = first_untried_screening_index(tasks, tried, nc=preferred_nc)
    if forced_idx is None:
        forced_idx = first_untried_screening_index(tasks, tried)
    if forced_idx is None:
        return requested_idx, {
            "applied": False,
            "reason": (
                "NC screening gate is active, but no untried screening task remains; "
                "cannot enforce further screening."
            ),
            "screening_progress": {
                ",".join(str(v) for v in nc): progress[nc] for nc in progress
            },
        }

    forced_task = tasks[forced_idx]
    forced_nc = tuple(int(v) for v in forced_task.get("nc", []))
    completed = int(progress.get(forced_nc, {}).get("completed", 0))
    required = int(required_by_nc.get(forced_nc, 0))
    return forced_idx, {
        "applied": True,
        "reason": (
            f"NC screening gate enforced for nc={list(forced_nc)}: "
            f"completed_screening_runs={completed}/{required}. "
            f"Blocked deeper seed '{requested_task.get('seed_name')}' and forced a screening run first."
        ),
        "completed_screening_runs": completed,
        "required_screening_runs": required,
        "requested_task": requested_task,
        "forced_task": forced_task,
    }


def probe_reference_runs_required(args: argparse.Namespace, tasks: List[Dict[str, object]]) -> int:
    required_by_nc = screening_targets_by_nc(args, tasks, [])
    if not required_by_nc:
        return 0
    return sum(int(value) for value in required_by_nc.values())


def search_execution_policy(
    args: argparse.Namespace,
    tasks: List[Dict[str, object]],
    search_results: List[Dict[str, object]],
    task: Dict[str, object],
) -> Dict[str, object]:
    phase_state = screening_phase_state(args, tasks, search_results)
    low_fidelity_enabled = bool(int(getattr(args, "probe_low_fidelity_enabled", 1)))
    probe_phase_active = bool(phase_state.get("active"))

    policy: Dict[str, object] = {
        "probe_phase_active": probe_phase_active,
        "screening_progress": {
            ",".join(str(v) for v in nc): stats for nc, stats in dict(phase_state.get("progress", {})).items()
        },
        "required_reference_runs": probe_reference_runs_required(args, tasks),
        "low_fidelity_enabled": low_fidelity_enabled,
    }
    if not probe_phase_active:
        if not bool(int(getattr(args, "finalization_hard_gate_enabled", 1))):
            if bool(task.get("continuation_priority")):
                policy["solver_override"] = solver_override_from_env(
                    "SMB_NEAR_FEASIBLE_IPOPT",
                    default_max_iter=1500,
                    default_tol=5e-5,
                    default_acceptable_tol=5e-4,
                    default_max_solve_seconds=600.0,
                )
                policy["reason"] = (
                    "Near-feasible continuation: relaxed solver tolerances and higher iteration budget "
                    "to stay in the current low-violation basin."
                )
            return policy
        if task_is_screening_seed(task):
            policy["solver_override"] = solver_override_from_env(
                "SMB_NEAR_FEASIBLE_IPOPT",
                default_max_iter=1500,
                default_tol=5e-5,
                default_acceptable_tol=5e-4,
                default_max_solve_seconds=600.0,
            )
            policy["reason"] = "Late screening task retained the near-feasible continuation solver profile."
            return policy
        nc = tuple(task.get("nc", []))
        if has_low_fidelity_optimization_evidence_for_nc(args, search_results, nc):
            if bool(task.get("continuation_priority")):
                policy["solver_override"] = solver_override_from_env(
                    "SMB_NEAR_FEASIBLE_IPOPT",
                    default_max_iter=1500,
                    default_tol=5e-5,
                    default_acceptable_tol=5e-4,
                    default_max_solve_seconds=600.0,
                )
                policy["reason"] = (
                    "Near-feasible continuation: low-fidelity gate already satisfied for this NC, "
                    "so keep the local continuation profile."
                )
            return policy
        limits = low_fidelity_limits(args)
        policy["fidelity_override"] = {
            "nfex": limits["nfex"],
            "nfet": limits["nfet"],
            "ncp": limits["ncp"],
        }
        policy["solver_override"] = solver_override_from_env(
            "SMB_FINALIZATION_IPOPT",
            default_max_iter=1000,
            default_tol=1e-4,
            default_acceptable_tol=1e-3,
            default_max_solve_seconds=600.0,
        )
        policy["reason"] = (
            "Finalization hard gate precheck: forcing first non-reference optimization for this NC "
            f"to low-fidelity (nfex={limits['nfex']}, nfet={limits['nfet']}, ncp={limits['ncp']}) "
            "before expensive final optimization is allowed."
        )
        return policy
    if not low_fidelity_enabled:
        policy["reason"] = "Probe phase active, but low-fidelity override is disabled."
        return policy
    if not task_is_screening_seed(task):
        policy["reason"] = "Probe phase active, waiting for required per-NC screening runs before deeper seeds."
        return policy

    policy["fidelity_override"] = {
        "nfex": max(1, int(getattr(args, "probe_nfex", 5))),
        "nfet": max(1, int(getattr(args, "probe_nfet", 2))),
        "ncp": max(1, int(getattr(args, "probe_ncp", 1))),
    }
    policy["solver_override"] = solver_override_from_env(
        "SMB_SCREENING_IPOPT",
        default_max_iter=800,
        default_tol=1e-4,
        default_acceptable_tol=1e-3,
        default_max_solve_seconds=180.0,
    )
    policy["reason"] = (
        "Probe phase screening task: forcing low-fidelity "
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


def check_systematic_infeasibility(
    results: List[Dict[str, object]],
    k: int,
    *,
    near_feasible_violation_threshold: float = 1e-5,
) -> Dict[str, object]:
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
    near_feasible_entries: List[str] = []
    for item in recent:
        status = str(item.get("status", "")).strip().lower()
        feasible = bool(item.get("feasible"))
        bad_status = status in {"solver_error", "infeasible", "failed", "error", "other"}
        violation = effective_violation(item)
        high_violation = violation >= 1e-3
        near_feasible = has_metric_evidence(item) and violation <= near_feasible_violation_threshold
        if near_feasible:
            near_feasible_entries.append(
                f"run={item.get('run_name')} status={item.get('status')} feasible={item.get('feasible')} viol={violation:.6g}"
            )
            continue
        if (not feasible) or bad_status or high_violation:
            bad_entries.append(
                f"run={item.get('run_name')} status={item.get('status')} feasible={item.get('feasible')} viol={violation:.6g}"
            )
    triggered = len(bad_entries) >= window
    return {
        "triggered": triggered,
        "window": window,
        "recent_count": len(recent),
        "bad_count": len(bad_entries),
        "bad_entries": bad_entries,
        "near_feasible_count": len(near_feasible_entries),
        "near_feasible_entries": near_feasible_entries,
        "reason": (
            f"Systematic infeasibility trigger fired across the last {window} results."
            if triggered
            else (
                f"Systematic infeasibility trigger not met ({len(bad_entries)}/{window} hard-bad results; "
                f"{len(near_feasible_entries)} near-feasible boundary runs excluded)."
            )
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
