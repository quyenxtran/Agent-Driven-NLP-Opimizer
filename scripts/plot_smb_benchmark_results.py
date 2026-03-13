#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot SMB benchmark results from JSON artifacts.")
    parser.add_argument(
        "--input-dirs",
        nargs="+",
        default=[
            str(REPO_ROOT / "artifacts" / "smb_stage_runs"),
            str(REPO_ROOT / "artifacts" / "agent_runs"),
        ],
    )
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "plots"))
    parser.add_argument("--prefix", default="smb_benchmark")
    return parser.parse_args()


def iter_json_files(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_file() and path.suffix.lower() == ".json":
            yield path
            continue
        for item in sorted(path.rglob("*.json")):
            yield item


def load_json(path: Path) -> Optional[Dict[str, object]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_metrics(payload: Dict[str, object]) -> Tuple[Optional[Dict[str, float]], bool]:
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        return ({k: float(v) for k, v in metrics.items()}, bool(payload.get("feasible")))
    provisional = payload.get("provisional")
    if isinstance(provisional, dict):
        provisional_metrics = provisional.get("metrics")
        if isinstance(provisional_metrics, dict):
            return ({k: float(v) for k, v in provisional_metrics.items()}, False)
    return None, False


def get_best_payload(artifact: Dict[str, object]) -> Optional[Dict[str, object]]:
    best = artifact.get("best_result")
    if isinstance(best, dict):
        return best
    if artifact.get("stage") in {"reference-eval", "solver-check"}:
        return artifact
    for key in ("ranked_results", "results", "search_results", "validation_results"):
        items = artifact.get(key)
        if isinstance(items, list):
            candidate_items = [item for item in items if isinstance(item, dict)]
            if not candidate_items:
                continue
            best_item = None
            best_score = None
            for item in candidate_items:
                metrics, validated = get_metrics(item)
                if metrics is None:
                    continue
                feasible = 1 if item.get("feasible") else 0
                productivity = float(metrics.get("productivity_ex_ga_ma", 0.0))
                violation = 1e9
                slacks = item.get("constraint_slacks")
                if isinstance(slacks, dict) and "normalized_total_violation" in slacks:
                    violation = float(slacks["normalized_total_violation"])
                score = (feasible, productivity, -violation)
                if best_score is None or score > best_score:
                    best_score = score
                    best_item = item
            if best_item is not None:
                return best_item
    return None


def total_timing_hours(artifact: Dict[str, object]) -> Tuple[float, float]:
    wall_seconds = 0.0
    cpu_hours = 0.0

    def add_timing(node: Dict[str, object]) -> None:
        nonlocal wall_seconds, cpu_hours
        timing = node.get("timing")
        if isinstance(timing, dict):
            wall_seconds += float(timing.get("wall_seconds", 0.0))
            cpu_hours += float(timing.get("cpu_hours_accounted", 0.0))

    ledger = artifact.get("ledger")
    if isinstance(ledger, list):
        for item in ledger:
            if isinstance(item, dict):
                add_timing(item)
        return wall_seconds / 3600.0, cpu_hours

    for key in ("results", "search_results", "validation_results"):
        items = artifact.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    add_timing(item)

    if wall_seconds == 0.0 and cpu_hours == 0.0:
        add_timing(artifact)
    return wall_seconds / 3600.0, cpu_hours


def classify_method(artifact: Dict[str, object], path: Path) -> str:
    stage = str(artifact.get("stage", ""))
    if path.name.startswith("agent-runner") or artifact.get("search_results") is not None:
        return "agent"
    if stage == "optimize-layouts":
        return "baseline"
    return stage or "unknown"


def build_record(path: Path, artifact: Dict[str, object]) -> Optional[Dict[str, object]]:
    best = get_best_payload(artifact)
    if best is None:
        return None
    metrics, validated = get_metrics(best)
    if metrics is None:
        return None

    wall_hours, cpu_hours = total_timing_hours(artifact)
    flow = None
    for key in ("optimized_flow", "provisional_optimized_flow", "initial_flow", "flow"):
        candidate = best.get(key)
        if isinstance(candidate, dict):
            flow = candidate
            break

    return {
        "artifact_path": str(path),
        "method": classify_method(artifact, path),
        "run_name": best.get("run_name", artifact.get("run_name", path.stem)),
        "validated": validated,
        "feasible": bool(best.get("feasible", False)),
        "nc": str(best.get("nc")),
        "productivity": metrics.get("productivity_ex_ga_ma"),
        "purity": metrics.get("purity_ex_meoh_free"),
        "recovery_ga": metrics.get("recovery_ex_GA"),
        "recovery_ma": metrics.get("recovery_ex_MA"),
        "wall_hours": wall_hours,
        "cpu_hours": cpu_hours,
        "f1": flow.get("F1") if isinstance(flow, dict) else None,
        "ffeed": flow.get("Ffeed") if isinstance(flow, dict) else None,
        "fdes": flow.get("Fdes") if isinstance(flow, dict) else None,
        "fex": flow.get("Fex") if isinstance(flow, dict) else None,
        "tstep": flow.get("tstep") if isinstance(flow, dict) else None,
    }


def write_csv(records: List[Dict[str, object]], path: Path) -> None:
    if not records:
        return
    fieldnames = list(records[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def plot_best_productivity(records: List[Dict[str, object]], output: Path) -> None:
    if not records:
        return
    labels = [f"{r['method']}:{r['run_name']}" for r in records]
    values = [float(r["productivity"]) if r["productivity"] is not None else 0.0 for r in records]
    colors = ["tab:blue" if r["method"] == "baseline" else "tab:orange" for r in records]

    fig, ax = plt.subplots(figsize=(max(8, len(records) * 1.1), 5))
    bars = ax.bar(range(len(records)), values, color=colors)
    for idx, record in enumerate(records):
        if not record["validated"]:
            bars[idx].set_hatch("//")
    ax.set_xticks(range(len(records)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Productivity")
    ax.set_title("Best SMB Productivity by Run")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output, dpi=300)
    plt.close(fig)


def plot_constraint_metrics(records: List[Dict[str, object]], output: Path) -> None:
    if not records:
        return
    labels = [f"{r['method']}:{r['run_name']}" for r in records]
    purity = [float(r["purity"]) if r["purity"] is not None else 0.0 for r in records]
    rga = [float(r["recovery_ga"]) if r["recovery_ga"] is not None else 0.0 for r in records]
    rma = [float(r["recovery_ma"]) if r["recovery_ma"] is not None else 0.0 for r in records]
    x = range(len(records))

    fig, ax = plt.subplots(figsize=(max(8, len(records) * 1.2), 5))
    width = 0.25
    ax.bar([i - width for i in x], purity, width=width, label="purity_ex_meoh_free")
    ax.bar(list(x), rga, width=width, label="recovery_ex_GA")
    ax.bar([i + width for i in x], rma, width=width, label="recovery_ex_MA")
    ax.axhline(0.90, color="red", linestyle="--", linewidth=1, label="target=0.90")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylim(0.0, max(1.05, max(purity + rga + rma) + 0.05))
    ax.set_ylabel("Metric value")
    ax.set_title("Purity and Recovery Metrics")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output, dpi=300)
    plt.close(fig)


def plot_compute_vs_productivity(records: List[Dict[str, object]], output: Path) -> None:
    if not records:
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    for record in records:
        x = float(record["cpu_hours"]) if record["cpu_hours"] is not None else 0.0
        y = float(record["productivity"]) if record["productivity"] is not None else 0.0
        color = "tab:blue" if record["method"] == "baseline" else "tab:orange"
        marker = "o" if record["validated"] else "x"
        ax.scatter(x, y, color=color, marker=marker, s=80)
        ax.annotate(str(record["run_name"]), (x, y), textcoords="offset points", xytext=(4, 4), fontsize=8)
    ax.set_xlabel("SMB-only CPU-hours")
    ax.set_ylabel("Productivity")
    ax.set_title("Compute vs Productivity")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output, dpi=300)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, object]] = []
    for path in iter_json_files(args.input_dirs):
        artifact = load_json(path)
        if not isinstance(artifact, dict):
            continue
        record = build_record(path, artifact)
        if record is not None:
            records.append(record)

    if not records:
        print("No plottable benchmark records found.")
        return 1

    records.sort(key=lambda item: (str(item["method"]), str(item["run_name"])))
    csv_path = output_dir / f"{args.prefix}_summary.csv"
    write_csv(records, csv_path)
    plot_best_productivity(records, output_dir / f"{args.prefix}_best_productivity.png")
    plot_constraint_metrics(records, output_dir / f"{args.prefix}_constraint_metrics.png")
    plot_compute_vs_productivity(records, output_dir / f"{args.prefix}_compute_vs_productivity.png")

    print(f"Wrote summary CSV: {csv_path}")
    print(f"Wrote plots under: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
