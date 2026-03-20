# SMB Optimization Objectives

## Maximize

```
productivity_ex_ga_ma = (CE_GA + CE_MA) * UE * area * eb
```

No chemistry or hardware redesign. Optimize only operating variables and layout.

## Hard Constraints (non-negotiable)

| Constraint | Threshold |
|---|---|
| `purity_ex_meoh_free` | ≥ 0.60 |
| `recovery_ex_GA` | ≥ 0.75 |
| `recovery_ex_MA` | ≥ 0.75 |
| `F1 = Fdes + Fex` | ±1% mass balance |
| `F1 = Ffeed + Fraf` | ±1% mass balance |
| All flows > 0 | strict positivity |

Any candidate that violates mass balance or cannot plausibly reach these targets is infeasible — reject it before running.

## Decision Variables

Optimize: `nc`, `F1`, `Fdes`, `Fex`, `Ffeed`, `tstep`

Derived (not a free variable): `Fraf = F1 − Ffeed`

## Flow Bounds (runtime-configurable defaults)

- `0.5 ≤ Ffeed ≤ 2.5` mL/min
- `Fdes, Fex ≤ 2.5` mL/min (max pump flow)
- `Fraf ≤ 5.0` mL/min (raffinate pump cap)
- `F1 ≤ 5.0` mL/min

## NC Layout

- Total columns: **8** (fixed hardware)
- `nc = (Z1, Z2, Z3, Z4)` where `sum(nc) = 8`, all zones ≥ 1
- Reference layout: `nc = (1, 2, 3, 2)`

## Feed and Desorbent Chemistry

Kraton feed (mass fractions): `wt0 = (GA=0.003, MA=0.004, Water=0.990, MeOH=0.003)`

Feed concentration: `CF = wt0 / sum(wt0 / rho)` where `rho = (1.5, 1.6, 1.0, 0.79) g/mL`

Desorbent: pure MeOH `(0, 0, 0, 1)` mass fraction

## Fidelity Ladder

| Level | nfex | nfet | ncp | Use |
|---|---|---|---|---|
| Low | 4–5 | 2 | 1 | Layout screening, first feasibility |
| Medium | 6 | 3 | 2 | Candidate refinement |
| High | 10 | 5 | 2 | Final validation only |

Never jump from low to high directly. A high-fidelity run is only justified if a low-fidelity feasible result already exists for that `nc`.

## Required Search Workflow

1. **Screen** — cover all NC layouts with reference seed at low fidelity
2. **Rank** — compare productivity/purity/recovery/violation across layouts
3. **Refine** — perturb flows around top feasible candidates at medium fidelity
4. **Validate** — promote best candidate to high fidelity; confirm all constraints met
5. **Claim** — report only results with high-fidelity evidence

## Simulation Priority Order

1. Reduce `normalized_total_violation` (feasibility first)
2. Meet quality constraints (`purity`, `recovery_GA`, `recovery_MA`)
3. Maximize `productivity_ex_ga_ma` inside the feasible region

## Mandatory Evidence per Iteration

Every proposal must include:

- numeric comparison vs at least one prior run (productivity, purity, recovery, violation)
- flow deltas: `ΔFfeed, ΔF1, ΔFdes, ΔFex, ΔFraf, Δtstep`
- topology deltas: `ΔZ1, ΔZ2, ΔZ3, ΔZ4`
- explicit physics rationale (zone I–IV mechanics, selectivity, mass balance)

Generic text without run-name references and numeric values is rejected.
