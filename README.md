# Finance Explain

Finance Explain is a `FastAPI` application with both:

- a browser UI for uploading a P&L and reviewing results
- a JSON API for direct integrations

It turns a startup Profit & Loss statement into structured financial metrics, founder-friendly summaries, AI-generated CFO analysis, and what-if scenario reviews.

## Project Structure

```text
finance_explain/
|- app.py
|- static/
|  `- index.html
|- requirements.txt
|- sample_pnl.csv
`- README.md
```

## Why FastAPI

- Native request validation for scenario inputs
- Clean file upload support for CSV and Excel files
- JSON responses that are easy to connect to a web or mobile frontend
- Simple serving of the included browser UI from the same process
- Built-in interactive API docs at `/docs`

## Features

- Upload CSV or Excel P&L files
- Validate and normalize `Revenue`, `Expenses`, `Profit`, and `Month`
- Auto-calculate missing profit values
- Use the browser UI directly at `/`
- Return top-level KPI metrics and a preview of uploaded data
- Generate AI CFO analysis using OpenAI or Gemini
- Run what-if scenarios for growth, hiring, and marketing decisions
- Return structured scenario comparisons and optional AI scenario review

## Requirements

- Python 3.11+
- An API key for either OpenAI or Gemini if you want AI-generated output

## Installation

1. Move into the project folder:

```bash
cd finance_explain
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

Set one of the following API keys before running the API.

### Option 1: OpenAI

```powershell
$env:OPENAI_API_KEY="your_openai_api_key"
```

Optional model override:

```powershell
$env:OPENAI_MODEL="gpt-4o-mini"
```

### Option 2: Gemini

```powershell
$env:GEMINI_API_KEY="your_gemini_api_key"
```

Optional model override:

```powershell
$env:GEMINI_MODEL="gemini-2.5-flash"
```

## Run the Application

```bash
uvicorn app:app --reload
```

Then open:

- App UI: `http://127.0.0.1:8000/`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Browser UI

The main browser interface is served from `/`.

Use it like this:

1. Start the server with `uvicorn app:app --reload`
2. Open `http://127.0.0.1:8000/`
3. Upload `sample_pnl.csv` or your own CSV/XLS/XLSX file
4. Optionally pick `OpenAI` or `Gemini`, or leave provider on auto-detect
5. Run base business analysis
6. Run a scenario review with custom assumptions or a preset

## API Overview

### `GET /`

Serves the browser UI.

### `GET /api`

Returns a small API overview and the available scenario presets.

### `GET /health`

Returns service health and the configured AI provider, if any.

### `GET /presets`

Returns the built-in scenario presets.

### `POST /analyze`

Multipart form fields:

- `file`: required CSV/XLS/XLSX file
- `include_ai`: optional boolean, default `true`
- `provider`: optional `OpenAI` or `Gemini`

Response includes:

- normalized metrics
- financial summary text
- uploaded data preview
- optional AI CFO analysis

Example `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "file=@sample_pnl.csv" \
  -F "include_ai=false"
```

### `POST /scenario`

Multipart form fields:

- `file`: required CSV/XLS/XLSX file
- `revenue_growth`: optional number, default `0`
- `expense_change`: optional number, default `0`
- `new_employees`: optional integer, default `0`
- `monthly_cost_per_employee`: optional number, default `6000`
- `marketing_spend_increase`: optional number, default `0`
- `include_ai_review`: optional boolean, default `true`
- `provider`: optional `OpenAI` or `Gemini`

Response includes:

- current metrics
- scenario inputs
- scenario metrics
- change comparison
- optional AI scenario review

Example `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/scenario" \
  -F "file=@sample_pnl.csv" \
  -F "revenue_growth=20" \
  -F "expense_change=10" \
  -F "new_employees=3" \
  -F "monthly_cost_per_employee=6000" \
  -F "marketing_spend_increase=15" \
  -F "include_ai_review=false"
```

## Expected Input Columns

The API expects columns such as:

- `Revenue`
- `Expenses`
- `Profit` optional
- `Month` optional but useful for trend summaries

If `Profit` is missing, the API calculates:

```text
Profit = Revenue - Expenses
```

## Notes

- This is still an MVP backend, not a full finance platform.
- No authentication, database, background jobs, or persistent storage is included.
- The next logical step is to place a separate frontend on top of these endpoints.
