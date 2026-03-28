"""CLI entry point for the Conversation Analysis System."""

from __future__ import annotations

import sys
from datetime import datetime

import click

from cas.ingestion import load_data
from cas.analyzers import analyze
from cas.aggregator import aggregate
from cas.reporter import generate_report
from cas.storage import save_run


@click.group()
def cli() -> None:
    """Conversation Analysis System."""


@cli.command()
@click.option("--mongo-uri", default="mongodb://localhost:27017", show_default=True,
              help="MongoDB connection URI.")
@click.option("--widget-id", default=None,
              help="Optional brand filter (widget ID).")
@click.option("--date-from", default=None,
              help="Optional start date filter as YYYY-MM-DD.")
@click.option("--date-to", default=None,
              help="Optional end date filter as YYYY-MM-DD.")
@click.option("--output", default="./output", show_default=True,
              help="Output directory for reports.")
@click.option("--storage", default="runs.json", show_default=True,
              help="Path to trend storage JSON file.")
def analyze_cmd(
    mongo_uri: str,
    widget_id: str | None,
    date_from: str | None,
    date_to: str | None,
    output: str,
    storage: str,
) -> None:
    """Run the full conversation analysis pipeline."""
    try:
        # Parse optional date strings
        parsed_date_from: datetime | None = None
        parsed_date_to: datetime | None = None
        if date_from:
            parsed_date_from = datetime.strptime(date_from, "%Y-%m-%d")
        if date_to:
            parsed_date_to = datetime.strptime(date_to, "%Y-%m-%d")

        # 1. Load data
        conversations = load_data(mongo_uri, widget_id, parsed_date_from, parsed_date_to)

        # 1b. Learn frustration keywords and product suggestion phrases from the dataset
        from cas.analyzers.dropoff import learn_keywords
        from cas.analyzers.products import learn_suggestion_phrases
        learn_keywords(conversations)
        learn_suggestion_phrases(conversations)

        # 2. Analyze each conversation
        results = [analyze(conv) for conv in conversations]

        # 3. Aggregate results
        filters_applied: dict = {}
        if widget_id is not None:
            filters_applied["widget_id"] = widget_id
        if date_from is not None:
            filters_applied["date_from"] = date_from
        if date_to is not None:
            filters_applied["date_to"] = date_to

        report = aggregate(results, filters_applied)

        # 4. Generate report
        generate_report(report, output)

        # 5. Save run
        save_run(report.brand_metrics, report.run_date, storage)

        # 6. Print summary
        click.echo(f"Conversations analyzed: {report.summary.total_conversations}")
        click.echo(f"Brands analyzed: {report.summary.total_brands}")
        click.echo(f"Output directory: {output}")

    except (ConnectionError, IOError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(1)


# Register the command under the name "analyze"
cli.add_command(analyze_cmd, name="analyze")
