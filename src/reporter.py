"""
Reporter — generates evaluation reports in Markdown and terminal formats.

Produces:
  - Per-template report (reports/v1_report.md, etc.)
  - Comparison report across template versions (reports/comparison.md)
  - Rich terminal output for quick feedback
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.evaluator import EvaluationReport, PromptEvaluation, FAILURE_TYPES
from src.config import REPORTS_DIR

console = Console()


class Reporter:
    """Generates Markdown and terminal evaluation reports."""

    # ------------------------------------------------------------------
    # Terminal Output
    # ------------------------------------------------------------------

    @staticmethod
    def print_summary(report: EvaluationReport) -> None:
        """Print a rich terminal summary of the evaluation."""
        # Header
        console.print()
        console.print(
            Panel(
                f"[bold]Prompt Reliability Lab — {report.template_version.upper()} Report[/bold]\n"
                f"Model: {report.model}  |  Prompts: {len(report.evaluations)}",
                style="cyan",
            )
        )

        # Overall score
        score_color = _score_color(report.overall_score)
        console.print(
            f"\n  Overall Score: [{score_color}]{report.overall_score * 100:.1f}%[/{score_color}]\n"
        )

        # By-category table
        cat_table = Table(title="Scores by Category", show_header=True)
        cat_table.add_column("Category", style="bold")
        cat_table.add_column("Score", justify="right")
        cat_table.add_column("Bar", min_width=20)
        for cat, score in sorted(report.by_category().items()):
            color = _score_color(score)
            bar = _bar(score, 20)
            cat_table.add_row(cat, f"[{color}]{score * 100:.1f}%[/{color}]", bar)
        console.print(cat_table)
        console.print()

        # By-metric table
        met_table = Table(title="Scores by Metric", show_header=True)
        met_table.add_column("Metric", style="bold")
        met_table.add_column("Score", justify="right")
        met_table.add_column("Bar", min_width=20)
        for name, score in sorted(report.by_metric().items()):
            color = _score_color(score)
            bar = _bar(score, 20)
            met_table.add_row(name, f"[{color}]{score * 100:.1f}%[/{color}]", bar)
        console.print(met_table)
        console.print()

        # Failure taxonomy
        failures = report.failure_taxonomy()
        if failures:
            fail_table = Table(title="Failure Taxonomy", show_header=True)
            fail_table.add_column("Failure Type", style="bold")
            fail_table.add_column("Count", justify="right")
            fail_table.add_column("Description")
            for ftype, count in failures.items():
                desc = FAILURE_TYPES.get(ftype, "Unknown failure type")
                fail_table.add_row(ftype, str(count), desc)
            console.print(fail_table)
        else:
            console.print("  [green]No failures detected![/green]")
        console.print()

        # Bottom performers
        worst = sorted(report.evaluations, key=lambda e: e.overall_score)[:5]
        if any(e.overall_score < 1.0 for e in worst):
            bp_table = Table(title="Lowest-Scoring Prompts", show_header=True)
            bp_table.add_column("ID", style="bold")
            bp_table.add_column("Category")
            bp_table.add_column("Score", justify="right")
            bp_table.add_column("Prompt", max_width=50)
            bp_table.add_column("Failures")
            for e in worst:
                if e.overall_score < 1.0:
                    color = _score_color(e.overall_score)
                    bp_table.add_row(
                        e.prompt_id,
                        e.category,
                        f"[{color}]{e.overall_score * 100:.1f}%[/{color}]",
                        e.prompt_text[:50],
                        ", ".join(e.failures) or "—",
                    )
            console.print(bp_table)
            console.print()

    # ------------------------------------------------------------------
    # Markdown Reports
    # ------------------------------------------------------------------

    @staticmethod
    def save_report(report: EvaluationReport) -> Path:
        """Save a detailed markdown report for a single template version."""
        path = REPORTS_DIR / f"{report.template_version}_report.md"

        lines: list[str] = [
            f"# Prompt Reliability Report — {report.template_version.upper()}",
            "",
            f"**Model:** {report.model}",
            f"**Prompts evaluated:** {len(report.evaluations)}",
            f"**Overall score:** {report.overall_score * 100:.1f}%",
            "",
            "---",
            "",
            "## Scores by Category",
            "",
            "| Category | Score |",
            "|----------|-------|",
        ]
        for cat, score in sorted(report.by_category().items()):
            lines.append(f"| {cat} | {score * 100:.1f}% |")

        lines += [
            "",
            "## Scores by Metric",
            "",
            "| Metric | Score |",
            "|--------|-------|",
        ]
        for name, score in sorted(report.by_metric().items()):
            lines.append(f"| {name} | {score * 100:.1f}% |")

        lines += [
            "",
            "## Scores by Difficulty",
            "",
            "| Difficulty | Score |",
            "|------------|-------|",
        ]
        for diff, score in sorted(report.by_difficulty().items()):
            lines.append(f"| {diff} | {score * 100:.1f}% |")

        # Failure taxonomy
        failures = report.failure_taxonomy()
        if failures:
            lines += [
                "",
                "## Failure Taxonomy",
                "",
                "| Failure Type | Count | Description | Fix Strategy |",
                "|-------------|-------|-------------|-------------|",
            ]
            for ftype, count in failures.items():
                desc = FAILURE_TYPES.get(ftype, "—")
                fix = _fix_strategy(ftype)
                lines.append(f"| {ftype} | {count} | {desc} | {fix} |")

        # Detailed per-prompt results
        lines += ["", "## Per-Prompt Results", ""]
        for e in sorted(report.evaluations, key=lambda x: x.prompt_id):
            emoji = "✅" if e.overall_score >= 0.9 else "⚠️" if e.overall_score >= 0.5 else "❌"
            lines.append(f"### {emoji} {e.prompt_id} ({e.category}/{e.difficulty}) — {e.overall_score * 100:.1f}%")
            lines.append("")
            lines.append(f"> {e.prompt_text}")
            lines.append("")
            lines.append("| Metric | Score | Explanation |")
            lines.append("|--------|-------|-------------|")
            for mname, m in sorted(e.metrics.items()):
                lines.append(f"| {mname} | {m.score * 100:.1f}% | {m.explanation} |")
            if e.failures:
                lines.append(f"\n**Failures:** {', '.join(e.failures)}")
            lines.append("")

        # AI vs deterministic recommendation
        lines += [
            "---",
            "",
            "## Recommendation: AI vs Deterministic Rules",
            "",
            _ai_vs_deterministic_recommendation(report),
            "",
        ]

        path.write_text("\n".join(lines), encoding="utf-8")
        console.print(f"  Report saved: [cyan]{path}[/cyan]")
        return path

    @staticmethod
    def save_comparison(reports: list[EvaluationReport]) -> Path:
        """Save a comparison report across multiple template versions."""
        path = REPORTS_DIR / "comparison.md"

        lines: list[str] = [
            "# Prompt Template Comparison Report",
            "",
            f"**Versions compared:** {', '.join(r.template_version.upper() for r in reports)}",
            f"**Model:** {reports[0].model if reports else 'N/A'}",
            "",
            "---",
            "",
            "## Overall Scores",
            "",
            "| Version | Overall | Normal | Ambiguous | Adversarial |",
            "|---------|---------|--------|-----------|-------------|",
        ]
        for r in reports:
            cats = r.by_category()
            lines.append(
                f"| {r.template_version.upper()} "
                f"| {r.overall_score * 100:.1f}% "
                f"| {cats.get('normal', 0) * 100:.1f}% "
                f"| {cats.get('ambiguous', 0) * 100:.1f}% "
                f"| {cats.get('adversarial', 0) * 100:.1f}% |"
            )

        # Per-metric comparison
        lines += ["", "## Per-Metric Comparison", ""]
        all_metrics = set()
        for r in reports:
            all_metrics.update(r.by_metric().keys())

        header = "| Metric | " + " | ".join(r.template_version.upper() for r in reports) + " | Δ (first→last) |"
        sep = "|--------|" + "|".join("-------" for _ in reports) + "|---------|"
        lines.append(header)
        lines.append(sep)
        for metric in sorted(all_metrics):
            values = [r.by_metric().get(metric, 0) for r in reports]
            delta = values[-1] - values[0] if len(values) >= 2 else 0
            delta_str = f"+{delta * 100:.1f}%" if delta >= 0 else f"{delta * 100:.1f}%"
            row = f"| {metric} | " + " | ".join(f"{v * 100:.1f}%" for v in values) + f" | {delta_str} |"
            lines.append(row)

        # Improvement summary
        if len(reports) >= 2:
            first, last = reports[0], reports[-1]
            improvement = (last.overall_score - first.overall_score) * 100
            lines += [
                "",
                "## Improvement Summary",
                "",
                f"**Overall improvement ({first.template_version} → {last.template_version}):** "
                f"{'📈' if improvement > 0 else '📉'} {improvement:+.1f} percentage points",
                "",
            ]

            # What changed
            lines.append("### Key Changes Between Versions")
            lines.append("")
            lines.append("| Version | Key Additions |")
            lines.append("|---------|--------------|")
            lines.append("| V1 (Baseline) | Minimal instructions, no schema, no error handling |")
            lines.append("| V2 (Structured) | Explicit JSON schema, operation type catalog, basic rules |")
            lines.append("| V3 (Chain-of-Thought) | Reasoning steps, self-validation, exhaustive rules, worked examples, confidence scoring |")
            lines.append("")

            # Failure reduction
            first_failures = first.failure_taxonomy()
            last_failures = last.failure_taxonomy()
            all_ftypes = set(list(first_failures.keys()) + list(last_failures.keys()))
            if all_ftypes:
                lines.append("### Failure Reduction")
                lines.append("")
                lines.append("| Failure Type | " + first.template_version.upper() + " | " + last.template_version.upper() + " | Change |")
                lines.append("|-------------|---|---|--------|")
                for ft in sorted(all_ftypes):
                    f_count = first_failures.get(ft, 0)
                    l_count = last_failures.get(ft, 0)
                    change = l_count - f_count
                    emoji = "✅" if change < 0 else "⚠️" if change == 0 else "❌"
                    lines.append(f"| {ft} | {f_count} | {l_count} | {emoji} {change:+d} |")
                lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        console.print(f"  Comparison saved: [cyan]{path}[/cyan]")
        return path


# ── Helpers ───────────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    if score >= 0.9:
        return "green"
    if score >= 0.7:
        return "yellow"
    return "red"


def _bar(score: float, width: int) -> str:
    filled = int(score * width)
    return "█" * filled + "░" * (width - filled)


def _fix_strategy(failure_type: str) -> str:
    strategies = {
        "missing_params": "Add explicit 'required params' table to prompt with default values",
        "wrong_operation": "Add operation selection examples and disambiguation rules",
        "hallucinated_extra": "Add 'do not add operations not explicitly requested' instruction",
        "invalid_range": "Add param validation rules with explicit bounds checking",
        "refused_valid": "Relax error conditions and add 'when in doubt, attempt with assumptions' rule",
        "accepted_invalid": "Strengthen validation rules and add adversarial examples",
        "inconsistent_output": "Lower temperature, add deterministic formatting constraints",
        "no_explanation": "Require 'warnings' and 'assumptions' fields in all responses",
        "schema_violation": "Add explicit JSON schema with required fields in prompt",
    }
    return strategies.get(failure_type, "Review prompt template for gaps")


def _ai_vs_deterministic_recommendation(report: EvaluationReport) -> str:
    """Generate a recommendation on when to use AI vs deterministic rules."""
    cats = report.by_category()
    normal_score = cats.get("normal", 0)
    ambiguous_score = cats.get("ambiguous", 0)

    lines = [
        "Based on this evaluation, here are recommendations for when to use LLM-based "
        "interpretation vs deterministic rule-based parsing:",
        "",
        "### Use Deterministic Rules When:",
        "- The input follows a known, structured format (e.g., 'box 5x3x4')",
        "- Speed is critical (deterministic parsing is ~1000x faster)",
        "- The operation set is small and well-defined",
        f"- Normal prompt accuracy is below 90% (current: {normal_score * 100:.1f}%)",
        "",
        "### Use LLM Interpretation When:",
        "- The input is natural language with no fixed format",
        "- Context-dependent interpretation is needed (e.g., 'make it bigger')",
        "- The user expects conversational interaction with clarification",
        f"- Ambiguous prompts need intelligent defaults (current accuracy: {ambiguous_score * 100:.1f}%)",
        "",
        "### Hybrid Approach (Recommended):",
        "1. Attempt deterministic parsing first (regex/keyword match)",
        "2. If deterministic parsing fails, fall back to LLM interpretation",
        "3. For safety-critical operations, always validate LLM output against constraints",
        "4. Log all LLM interpretations for review and training data collection",
    ]
    return "\n".join(lines)
