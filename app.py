import io
import os
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from google import genai
from openai import OpenAI
from pydantic import BaseModel

# Load environment variables from a .env file if present
load_dotenv()



SYSTEM_PROMPT = """
You are an experienced startup CFO. Analyze the financial data provided and generate founder-friendly business insights. Focus on business decisions rather than accounting terminology. Provide responses under the following headings:

1. What's Going Well
2. Potential Risks
3. Recommended Actions

Keep the response concise, actionable, and easy for a startup founder to understand.
""".strip()


SCENARIO_SYSTEM_PROMPT = """
You are an experienced startup CFO reviewing a founder's financial scenario.
Answer under these headings:

1. Is This Scenario Financially Healthy?
2. Risks Introduced
3. Opportunities Created
4. Recommendation
5. What Management Should Monitor

Keep the response concise, practical, and decision-oriented.
""".strip()


PRESET_SCENARIOS = {
    "Aggressive Growth": {
        "revenue_growth": 30,
        "expense_change": 15,
        "new_employees": 0,
        "monthly_cost_per_employee": 6000,
        "marketing_spend_increase": 0,
    },
    "Cost Optimization": {
        "revenue_growth": 0,
        "expense_change": -10,
        "new_employees": 0,
        "monthly_cost_per_employee": 6000,
        "marketing_spend_increase": 0,
    },
    "Hire 5 Employees": {
        "revenue_growth": 0,
        "expense_change": 0,
        "new_employees": 5,
        "monthly_cost_per_employee": 6000,
        "marketing_spend_increase": 0,
    },
    "Market Expansion": {
        "revenue_growth": 20,
        "expense_change": 0,
        "new_employees": 0,
        "monthly_cost_per_employee": 6000,
        "marketing_spend_increase": 25,
    },
}


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


class ScenarioInputs(BaseModel):
    revenue_growth: float = 0
    expense_change: float = 0
    new_employees: int = 0
    monthly_cost_per_employee: float = 6000
    marketing_spend_increase: float = 0


app = FastAPI(
    title="Finance Explain API",
    description="Upload a P&L and receive CFO-style financial insights and scenario analysis.",
    version="1.0.0",
)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]

    rename_map = {}
    for column in normalized.columns:
        lowered = column.lower()
        if lowered == "revenue":
            rename_map[column] = "Revenue"
        elif lowered == "expenses":
            rename_map[column] = "Expenses"
        elif lowered == "profit":
            rename_map[column] = "Profit"
        elif lowered == "month":
            rename_map[column] = "Month"

    return normalized.rename(columns=rename_map)


def parse_uploaded_file_bytes(filename: str, raw_bytes: bytes) -> pd.DataFrame:
    suffix = filename.lower()

    if suffix.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw_bytes))
    if suffix.endswith(".xlsx") or suffix.endswith(".xls"):
        return pd.read_excel(io.BytesIO(raw_bytes))

    raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")


def validate_and_prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    prepared = normalize_columns(df)

    if "Revenue" not in prepared.columns or "Expenses" not in prepared.columns:
        raise ValueError("The file must include Revenue and Expenses columns.")

    for column in ["Revenue", "Expenses"]:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    if prepared[["Revenue", "Expenses"]].isna().all().any():
        raise ValueError("Revenue and Expenses columns must contain numeric values.")

    prepared["Revenue"] = prepared["Revenue"].fillna(0)
    prepared["Expenses"] = prepared["Expenses"].fillna(0)

    if "Profit" in prepared.columns:
        prepared["Profit"] = pd.to_numeric(prepared["Profit"], errors="coerce")
        prepared["Profit"] = prepared["Profit"].fillna(prepared["Revenue"] - prepared["Expenses"])
    else:
        prepared["Profit"] = prepared["Revenue"] - prepared["Expenses"]

    return prepared


def calculate_metrics(df: pd.DataFrame) -> dict:
    total_revenue = float(df["Revenue"].sum())
    total_expenses = float(df["Expenses"].sum())
    net_profit = float(df["Profit"].sum())
    profit_margin = (net_profit / total_revenue * 100) if total_revenue else 0.0

    return {
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
    }


def format_currency(value: float) -> str:
    return f"${value:,.0f}"


def trend_summary(df: pd.DataFrame, metric: str) -> str:
    if "Month" not in df.columns or len(df) < 2:
        return f"{metric} trend data is not available."

    trend_df = df[["Month", metric]].copy()
    trend_df[metric] = pd.to_numeric(trend_df[metric], errors="coerce").fillna(0)

    start_value = float(trend_df[metric].iloc[0])
    end_value = float(trend_df[metric].iloc[-1])
    change = end_value - start_value
    change_pct = (change / start_value * 100) if start_value else 0.0

    if change > 0:
        direction = "increased"
    elif change < 0:
        direction = "decreased"
    else:
        direction = "stayed flat"

    start_month = str(trend_df["Month"].iloc[0])
    end_month = str(trend_df["Month"].iloc[-1])
    average_value = float(trend_df[metric].mean())

    return (
        f"{metric} {direction} from {format_currency(start_value)} in {start_month} "
        f"to {format_currency(end_value)} in {end_month} "
        f"({change_pct:+.1f}%). Average {metric.lower()} was {format_currency(average_value)}."
    )


def build_financial_summary(df: pd.DataFrame, metrics: dict) -> str:
    summary_lines = [
        "Financial summary:",
        f"- Total Revenue: {format_currency(metrics['total_revenue'])}",
        f"- Total Expenses: {format_currency(metrics['total_expenses'])}",
        f"- Net Profit: {format_currency(metrics['net_profit'])}",
        f"- Profit Margin: {metrics['profit_margin']:.1f}%",
        f"- Revenue trend: {trend_summary(df, 'Revenue')}",
        f"- Expense trend: {trend_summary(df, 'Expenses')}",
    ]

    if "Month" in df.columns:
        monthly_snapshot = df[["Month", "Revenue", "Expenses", "Profit"]].head(12)
        summary_lines.append("- Monthly snapshot:")
        for _, row in monthly_snapshot.iterrows():
            summary_lines.append(
                f"  - {row['Month']}: Revenue {format_currency(row['Revenue'])}, "
                f"Expenses {format_currency(row['Expenses'])}, Profit {format_currency(row['Profit'])}"
            )

    return "\n".join(summary_lines)


def detect_provider() -> Optional[str]:
    if os.getenv("GEMINI_API_KEY"):
        return "Gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "OpenAI"
    return None


def resolve_provider(requested_provider: Optional[str]) -> str:
    if requested_provider:
        normalized = requested_provider.strip().lower()
        if normalized == "gemini" and os.getenv("GEMINI_API_KEY"):
            return "Gemini"
        if normalized == "openai" and os.getenv("OPENAI_API_KEY"):
            return "OpenAI"
        raise ValueError(f"Requested provider '{requested_provider}' is not configured.")

    provider = detect_provider()
    if not provider:
        raise ValueError("No supported AI provider is configured.")
    return provider


def generate_ai_analysis(summary: str, provider: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    if provider == "OpenAI":
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": summary},
            ],
        )
        return response.output_text

    if provider == "Gemini":
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=f"{system_prompt}\n\n{summary}",
        )
        return response.text

    raise ValueError("No supported AI provider is configured.")


def get_analysis_periods(df: pd.DataFrame) -> int:
    if "Month" in df.columns and len(df) > 0:
        return len(df)
    return 12


def run_scenario(metrics: dict, periods: int, inputs: dict) -> dict:
    current_revenue = metrics["total_revenue"]
    current_expenses = metrics["total_expenses"]

    scenario_revenue = current_revenue * (1 + inputs["revenue_growth"] / 100)
    adjusted_expenses = current_expenses * (1 + inputs["expense_change"] / 100)
    employee_cost = inputs["new_employees"] * inputs["monthly_cost_per_employee"] * periods
    marketing_cost = current_expenses * (inputs["marketing_spend_increase"] / 100)
    scenario_expenses = adjusted_expenses + employee_cost + marketing_cost
    scenario_profit = scenario_revenue - scenario_expenses
    scenario_margin = (scenario_profit / scenario_revenue * 100) if scenario_revenue else 0.0

    return {
        "total_revenue": scenario_revenue,
        "total_expenses": scenario_expenses,
        "net_profit": scenario_profit,
        "profit_margin": scenario_margin,
        "employee_cost": employee_cost,
        "marketing_cost": marketing_cost,
        "periods": periods,
    }


def build_scenario_summary(current_metrics: dict, scenario_metrics: dict, inputs: dict) -> str:
    return "\n".join(
        [
            "Current business metrics:",
            f"- Revenue: {format_currency(current_metrics['total_revenue'])}",
            f"- Expenses: {format_currency(current_metrics['total_expenses'])}",
            f"- Profit: {format_currency(current_metrics['net_profit'])}",
            f"- Profit Margin: {current_metrics['profit_margin']:.1f}%",
            "",
            "Scenario assumptions:",
            f"- Revenue Growth: {inputs['revenue_growth']}%",
            f"- Expense Change: {inputs['expense_change']}%",
            f"- New Employees: {inputs['new_employees']}",
            f"- Monthly Cost Per Employee: {format_currency(inputs['monthly_cost_per_employee'])}",
            f"- Marketing Spend Increase: {inputs['marketing_spend_increase']}%",
            "",
            "Scenario results:",
            f"- Revenue: {format_currency(scenario_metrics['total_revenue'])}",
            f"- Expenses: {format_currency(scenario_metrics['total_expenses'])}",
            f"- Profit: {format_currency(scenario_metrics['net_profit'])}",
            f"- Profit Margin: {scenario_metrics['profit_margin']:.1f}%",
            f"- Added Employee Cost: {format_currency(scenario_metrics['employee_cost'])}",
            f"- Added Marketing Cost: {format_currency(scenario_metrics['marketing_cost'])}",
        ]
    )


def build_comparison(current_metrics: dict, scenario_metrics: dict) -> dict:
    return {
        "revenue_change": scenario_metrics["total_revenue"] - current_metrics["total_revenue"],
        "expenses_change": scenario_metrics["total_expenses"] - current_metrics["total_expenses"],
        "profit_change": scenario_metrics["net_profit"] - current_metrics["net_profit"],
        "margin_change": scenario_metrics["profit_margin"] - current_metrics["profit_margin"],
    }


def dataframe_preview(df: pd.DataFrame, max_rows: int = 20) -> list[dict]:
    preview_df = df.head(max_rows).copy()
    preview_df = preview_df.where(pd.notnull(preview_df), None)
    return preview_df.to_dict(orient="records")


async def load_financial_dataframe(file: UploadFile) -> pd.DataFrame:
    if not file.filename:
        raise ValueError("Uploaded file must have a filename.")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise ValueError("Uploaded file is empty.")

    raw_df = parse_uploaded_file_bytes(file.filename, raw_bytes)
    return validate_and_prepare_data(raw_df)


def parse_bool(value: bool) -> bool:
    return value


def scenario_inputs_from_form(
    revenue_growth: float,
    expense_change: float,
    new_employees: int,
    monthly_cost_per_employee: float,
    marketing_spend_increase: float,
) -> ScenarioInputs:
    return ScenarioInputs(
        revenue_growth=revenue_growth,
        expense_change=expense_change,
        new_employees=new_employees,
        monthly_cost_per_employee=monthly_cost_per_employee,
        marketing_spend_increase=marketing_spend_increase,
    )


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api")
def api_root() -> dict:
    return {
        "message": "Finance Explain API",
        "docs_url": "/docs",
        "available_presets": list(PRESET_SCENARIOS.keys()),
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "configured_provider": detect_provider(),
    }


@app.get("/presets")
def presets() -> dict:
    return PRESET_SCENARIOS


@app.post("/analyze")
async def analyze_financials(
    file: UploadFile = File(...),
    include_ai: bool = Form(True),
    provider: Optional[Literal["OpenAI", "Gemini", "openai", "gemini"]] = Form(None),
) -> dict:
    try:
        financial_df = await load_financial_dataframe(file)
        metrics = calculate_metrics(financial_df)
        summary = build_financial_summary(financial_df, metrics)

        response = {
            "filename": file.filename,
            "provider": None,
            "metrics": metrics,
            "summary": summary,
            "data_preview": dataframe_preview(financial_df),
            "row_count": int(len(financial_df)),
            "analysis_periods": get_analysis_periods(financial_df),
            "ai_analysis": None,
        }

        if parse_bool(include_ai):
            resolved_provider = resolve_provider(provider)
            response["provider"] = resolved_provider
            response["ai_analysis"] = generate_ai_analysis(summary, resolved_provider)

        return response
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Something went wrong while processing the file: {error}") from error


@app.post("/scenario")
async def analyze_scenario(
    file: UploadFile = File(...),
    revenue_growth: float = Form(0),
    expense_change: float = Form(0),
    new_employees: int = Form(0),
    monthly_cost_per_employee: float = Form(6000),
    marketing_spend_increase: float = Form(0),
    include_ai_review: bool = Form(True),
    provider: Optional[Literal["OpenAI", "Gemini", "openai", "gemini"]] = Form(None),
) -> dict:
    try:
        financial_df = await load_financial_dataframe(file)
        metrics = calculate_metrics(financial_df)
        periods = get_analysis_periods(financial_df)
        inputs = scenario_inputs_from_form(
            revenue_growth=revenue_growth,
            expense_change=expense_change,
            new_employees=new_employees,
            monthly_cost_per_employee=monthly_cost_per_employee,
            marketing_spend_increase=marketing_spend_increase,
        ).model_dump()

        scenario_metrics = run_scenario(metrics, periods, inputs)
        scenario_summary = build_scenario_summary(metrics, scenario_metrics, inputs)

        response = {
            "filename": file.filename,
            "provider": None,
            "current_metrics": metrics,
            "scenario_inputs": inputs,
            "scenario_metrics": scenario_metrics,
            "comparison": build_comparison(metrics, scenario_metrics),
            "scenario_summary": scenario_summary,
            "ai_review": None,
        }

        if parse_bool(include_ai_review):
            resolved_provider = resolve_provider(provider)
            response["provider"] = resolved_provider
            response["ai_review"] = generate_ai_analysis(
                scenario_summary,
                resolved_provider,
                system_prompt=SCENARIO_SYSTEM_PROMPT,
            )

        return response
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Something went wrong while processing the file: {error}") from error
