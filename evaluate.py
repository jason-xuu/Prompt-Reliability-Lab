#!/usr/bin/env python3
"""
Prompt Reliability Lab — CLI Entry Point.

Usage:
    python evaluate.py --template v1                # Run one template
    python evaluate.py --template v1 v2 v3          # Run all and compare
    python evaluate.py --template v3 --runs 1       # Quick single-run check
    python evaluate.py --compare reports/            # Compare existing reports

Examples:
    # Full evaluation with comparison
    python evaluate.py --template v1 v2 v3

    # Quick smoke test
    python evaluate.py --template v3 --runs 1
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import get_llm_config, get_eval_config, REPORTS_DIR
from src.runner import Runner
from src.reporter import Reporter
from src.evaluator import EvaluationReport

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_time=False)],
    )


def run_evaluation(templates: list[str], consistency_runs: int | None = None) -> list[EvaluationReport]:
    """Run evaluations for the specified templates."""
    llm_config = get_llm_config()
    eval_config = get_eval_config()

    # Override consistency runs if specified
    if consistency_runs is not None:
        eval_config = type(eval_config)(
            consistency_runs=consistency_runs,
            max_concurrent=eval_config.max_concurrent,
            corpus_path=eval_config.corpus_path,
            gold_path=eval_config.gold_path,
        )

    runner = Runner(llm_config, eval_config)
    reports: list[EvaluationReport] = []

    for template in templates:
        console.print(f"\n{'='*60}")
        console.print(f"  Running evaluation: [bold cyan]{template.upper()}[/bold cyan]")
        console.print(f"{'='*60}\n")

        report = runner.run(template)
        reports.append(report)

        # Print summary to terminal
        Reporter.print_summary(report)

        # Save individual report
        Reporter.save_report(report)

        # Also save raw results as JSON for later analysis
        raw_path = REPORTS_DIR / f"{template}_raw.json"
        _save_raw_results(report, raw_path)

    # Generate comparison if multiple templates
    if len(reports) > 1:
        console.print(f"\n{'='*60}")
        console.print("  [bold cyan]COMPARISON REPORT[/bold cyan]")
        console.print(f"{'='*60}\n")
        Reporter.save_comparison(reports)

        # Print comparison summary
        first, last = reports[0], reports[-1]
        improvement = (last.overall_score - first.overall_score) * 100
        emoji = "📈" if improvement > 0 else "📉"
        console.print(
            f"  {emoji} Overall improvement "
            f"({first.template_version} → {last.template_version}): "
            f"[bold]{improvement:+.1f}[/bold] percentage points\n"
        )

    return reports


def _save_raw_results(report: EvaluationReport, path: Path) -> None:
    """Save raw evaluation data as JSON for debugging/analysis."""
    data = {
        "template_version": report.template_version,
        "model": report.model,
        "overall_score": report.overall_score,
        "by_category": report.by_category(),
        "by_metric": report.by_metric(),
        "failure_taxonomy": report.failure_taxonomy(),
        "evaluations": [
            {
                "prompt_id": e.prompt_id,
                "category": e.category,
                "difficulty": e.difficulty,
                "prompt_text": e.prompt_text,
                "overall_score": e.overall_score,
                "metrics": {
                    name: {"score": m.score, "explanation": m.explanation}
                    for name, m in e.metrics.items()
                },
                "failures": e.failures,
            }
            for e in report.evaluations
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    console.print(f"  Raw results saved: [dim]{path}[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prompt Reliability Lab — Evaluate prompt templates for geometry LLM commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--template", "-t",
        nargs="+",
        choices=["v1", "v2", "v3"],
        required=True,
        help="Template version(s) to evaluate (v1, v2, v3). Specify multiple for comparison.",
    )
    parser.add_argument(
        "--runs", "-r",
        type=int,
        default=None,
        help="Override number of consistency runs per prompt (default: from .env)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        reports = run_evaluation(args.template, args.runs)
        console.print("\n[green bold]✓ Evaluation complete![/green bold]")
        console.print(f"  Reports saved to: [cyan]{REPORTS_DIR}[/cyan]\n")
    except ValueError as exc:
        console.print(f"\n[red bold]✗ Configuration error:[/red bold] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"\n[red bold]✗ Error:[/red bold] {exc}")
        logging.getLogger().exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
