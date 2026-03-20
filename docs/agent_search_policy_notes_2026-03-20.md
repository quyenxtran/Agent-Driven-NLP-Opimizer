# Agent Search Policy Notes

Date: 2026-03-20

## Summary

The outer agent loop was updated so it no longer behaves like a global one-reference gate followed by topology hopping. It now:

1. Screens each NC with an adaptive `3-4` seed bundle.
2. Continues on the same NC when a run is near-feasible but not yet feasible.
3. Only forces diagnostic recovery for hard-bad windows, not near-boundary runs.
4. Uses phase-aware IPOPT settings during screening and continuation.

## Main Behavioral Changes

### 1. Per-NC adaptive screening

Search tasks are now organized by NC screening phase first, then deeper optimization.

- Minimum screening runs per NC: `3`
- Maximum screening runs per NC: `4`
- The 4th screening run is only required when the first 3 runs do not establish:
  - a feasible result, or
  - a near-feasible anchor

This makes the screening count autonomous without relying on free-form LLM reasoning.

### 2. Near-feasible continuation

If there is no feasible run yet, but a run has:

- very small `normalized_total_violation`
- purity/recovery close to thresholds

then the next task is chosen deterministically from the same NC before the loop switches topology.

This is intended to keep the search near the low-violation basin instead of discarding it.

### 3. Diagnostic trigger refinement

Systematic infeasibility no longer treats all `feasible=False` runs equally.

Near-feasible boundary runs are excluded from the hard-bad count used to trigger diagnostic forcing.

This prevents sequences of tiny-violation boundary misses from being misclassified as catastrophic failure.

### 4. Phase-aware solver settings

`search_execution_policy` can now emit `solver_override` alongside `fidelity_override`.

The intended profiles are:

- Screening phase: lower-fidelity and relaxed tolerances for fast coarse evidence
- Near-feasible continuation: slightly looser tolerances plus more iterations
- Finalization hard-gate: low-fidelity precheck before expensive final optimization

## New/Relevant Runtime Knobs

### Screening control

- `SMB_SCREENING_RUNS_MIN_PER_NC`
- `SMB_SCREENING_RUNS_MAX_PER_NC`
- `SMB_SCREENING_RUNS_PER_NC`

Notes:

- `SMB_SCREENING_RUNS_PER_NC` now acts as the default max if the explicit max is not set.
- Recommended default range is `3-4`.

### Near-feasible continuation

- `SMB_NEAR_FEASIBLE_VIOLATION_THRESHOLD`
- `SMB_NEAR_FEASIBLE_PURITY_SLACK`
- `SMB_NEAR_FEASIBLE_RECOVERY_SLACK`

Recommended starting values:

- `SMB_NEAR_FEASIBLE_VIOLATION_THRESHOLD=1e-5`
- `SMB_NEAR_FEASIBLE_PURITY_SLACK=0.005`
- `SMB_NEAR_FEASIBLE_RECOVERY_SLACK=0.005`

### Solver override profiles

#### Screening phase

- `SMB_SCREENING_IPOPT_MAX_ITER`
- `SMB_SCREENING_IPOPT_TOL`
- `SMB_SCREENING_IPOPT_ACCEPTABLE_TOL`

Recommended starting values:

- `SMB_SCREENING_IPOPT_MAX_ITER=800`
- `SMB_SCREENING_IPOPT_TOL=1e-4`
- `SMB_SCREENING_IPOPT_ACCEPTABLE_TOL=1e-3`

#### Near-feasible continuation

- `SMB_NEAR_FEASIBLE_IPOPT_MAX_ITER`
- `SMB_NEAR_FEASIBLE_IPOPT_TOL`
- `SMB_NEAR_FEASIBLE_IPOPT_ACCEPTABLE_TOL`

Recommended starting values:

- `SMB_NEAR_FEASIBLE_IPOPT_MAX_ITER=1500`
- `SMB_NEAR_FEASIBLE_IPOPT_TOL=5e-5`
- `SMB_NEAR_FEASIBLE_IPOPT_ACCEPTABLE_TOL=5e-4`

#### Finalization hard-gate

- `SMB_FINALIZATION_IPOPT_MAX_ITER`
- `SMB_FINALIZATION_IPOPT_TOL`
- `SMB_FINALIZATION_IPOPT_ACCEPTABLE_TOL`

Recommended starting values:

- `SMB_FINALIZATION_IPOPT_MAX_ITER=1000`
- `SMB_FINALIZATION_IPOPT_TOL=1e-4`
- `SMB_FINALIZATION_IPOPT_ACCEPTABLE_TOL=1e-3`

## Practical Interpretation

The search loop should now behave more like:

1. Screen each NC with 3 runs.
2. Add a 4th only if that NC still lacks a promising anchor.
3. If a near-feasible basin appears, keep optimizing around that NC first.
4. Only escalate to diagnostic forcing when the recent window is genuinely hard-bad.

## Validation Status

Implemented and validated with:

- `python -m py_compile benchmarks/agent_policy.py benchmarks/agent_runner.py tests/test_agent_logic.py tests/test_module_split.py`
- `python -m pytest -q`

Current result at implementation time:

- `185 passed, 5 skipped`
