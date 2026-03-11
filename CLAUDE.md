# CLAUDE.md — Global Rules for SEA Automation Agency

## Autoresearch Agent Loop (Karpathy Pattern)

Every pipeline stage MUST run inside an agent loop. The loop protocol is:

1. **Generate** — Run the stage normally (qualify leads, send emails, generate proposal, deploy service, create report)
2. **Evaluate** — Score the output against the metrics defined in `program.md` (composite score 0-100)
3. **Decide** — If composite score ≥ stage threshold → PASS, proceed to next stage
4. **Improve** — If score < threshold AND iterations < max → apply the improvement actions from `program.md`, then re-run
5. **Escalate** — If max iterations exhausted and still failing → log failure, alert operator, HALT pipeline

### Stage Thresholds (from program.md)

| Stage    | Threshold | Max Iterations |
|----------|-----------|----------------|
| FIND     | 70        | 3              |
| OUTREACH | 90        | 2              |
| PROPOSE  | 95        | 2              |
| DELIVER  | 95        | 3              |
| REPORT   | 90        | 2              |

### Rules for Using the Loop

- **Always use the loop by default.** The `--no-loop` flag exists only for debugging or quick manual runs.
- **Never skip evaluation.** Even if the output "looks good", the metrics must be computed and logged.
- **Metrics are always recorded** to `data/metrics_history.json` — even for passing runs. This powers the trend dashboard.
- **Improvement actions are automated** — each evaluator knows what to try when a metric fails (e.g., relax thresholds, fill defaults, retry API calls).
- **Escalation is a hard stop.** If a stage escalates, do NOT proceed to the next stage. Fix the root cause first.

### Key Files

| File | Purpose |
|------|---------|
| `program.md` | Human-defined quality rules, metrics, thresholds per stage |
| `scripts/quality_loop.py` | Agent loop engine + all 5 stage evaluators |
| `scripts/metrics_tracker.py` | Dashboard: `python scripts/metrics_tracker.py --trend` |
| `data/metrics_history.json` | Auto-generated metrics log (do not edit manually) |

### How to Wire a New Stage

```python
from scripts.quality_loop import AgentLoop, get_evaluator

evaluator = get_evaluator("STAGE_NAME")
loop = AgentLoop(stage="STAGE_NAME", threshold=70, max_iterations=3)
result = loop.run(
    generate_fn=my_generate_function,
    evaluate_fn=evaluator.evaluate,
    improve_fn=my_improve_function,  # optional
)
print(result.summary())
```

## General Pipeline Rules

- The pipeline runs in order: FIND → OUTREACH → PROPOSE → DELIVER → REPORT
- Each stage's output feeds the next stage's input
- All operations are logged and tracked in the Google Sheets CRM
- Vietnamese is the default language for all client-facing content
- Use `--dry-run` flags to preview before live execution
- Secrets go in `.env`, never in code or config.yaml
