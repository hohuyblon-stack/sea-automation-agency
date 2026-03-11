#!/usr/bin/env python3
"""
quality_loop.py — Autoresearch Agent Loop Engine

Implements Karpathy's autoresearch pattern:
    Human writes rules (program.md) → Agent loops (generate → evaluate → improve → repeat)

Each pipeline stage is wrapped in an evaluate→improve loop that scores output
against the metrics defined in program.md and retries with improvement actions
until the threshold is met or max iterations are exhausted.

Usage:
    from scripts.quality_loop import AgentLoop, StageEvaluator

    loop = AgentLoop("FIND", threshold=70, max_iterations=3)
    result = loop.run(generate_fn=my_generate, evaluate_fn=my_evaluate, improve_fn=my_improve)
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path.home() / "sea-automation-agency" / "data"
METRICS_FILE = DATA_DIR / "metrics_history.json"


@dataclass
class MetricResult:
    """A single metric evaluation."""
    name: str
    score: float  # 0-100
    target: float
    passed: bool
    detail: str = ""


@dataclass
class EvaluationResult:
    """Full evaluation of a pipeline stage output."""
    stage: str
    metrics: List[MetricResult]
    composite_score: float
    passed: bool
    iteration: int
    timestamp: str = ""
    improvement_actions: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def summary(self) -> str:
        lines = [
            f"[{self.stage}] Iteration {self.iteration} — Score: {self.composite_score:.1f} ({'PASS' if self.passed else 'FAIL'})"
        ]
        for m in self.metrics:
            status = "✓" if m.passed else "✗"
            lines.append(f"  {status} {m.name}: {m.score:.1f} (target: {m.target})")
        if self.improvement_actions:
            lines.append("  Improvements to apply:")
            for action in self.improvement_actions:
                lines.append(f"    → {action}")
        return "\n".join(lines)


@dataclass
class LoopResult:
    """Final result of an agent loop run."""
    stage: str
    passed: bool
    final_score: float
    iterations_used: int
    max_iterations: int
    output: Any = None
    evaluations: List[EvaluationResult] = field(default_factory=list)
    escalated: bool = False

    def summary(self) -> str:
        status = "PASSED" if self.passed else ("ESCALATED" if self.escalated else "FAILED")
        lines = [
            f"\n{'='*60}",
            f"Agent Loop Result: {self.stage}",
            f"{'='*60}",
            f"Status:     {status}",
            f"Score:      {self.final_score:.1f}",
            f"Iterations: {self.iterations_used}/{self.max_iterations}",
        ]
        if self.evaluations:
            lines.append("\nIteration History:")
            for ev in self.evaluations:
                lines.append(f"  [{ev.iteration}] {ev.composite_score:.1f} — {'PASS' if ev.passed else 'FAIL'}")
        lines.append(f"{'='*60}")
        return "\n".join(lines)


class AgentLoop:
    """
    The core autoresearch agent loop.

    Wraps any pipeline stage in a generate → evaluate → improve cycle.
    Keeps looping until the evaluation threshold is met or max iterations exhausted.
    """

    def __init__(self, stage: str, threshold: float = 70, max_iterations: int = 3):
        self.stage = stage
        self.threshold = threshold
        self.max_iterations = max_iterations

    def run(
        self,
        generate_fn: Callable[..., Any],
        evaluate_fn: Callable[[Any], EvaluationResult],
        improve_fn: Optional[Callable[[Any, EvaluationResult], Any]] = None,
        generate_kwargs: Optional[Dict] = None,
    ) -> LoopResult:
        """
        Run the agent loop.

        Args:
            generate_fn: Produces the stage output. Called with **generate_kwargs.
            evaluate_fn: Scores the output. Returns EvaluationResult.
            improve_fn: Optional. Takes (output, evaluation) and returns improved output.
                         If None, generate_fn is re-called on each iteration.
            generate_kwargs: Keyword args passed to generate_fn.

        Returns:
            LoopResult with final status, score, and history.
        """
        kwargs = generate_kwargs or {}
        evaluations = []
        output = None

        for iteration in range(1, self.max_iterations + 1):
            # --- GENERATE ---
            logger.info(f"[{self.stage}] Iteration {iteration}/{self.max_iterations} — generating...")
            try:
                if iteration == 1 or improve_fn is None:
                    output = generate_fn(**kwargs)
                else:
                    # Use the improve function to refine previous output
                    output = improve_fn(output, evaluations[-1])
            except Exception as e:
                logger.error(f"[{self.stage}] Generate failed: {e}")
                evaluations.append(EvaluationResult(
                    stage=self.stage,
                    metrics=[],
                    composite_score=0,
                    passed=False,
                    iteration=iteration,
                    improvement_actions=[f"Fix generation error: {e}"],
                ))
                continue

            # --- EVALUATE ---
            logger.info(f"[{self.stage}] Evaluating output...")
            evaluation = evaluate_fn(output)
            evaluation.iteration = iteration
            evaluation.stage = self.stage
            evaluation.passed = evaluation.composite_score >= self.threshold
            evaluations.append(evaluation)

            logger.info(evaluation.summary())

            # --- DECIDE ---
            if evaluation.passed:
                logger.info(f"[{self.stage}] PASSED at iteration {iteration} with score {evaluation.composite_score:.1f}")
                result = LoopResult(
                    stage=self.stage,
                    passed=True,
                    final_score=evaluation.composite_score,
                    iterations_used=iteration,
                    max_iterations=self.max_iterations,
                    output=output,
                    evaluations=evaluations,
                )
                self._record_metrics(result)
                return result

            # --- IMPROVE (or loop back to generate) ---
            if iteration < self.max_iterations:
                logger.info(f"[{self.stage}] Score {evaluation.composite_score:.1f} < {self.threshold} — improving...")

        # Max iterations exhausted — escalate
        final_eval = evaluations[-1] if evaluations else None
        result = LoopResult(
            stage=self.stage,
            passed=False,
            final_score=final_eval.composite_score if final_eval else 0,
            iterations_used=self.max_iterations,
            max_iterations=self.max_iterations,
            output=output,
            evaluations=evaluations,
            escalated=True,
        )
        self._record_metrics(result)
        logger.warning(
            f"[{self.stage}] ESCALATED — max iterations reached. "
            f"Final score: {result.final_score:.1f}"
        )
        return result

    def _record_metrics(self, result: LoopResult):
        """Persist metrics to history file for trend analysis."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        history = []
        if METRICS_FILE.exists():
            try:
                history = json.loads(METRICS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                history = []

        record = {
            "stage": result.stage,
            "timestamp": datetime.now().isoformat(),
            "passed": result.passed,
            "final_score": result.final_score,
            "iterations_used": result.iterations_used,
            "escalated": result.escalated,
            "metrics": {},
        }
        if result.evaluations:
            last_eval = result.evaluations[-1]
            for m in last_eval.metrics:
                record["metrics"][m.name] = {
                    "score": m.score,
                    "target": m.target,
                    "passed": m.passed,
                }

        history.append(record)
        METRICS_FILE.write_text(json.dumps(history, indent=2))


# ---------------------------------------------------------------------------
# Stage-specific evaluators
# ---------------------------------------------------------------------------

class FindEvaluator:
    """Evaluator for the FIND (Lead Qualification) stage."""

    def evaluate(self, leads: list) -> EvaluationResult:
        if not leads:
            return EvaluationResult(
                stage="FIND", metrics=[], composite_score=0,
                passed=False, iteration=0,
                improvement_actions=["No leads produced — check scraper input"],
            )

        total = len(leads)

        # contact_coverage: % with BOTH phone AND email
        both_contact = sum(
            1 for l in leads
            if l.get("phone", "").strip() and l.get("email", "").strip()
        )
        contact_coverage = (both_contact / total) * 100

        # platform_match: % with detected platform
        with_platform = sum(
            1 for l in leads
            if l.get("platform", "").strip()
        )
        platform_match = (with_platform / total) * 100

        # city_concentration: % in major cities
        major_cities = {
            "ho chi minh", "hcm", "tphcm", "saigon",
            "ha noi", "hanoi", "da nang", "danang",
            "can tho", "hai phong", "bien hoa",
        }
        in_major = sum(
            1 for l in leads
            if any(c in l.get("city", "").lower() for c in major_cities)
        )
        city_concentration = (in_major / total) * 100

        # avg_score
        scores = [int(l.get("score", 0) or 0) for l in leads]
        avg_score = sum(scores) / len(scores) if scores else 0

        metrics = [
            MetricResult("contact_coverage", contact_coverage, 60, contact_coverage >= 60),
            MetricResult("platform_match", platform_match, 70, platform_match >= 70),
            MetricResult("city_concentration", city_concentration, 50, city_concentration >= 50),
            MetricResult("avg_score", avg_score, 45, avg_score >= 45),
        ]

        composite = sum(m.score for m in metrics) / len(metrics)

        # Determine improvement actions for failing metrics
        actions = []
        if contact_coverage < 60:
            actions.append("broaden_scraper: add alternate contact field extraction")
        if platform_match < 70:
            actions.append("enhance_platform_detection: check website/social for Shopee/TikTok links")
        if avg_score < 45:
            actions.append("tighten_targeting: focus scraper on higher-signal sources")

        return EvaluationResult(
            stage="FIND",
            metrics=metrics,
            composite_score=composite,
            passed=composite >= 70,
            iteration=0,
            improvement_actions=actions,
        )


class OutreachEvaluator:
    """Evaluator for the OUTREACH (Email Sequence) stage."""

    def evaluate(self, send_results: list) -> EvaluationResult:
        """
        Evaluate outreach results.

        send_results: list of dicts with keys:
            - sent: bool (API call succeeded)
            - personalized: bool (all 5 vars filled)
            - timing_ok: bool (respects sequence delays)
            - clean_render: bool (no unresolved {{placeholders}})
            - crm_synced: bool (logged to CRM)
        """
        if not send_results:
            return EvaluationResult(
                stage="OUTREACH", metrics=[], composite_score=0,
                passed=False, iteration=0,
                improvement_actions=["No sends attempted — check lead input"],
            )

        total = len(send_results)

        delivery = sum(1 for r in send_results if r.get("sent")) / total * 100
        personal = sum(1 for r in send_results if r.get("personalized")) / total * 100
        timing = sum(1 for r in send_results if r.get("timing_ok")) / total * 100
        clean = sum(1 for r in send_results if r.get("clean_render")) / total * 100
        crm = sum(1 for r in send_results if r.get("crm_synced")) / total * 100

        metrics = [
            MetricResult("delivery_rate", delivery, 95, delivery >= 95),
            MetricResult("personalization_score", personal, 100, personal >= 100),
            MetricResult("sequence_compliance", timing, 100, timing >= 100),
            MetricResult("template_render_clean", clean, 100, clean >= 100),
            MetricResult("crm_sync_rate", crm, 98, crm >= 98),
        ]

        composite = sum(m.score for m in metrics) / len(metrics)

        actions = []
        if delivery < 95:
            actions.append("retry_failed_sends: backoff and retry Gmail API errors")
        if personal < 100:
            actions.append("fill_missing_fields: flag leads with missing vars, use defaults")
        if clean < 100:
            actions.append("audit_templates: check template vars vs CSV columns")
        if crm < 98:
            actions.append("retry_crm_sync: add retry logic to Sheets API calls")

        return EvaluationResult(
            stage="OUTREACH",
            metrics=metrics,
            composite_score=composite,
            passed=composite >= 90,
            iteration=0,
            improvement_actions=actions,
        )


class ProposeEvaluator:
    """Evaluator for the PROPOSE (Proposal Generation) stage."""

    REQUIRED_FIELDS = ["client_name", "business_name", "platform", "price_vnd", "hours_saved"]

    def evaluate(self, proposal_data: dict) -> EvaluationResult:
        """
        Evaluate a generated proposal.

        proposal_data: dict with keys:
            - fields: dict of field_name → value
            - md_path: str (path to generated .md file)
            - html_path: str (path to generated .html file)
            - hours_saved: float
            - monthly_orders: int
        """
        metrics = []

        # field_completeness
        fields = proposal_data.get("fields", {})
        filled = sum(1 for f in self.REQUIRED_FIELDS if fields.get(f))
        completeness = (filled / len(self.REQUIRED_FIELDS)) * 100
        metrics.append(MetricResult("field_completeness", completeness, 100, completeness >= 100))

        # format_validity
        md_exists = Path(proposal_data.get("md_path", "")).exists() if proposal_data.get("md_path") else False
        html_exists = Path(proposal_data.get("html_path", "")).exists() if proposal_data.get("html_path") else False
        format_score = 100 if (md_exists and html_exists) else (50 if (md_exists or html_exists) else 0)
        metrics.append(MetricResult("format_validity", format_score, 100, format_score >= 100))

        # roi_accuracy
        orders = proposal_data.get("monthly_orders", 0)
        expected_hours = (orders * 5) / 60
        actual_hours = proposal_data.get("hours_saved", 0)
        roi_ok = abs(expected_hours - actual_hours) < 0.1 if orders else True
        roi_score = 100 if roi_ok else 0
        metrics.append(MetricResult("roi_accuracy", roi_score, 100, roi_ok))

        # file_output
        file_score = 100 if (md_exists and html_exists) else 0
        metrics.append(MetricResult("file_output", file_score, 100, file_score >= 100))

        composite = sum(m.score for m in metrics) / len(metrics)

        actions = []
        if completeness < 100:
            actions.append("fill_missing: prompt for missing proposal fields or use defaults")
        if format_score < 100:
            actions.append("fix_render: re-generate missing output format")
        if not roi_ok:
            actions.append("fix_roi: recompute hours_saved from monthly_orders")

        return EvaluationResult(
            stage="PROPOSE",
            metrics=metrics,
            composite_score=composite,
            passed=composite >= 95,
            iteration=0,
            improvement_actions=actions,
        )


class DeliverEvaluator:
    """Evaluator for the DELIVER (Service Deployment) stage."""

    REQUIRED_CONFIG_KEYS = ["business_name", "email", "zalo_webhook"]

    def evaluate(self, deploy_data: dict) -> EvaluationResult:
        """
        Evaluate a service deployment.

        deploy_data: dict with keys:
            - config: dict (client config.json contents)
            - first_sync_ok: bool
            - webhook_ok: bool
            - tables_created: list of table names
            - errors_24h: int
            - total_ops_24h: int
        """
        metrics = []

        # config_validity
        config = deploy_data.get("config", {})
        client = config.get("client", {})
        filled = sum(1 for k in self.REQUIRED_CONFIG_KEYS if client.get(k))
        config_score = (filled / len(self.REQUIRED_CONFIG_KEYS)) * 100
        metrics.append(MetricResult("config_validity", config_score, 100, config_score >= 100))

        # first_sync_success
        sync_ok = deploy_data.get("first_sync_ok", False)
        metrics.append(MetricResult("first_sync_success", 100 if sync_ok else 0, 100, sync_ok))

        # webhook_reachable
        webhook_ok = deploy_data.get("webhook_ok", False)
        metrics.append(MetricResult("webhook_reachable", 100 if webhook_ok else 0, 100, webhook_ok))

        # schema_integrity
        expected = {"orders", "sync_log"}
        actual = set(deploy_data.get("tables_created", []))
        schema_ok = expected.issubset(actual)
        metrics.append(MetricResult("schema_integrity", 100 if schema_ok else 0, 100, schema_ok))

        # error_rate_24h
        errors = deploy_data.get("errors_24h", 0)
        total_ops = deploy_data.get("total_ops_24h", 1)
        error_rate = (errors / total_ops) * 100 if total_ops else 0
        error_score = max(0, 100 - (error_rate * 50))  # 2% error → score 0
        metrics.append(MetricResult("error_rate_24h", error_score, 98, error_rate <= 2))

        composite = sum(m.score for m in metrics) / len(metrics)

        actions = []
        if config_score < 100:
            actions.append("fix_config: prompt operator for missing credentials")
        if not sync_ok:
            actions.append("debug_sync: check API credentials, retry with verbose logging")
        if not webhook_ok:
            actions.append("fix_webhook: verify Zalo webhook URL and connectivity")

        return EvaluationResult(
            stage="DELIVER",
            metrics=metrics,
            composite_score=composite,
            passed=composite >= 95,
            iteration=0,
            improvement_actions=actions,
        )


class ReportEvaluator:
    """Evaluator for the REPORT (Monthly Reporting) stage."""

    def evaluate(self, report_data: dict) -> EvaluationResult:
        """
        Evaluate a generated report.

        report_data: dict with keys:
            - days_with_data: int
            - days_in_month: int
            - totals_correct: bool
            - mom_correct: bool
            - html_valid: bool
            - email_sent: bool
            - crm_updated: bool
        """
        metrics = []

        days_data = report_data.get("days_with_data", 0)
        days_month = report_data.get("days_in_month", 30)
        completeness = (days_data / days_month) * 100 if days_month else 0
        metrics.append(MetricResult("data_completeness", completeness, 90, completeness >= 90))

        totals_ok = report_data.get("totals_correct", False)
        mom_ok = report_data.get("mom_correct", False)
        calc_score = 100 if (totals_ok and mom_ok) else (50 if totals_ok else 0)
        metrics.append(MetricResult("calculation_accuracy", calc_score, 100, calc_score >= 100))

        html_ok = report_data.get("html_valid", False)
        metrics.append(MetricResult("render_quality", 100 if html_ok else 0, 100, html_ok))

        email_ok = report_data.get("email_sent", False)
        metrics.append(MetricResult("delivery_success", 100 if email_ok else 0, 100, email_ok))

        crm_ok = report_data.get("crm_updated", False)
        metrics.append(MetricResult("crm_updated", 100 if crm_ok else 0, 100, crm_ok))

        composite = sum(m.score for m in metrics) / len(metrics)

        actions = []
        if completeness < 90:
            actions.append("backfill_data: check sync logs for gaps, re-sync missing days")
        if calc_score < 100:
            actions.append("recompute: recalculate from raw SQL queries")
        if not email_ok:
            actions.append("retry_email: retry Gmail API send")
        if not crm_ok:
            actions.append("retry_crm: update Sheets API")

        return EvaluationResult(
            stage="REPORT",
            metrics=metrics,
            composite_score=composite,
            passed=composite >= 90,
            iteration=0,
            improvement_actions=actions,
        )


# ---------------------------------------------------------------------------
# Convenience: get evaluator by stage name
# ---------------------------------------------------------------------------

EVALUATORS = {
    "FIND": FindEvaluator,
    "OUTREACH": OutreachEvaluator,
    "PROPOSE": ProposeEvaluator,
    "DELIVER": DeliverEvaluator,
    "REPORT": ReportEvaluator,
}


def get_evaluator(stage: str):
    """Get the evaluator class for a pipeline stage."""
    cls = EVALUATORS.get(stage.upper())
    if not cls:
        raise ValueError(f"Unknown stage: {stage}. Valid: {list(EVALUATORS.keys())}")
    return cls()
