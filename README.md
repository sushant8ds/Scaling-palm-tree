# Conversation Analysis System

Automated pipeline for analyzing AI assistant conversations across e-commerce brands. Ingests data from MongoDB, runs quality and engagement analyses, and produces JSON + Markdown insight reports.

## Dataset Setup

Place the MongoDB collection dump files in the `data/` directory:

```
data/
  conversations.json
  messages.json
```

Then import them into MongoDB:

```bash
mongoimport --db helio_intern --collection conversations --file data/conversations.json --jsonArray
mongoimport --db helio_intern --collection messages --file data/messages.json --jsonArray
```

## Installation

```bash
pip install -e ".[dev]"
```

Or install runtime dependencies only:

```bash
pip install -e .
```

## Usage

```bash
python -m cas analyze \
  --mongo-uri mongodb://localhost:27017 \
  --widget-id <brand-widget-id> \
  --date-from 2024-01-01 \
  --date-to 2024-01-31 \
  --output ./output
```

### CLI Options

| Option | Description | Default |
|---|---|---|
| `--mongo-uri` | MongoDB connection URI | `mongodb://localhost:27017` |
| `--widget-id` | Filter analysis to a specific brand | All brands |
| `--date-from` | Start date for conversation filter (YYYY-MM-DD) | No lower bound |
| `--date-to` | End date for conversation filter (YYYY-MM-DD) | No upper bound |
| `--output` | Directory to write report files | `./output` |

Reports are written to the output directory as `report.json` and `report.md`.

## Running Tests

```bash
pytest
```
