#!/usr/bin/env python3
"""
metrics_tracker.py — Pipeline Performance Tracker

Reads the metrics history logged by the agent loop and provides:
  - Trend analysis per stage
  - Pass/fail rates over time
  - Metric degradation alerts
  - Terminal dashboard view

Usage:
    python scripts/metrics_tracker.py                    # Show dashboard
    python scripts/metrics_tracker.py --stage FIND       # Show one stage
    python scripts/metrics_tracker.py --trend            # Show score trends
    python scripts/metrics_tracker.py --export report.json  # Export full history
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path.home() / "sea-automation-agency" / "data"
METRICS_FILE = DATA_DIR / "metrics_history.json"

STAGES = ["FIND", "OUTREACH", "PROPOSE", "DELIVER", "REPORT"]


def load_history() -> List[dict]:
    """Load the metrics history file."""
    if not METRICS_FILE.exists():
        return []
    try:
        return json.loads(METRICS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def filter_by_stage(history: list, stage: str) -> list:
    return [r for r in history if r.get("stage", "").upper() == stage.upper()]


def filter_by_days(history: list, days: int) -> list:
    cutoff = datetime.now() - timedelta(days=days)
    filtered = []
    for r in history:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
            if ts >= cutoff:
                filtered.append(r)
        except (KeyError, ValueError):
            filtered.append(r)
    return filtered


def stage_summary(history: list, stage: str) -> dict:
    """Compute summary stats for a single stage."""
    records = filter_by_stage(history, stage)
    if not records:
        return {"stage": stage, "runs": 0}

    scores = [r["final_score"] for r in records]
    passes = sum(1 for r in records if r["passed"])
    escalations = sum(1 for r in records if r.get("escalated"))
    iterations = [r.get("iterations_used", 1) for r in records]

    # Metric averages
    metric_totals = defaultdict(list)
    for r in records:
        for name, data in r.get("metrics", {}).items():
            metric_totals[name].append(data["score"])

    metric_avgs = {
        name: sum(vals) / len(vals)
        for name, vals in metric_totals.items()
    }

    return {
        "stage": stage,
        "runs": len(records),
        "pass_rate": (passes / len(records)) * 100,
        "escalation_rate": (escalations / len(records)) * 100,
        "avg_score": sum(scores) / len(scores),
        "min_score": min(scores),
        "max_score": max(scores),
        "avg_iterations": sum(iterations) / len(iterations),
        "metric_averages": metric_avgs,
        "last_run": records[-1]["timestamp"],
    }


def score_trend(history: list, stage: str, window: int = 10) -> List[dict]:
    """Get the last N scores for a stage to show trend."""
    records = filter_by_stage(history, stage)[-window:]
    return [
        {
            "timestamp": r["timestamp"],
            "score": r["final_score"],
            "passed": r["passed"],
            "iterations": r.get("iterations_used", 1),
        }
        for r in records
    ]


def detect_degradation(history: list, stage: str, window: int = 5) -> Optional[str]:
    """Check if a stage's scores are trending downward."""
    records = filter_by_stage(history, stage)
    if len(records) < window:
        return None

    recent = records[-window:]
    scores = [r["final_score"] for r in recent]

    # Simple linear trend: compare first half avg to second half avg
    mid = len(scores) // 2
    first_half = sum(scores[:mid]) / mid
    second_half = sum(scores[mid:]) / (len(scores) - mid)

    if second_half < first_half - 10:
        return (
            f"DEGRADATION ALERT: {stage} scores dropping. "
            f"First half avg: {first_half:.1f}, Second half avg: {second_half:.1f}"
        )
    return None


def print_dashboard(history: list, stage_filter: Optional[str] = None):
    """Print a terminal dashboard of pipeline health."""
    stages = [stage_filter.upper()] if stage_filter else STAGES

    print(f"\n{'='*70}")
    print(f"  SEA Automation Agency — Pipeline Health Dashboard")
    print(f"  (Autoresearch Agent Loop Metrics)")
    print(f"{'='*70}")

    if not history:
        print("\n  No metrics recorded yet. Run the pipeline to generate data.")
        print(f"{'='*70}\n")
        return

    for stage in stages:
        summary = stage_summary(history, stage)
        if summary["runs"] == 0:
            print(f"\n  [{stage}] No runs recorded")
            continue

        print(f"\n  [{stage}]")
        print(f"  {'─'*40}")
        print(f"  Runs:          {summary['runs']}")
        print(f"  Pass Rate:     {summary['pass_rate']:.0f}%")
        print(f"  Avg Score:     {summary['avg_score']:.1f}")
        print(f"  Score Range:   {summary['min_score']:.1f} – {summary['max_score']:.1f}")
        print(f"  Avg Iterations:{summary['avg_iterations']:.1f}")
        print(f"  Escalations:   {summary['escalation_rate']:.0f}%")
        print(f"  Last Run:      {summary['last_run']}")

        if summary.get("metric_averages"):
            print(f"\n  Metric Averages:")
            for name, avg in sorted(summary["metric_averages"].items()):
                bar_len = int(avg / 5)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                print(f"    {name:30s} {bar} {avg:.1f}")

        # Check for degradation
        alert = detect_degradation(history, stage)
        if alert:
            print(f"\n  ⚠ {alert}")

    print(f"\n{'='*70}\n")


def print_trend(history: list, stage_filter: Optional[str] = None):
    """Print score trend for stages."""
    stages = [stage_filter.upper()] if stage_filter else STAGES

    for stage in stages:
        trend = score_trend(history, stage)
        if not trend:
            continue

        print(f"\n[{stage}] Score Trend (last {len(trend)} runs):")
        for t in trend:
            ts = t["timestamp"][:16]
            score = t["score"]
            status = "PASS" if t["passed"] else "FAIL"
            iters = t["iterations"]
            bar_len = int(score / 5)
            bar = "█" * bar_len
            print(f"  {ts}  {bar:20s} {score:5.1f} [{status}] ({iters} iter)")


def main():
    parser = argparse.ArgumentParser(description="Pipeline metrics dashboard")
    parser.add_argument("--stage", default="", help="Filter by stage (FIND, OUTREACH, PROPOSE, DELIVER, REPORT)")
    parser.add_argument("--trend", action="store_true", help="Show score trends")
    parser.add_argument("--days", type=int, default=0, help="Filter to last N days")
    parser.add_argument("--export", default="", help="Export history to JSON file")
    args = parser.parse_args()

    history = load_history()

    if args.days:
        history = filter_by_days(history, args.days)

    if args.export:
        Path(args.export).write_text(json.dumps(history, indent=2))
        print(f"Exported {len(history)} records to {args.export}")
        return

    if args.trend:
        print_trend(history, args.stage or None)
    else:
        print_dashboard(history, args.stage or None)


if __name__ == "__main__":
    main()
