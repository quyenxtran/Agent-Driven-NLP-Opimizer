# Problem Definition

## Core Question

Find a high-productivity, feasible SMB operating point for Kraton feed under a fixed compute budget, using a reproducible search policy.

## Optimization Problem

**Objective:** maximize `productivity_ex_ga_ma`

**Hard constraints:**
- `purity_ex_meoh_free ≥ 0.60`
- `recovery_ex_GA ≥ 0.75`
- `recovery_ex_MA ≥ 0.75`
- flow mass balance: `F1 = Fdes + Fex = Ffeed + Fraf` (±1%)
- all flows within declared pump limits
- `nc` layout admissible: `sum(nc) = 8`, all zones ≥ 1

**Decision variables:** `nc`, `Ffeed`, `F1`, `Fdes`, `Fex`, `tstep`

**Derived:** `Fraf = F1 − Ffeed` (not independently optimized)

## Problem Type

- Fixed `nc` → large nonconvex NLP
- Variable `nc` → mixed discrete + continuous search

A global optimum is not guaranteed with local NLP solvers (IPOPT). The target is the best validated solution found under finite budget.

## Search Philosophy

**Feasibility first, optimization second, validation last.**

Do not exploit a region that has never produced a feasible run. Do not commit to high-fidelity evaluation without low-fidelity evidence. Do not claim a result without high-fidelity validation.

## Fixed-Budget Rule

Respect the job's exported time budget. Reserve validation budget (≈ final 20–25%) for high-fidelity confirmation. Do not spend validation runs during early screening.

## Benchmark Fairness

Hold constant across all methods compared:
- model and feed chemistry
- NC library
- flow bounds and quality constraints
- final high-fidelity validator (nfex=10, nfet=5, ncp=2)

Compare methods by:
- feasibility rate (fraction of runs producing feasible result)
- best validated `productivity_ex_ga_ma`
- evaluations and wall time to first feasible solution
- robustness of final operating point (sensitivity to small flow perturbations)

## Minimum Evidence for a Final Claim

A result is claimable only when all of the following exist:

1. High-fidelity run (`nfex=10, nfet=5, ncp=2`) that is feasible with all constraints met
2. Numeric comparison to at least two competitor runs (different `nc` or seed)
3. Explicit discussion of the nearest failure mode (what change breaks feasibility)
4. Reproducibility metadata: run name, solver profile, SQLite record, artifact path

## Bottom Line

Feasibility first → constraint satisfaction → productivity maximization → validated claim.
