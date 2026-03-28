# Implementation Plan: Conversation Analysis System

## Overview

Implement a Python CLI pipeline that ingests MongoDB conversation data, runs a suite of analyzers, aggregates per-brand metrics, and produces JSON + Markdown reports. The implementation follows the five-stage linear pipeline: ingestion → analysis → aggregation → reporting → trend storage.

## Tasks

- [x] 1. Set up project structure, data models, and dependencies
  - Create package layout: `cas/`, `cas/analyzers/`, `tests/`, `templates/`, `data/`
  - Create `pyproject.toml` (or `requirements.txt`) with dependencies: `pymongo`, `click`, `jinja2`, `hypothesis`, `pytest`, `textblob`, `sentence-transformers`
  - Define all dataclasses in `cas/models.py`: `Conversation`, `Message`, `EnrichedConversation`, `AnalysisResult`, `FlaggedResponse`, `BrandMetrics`, `AggregatedReport`, `ReportSummary`, `FlaggedConversation`, `RunRecord`
  - _Requirements: 1.1, 1.2, 2.1_

- [x] 2. Implement data ingestion (`cas/ingestion.py`)
  - [x] 2.1 Implement `load_data()` with MongoDB connection, join, and filtering
    - Connect to `helio_intern` database via `pymongo`
    - Query `conversations` with optional `widgetId` and `createdAt` filters
    - Fetch and group messages by `conversationId`
    - Exclude zero-message conversations with `WARNING` log
    - Return `list[EnrichedConversation]` with messages sorted by `created_at`
    - Raise `ConnectionError` on connection failure
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.2 Write property test: message-to-conversation join correctness
    - **Property 1: Message-to-conversation join correctness**
    - **Validates: Requirements 1.2**

  - [ ]* 2.3 Write property test: widgetId filter correctness
    - **Property 2: widgetId filter correctness**
    - **Validates: Requirements 1.3, 2.1**

  - [ ]* 2.4 Write property test: date range filter correctness
    - **Property 3: Date range filter correctness**
    - **Validates: Requirements 1.4**

  - [ ]* 2.5 Write property test: zero-message conversation exclusion
    - **Property 4: Zero-message conversation exclusion**
    - **Validates: Requirements 1.6**

  - [ ]* 2.6 Write unit tests for ingestion
    - Test connection failure raises `ConnectionError`
    - Test empty result set returns empty list
    - Test messages are sorted by `created_at`
    - _Requirements: 1.5, 1.6_

- [x] 3. Checkpoint — Ensure all ingestion tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement conversation segmentation analyzer (`cas/analyzers/segmentation.py`)
  - [x] 4.1 Implement `analyze(conv: EnrichedConversation) -> AnalysisResult` (partial)
    - Separate text messages from event messages
    - Classify conversation into topic categories using user text messages
    - Flag conversation as unanswered if no agent messages exist
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [ ]* 4.2 Write property test: message type partition invariant
    - **Property 5: Message type partition invariant**
    - **Validates: Requirements 2.2**

  - [ ]* 4.3 Write property test: topic classification completeness
    - **Property 6: Topic classification completeness**
    - **Validates: Requirements 2.3**

  - [ ]* 4.4 Write property test: unanswered conversation flag correctness
    - **Property 7: Unanswered conversation flag correctness**
    - **Validates: Requirements 2.4, 2.5**

  - [ ]* 4.5 Write unit tests for segmentation
    - Test known topic phrases map to expected categories
    - Test single-message (user-only) conversation is flagged unanswered
    - Test event-only conversation produces empty text message list
    - _Requirements: 2.2, 2.3, 2.5_

- [x] 5. Implement drop-off and frustration analyzer (`cas/analyzers/dropoff.py`)
  - [x] 5.1 Implement drop-off detection and frustration scoring
    - Detect drop-off: last message sender = "user" with no subsequent agent message
    - Score frustration using sentiment analysis and repeated-question detection
    - Return `is_drop_off`, `is_unanswered`, and `frustration_score` fields
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 5.2 Write property test: drop-off detection correctness
    - **Property 8: Drop-off detection correctness**
    - **Validates: Requirements 3.1**

  - [ ]* 5.3 Write property test: frustration score bounds invariant
    - **Property 9: Frustration score bounds invariant**
    - **Validates: Requirements 3.3**

  - [ ]* 5.4 Write unit tests for drop-off and frustration
    - Test conversation ending with user message is drop-off
    - Test conversation ending with agent message is not drop-off
    - Test known frustration phrases produce score > 0
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 6. Implement response quality analyzer (`cas/analyzers/quality.py`)
  - [x] 6.1 Implement relevance scoring, hallucination detection, and verbosity flagging
    - Score each agent response for relevance to preceding user message
    - Flag irrelevant responses; detect potential hallucinations with confidence score
    - Flag agent messages exceeding 500 words as verbose
    - Populate `flagged_responses` list with `FlaggedResponse` objects
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [ ]* 6.2 Write property test: verbose response flagging
    - **Property 12: Verbose response flagging**
    - **Validates: Requirements 4.6**

  - [ ]* 6.3 Write property test: hallucination record completeness
    - **Property 13: Hallucination record completeness**
    - **Validates: Requirements 4.4**

  - [ ]* 6.4 Write unit tests for quality analyzer
    - Test agent message > 500 words produces "verbose" flag
    - Test known irrelevant response pair produces "irrelevant" flag
    - Test hallucination record contains non-empty message_id, confidence in [0,1], non-empty reason
    - _Requirements: 4.2, 4.4, 4.6_

- [x] 7. Implement product suggestion analyzer (`cas/analyzers/products.py`)
  - [x] 7.1 Implement product engagement detection and low-engagement flagging
    - Detect `product_engagement` from event messages with `metadata.eventType = "product_view"`
    - Flag `low_engagement_product_rec` when product suggestions exist but zero engagement events
    - _Requirements: 5.1, 5.3_

  - [ ]* 7.2 Write property test: product engagement detection
    - **Property 15: Product engagement detection**
    - **Validates: Requirements 5.1**

  - [ ]* 7.3 Write unit tests for product analyzer
    - Test conversation with product_view event sets `product_engagement = True`
    - Test conversation without any events sets `product_engagement = False`
    - _Requirements: 5.1, 5.3_

- [x] 8. Wire analyzers into a single `analyze` pipeline (`cas/analyzers/__init__.py`)
  - Compose segmentation, dropoff, quality, and products analyzers into one `analyze(conv) -> AnalysisResult`
  - Merge partial results from each analyzer into a single `AnalysisResult`
  - _Requirements: 2.2, 2.3, 3.1, 4.1, 5.1_

- [x] 9. Checkpoint — Ensure all analyzer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement metric aggregation (`cas/aggregator.py`)
  - [x] 10.1 Implement `aggregate(results: list[AnalysisResult]) -> AggregatedReport`
    - Group results by `widget_id`
    - Compute per-brand: `drop_off_rate`, `frustration_rate`, `response_quality_score`, `product_engagement_rate`
    - Rank brands per metric; flag outliers (> 1 std dev from mean)
    - Classify systemic issues (> 50% of brands) and brand-specific issues (< 20% of brands)
    - Include low-engagement alert for brands with `product_engagement_rate < 0.10`
    - _Requirements: 3.4, 3.5, 4.5, 5.2, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 10.2 Write property test: drop-off rate computation
    - **Property 10: Drop-off rate computation**
    - **Validates: Requirements 3.4**

  - [ ]* 10.3 Write property test: frustration rate computation
    - **Property 11: Frustration rate computation**
    - **Validates: Requirements 3.5**

  - [ ]* 10.4 Write property test: response quality score bounds
    - **Property 14: Response quality score bounds**
    - **Validates: Requirements 4.5**

  - [ ]* 10.5 Write property test: product engagement rate computation
    - **Property 16: Product engagement rate computation**
    - **Validates: Requirements 5.2**

  - [ ]* 10.6 Write property test: low-engagement alert threshold
    - **Property 17: Low-engagement alert threshold**
    - **Validates: Requirements 5.5**

  - [ ]* 10.7 Write property test: outlier detection correctness
    - **Property 18: Outlier detection correctness**
    - **Validates: Requirements 6.3**

  - [ ]* 10.8 Write property test: systemic issue classification
    - **Property 19: Systemic issue classification**
    - **Validates: Requirements 6.4**

  - [ ]* 10.9 Write property test: brand-specific issue classification
    - **Property 20: Brand-specific issue classification**
    - **Validates: Requirements 6.5**

  - [ ]* 10.10 Write unit tests for aggregator
    - Test zero-results input produces well-formed report with empty metrics
    - Test single-brand input produces correct rates
    - Test outlier flagging with known std-dev scenario
    - _Requirements: 6.1, 6.2, 6.3, 7.6_

- [x] 11. Checkpoint — Ensure all aggregation tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement report generation (`cas/reporter.py` + Jinja2 templates)
  - [x] 12.1 Implement `generate_report(report: AggregatedReport, output_dir: str) -> None`
    - Write `report.json` with full metrics and flagged conversations
    - Write `report.md` using a Jinja2 template: summary, per-brand tables, flagged conversations, systemic/brand-specific issues
    - Handle zero-results case: produce report indicating no matches and filters applied
    - Raise `IOError` if output directory is not writable
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 12.2 Write property test: JSON report round-trip serialization
    - **Property 21: JSON report round-trip serialization**
    - **Validates: Requirements 7.3**

  - [ ]* 12.3 Write property test: JSON flagged conversation field completeness
    - **Property 22: JSON flagged conversation field completeness**
    - **Validates: Requirements 7.4**

  - [ ]* 12.4 Write unit tests for reporter
    - Test output files are created in the specified directory
    - Test JSON output contains all required top-level keys
    - Test Markdown output contains summary section and per-brand table
    - Test zero-results report includes filters applied
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 13. Implement trend storage (`cas/storage.py`)
  - [x] 13.1 Implement `save_run()` and `load_runs()` with local JSON persistence
    - Persist `BrandMetrics` per run date to a local JSON file (e.g., `runs.json`)
    - `load_runs()` returns all stored `RunRecord` objects
    - _Requirements: 8.1_

  - [x] 13.2 Implement week-over-week change computation and flagging
    - Compute WoW change as `(new - old) / old` for each per-brand metric
    - Flag regressions (WoW < -0.10) and improvements (WoW > +0.10) in the report
    - Skip WoW computation when fewer than two consecutive weeks of data exist
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 13.3 Write property test: run storage round-trip
    - **Property 23: Run storage round-trip**
    - **Validates: Requirements 8.1**

  - [ ]* 13.4 Write property test: week-over-week change computation
    - **Property 24: Week-over-week change computation**
    - **Validates: Requirements 8.2**

  - [ ]* 13.5 Write property test: directional WoW flag correctness
    - **Property 25: Directional week-over-week flag correctness**
    - **Validates: Requirements 8.3, 8.4**

  - [ ]* 13.6 Write unit tests for trend storage
    - Test save then load returns matching record
    - Test WoW regression flag triggers at exactly -10% change
    - Test WoW improvement flag triggers at exactly +10% change
    - Test insufficient history skips WoW and notes it in report
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 14. Implement CLI entry point (`cas/cli.py`)
  - Wire all stages together using `click`: ingestion → analysis → aggregation → reporting → trend storage
  - Expose `--mongo-uri`, `--widget-id`, `--date-from`, `--date-to`, `--output` options
  - Exit with non-zero status code on fatal errors
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 7.1_

- [x] 15. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` with `@settings(max_examples=100)`
- Unit tests use `pytest` with `mongomock` for MongoDB fixtures
- Checkpoints ensure incremental validation at each pipeline stage
