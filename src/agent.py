"""
agentic-claims-analyst / src/agent.py
======================================
LangGraph-based AI agent that ingests raw claims + enrollment data
(Excel or CSV) and autonomously:
  1. Validates & cleans the data
  2. Calculates PMPM metrics per provider and line of business
  3. Detects anomalies (spend spikes, December drops, LOB outliers)
  4. Generates a natural-language narrative findings report
  5. Exports an Excel exhibit workbook

Usage:
    python src/agent.py --input data/claims.xlsx
    python src/agent.py --input data/claims.csv --output my_report.xlsx
"""

import argparse
import json
import os
from pathlib import Path
from typing import Annotated, Any, TypedDict

import pandas as pd
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .data_loader import load_claims_data
from .metrics import (
    calculate_pmpm,
    calculate_summary,
    detect_anomalies,
    membership_by_lob,
)
from .report_exporter import export_excel_exhibit

# ── LLM setup ────────────────────────────────────────────────────────────────
LLM = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0.2)

# ── Agent State ───────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list, "conversation messages"]
    data_path: str
    raw_df: Any          # pandas DataFrame (serialized as JSON string for state)
    metrics: dict        # calculated PMPM / summary metrics
    anomalies: list      # detected anomalies
    narrative: str       # LLM-generated narrative
    output_path: str


# ── Tools (callable by the LLM agent) ─────────────────────────────────────────
@tool
def load_and_validate_data(file_path: str) -> str:
    """
    Load claims + enrollment data from an Excel or CSV file.
    Returns a JSON summary of the loaded dataset including shape,
    columns, date range, and lines of business detected.
    """
    try:
        df = load_claims_data(file_path)
        summary = {
            "rows": len(df),
            "columns": list(df.columns),
            "months_detected": sorted(df["month"].astype(str).unique().tolist()),
            "lines_of_business": df["lob"].unique().tolist() if "lob" in df.columns else [],
            "providers": df["provider"].unique().tolist() if "provider" in df.columns else [],
            "total_members": int(df["members"].sum()) if "members" in df.columns else None,
            "date_range": f"{df['month'].min()} → {df['month'].max()}" if "month" in df.columns else "unknown",
            "status": "loaded_successfully",
        }
        return json.dumps(summary, default=str)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def compute_pmpm_metrics(file_path: str) -> str:
    """
    Compute Per-Member Per-Month (PMPM) metrics from the claims file.
    Returns a JSON object with:
    - pmpm_by_provider_month: overall PMPM per provider per month
    - pmpm_by_lob_provider: PMPM broken down by line of business and provider
    - membership_summary: monthly membership counts by LOB
    - annual_averages: full-year weighted average PMPMs
    """
    try:
        df = load_claims_data(file_path)
        pmpm_df = calculate_pmpm(df)
        summary_df = calculate_summary(df)
        membership_df = membership_by_lob(df)

        result = {
            "pmpm_by_provider_month": pmpm_df.to_dict(orient="records"),
            "pmpm_by_lob_provider": summary_df.to_dict(orient="records"),
            "membership_by_lob_month": membership_df.to_dict(orient="records"),
            "annual_averages": {
                row["provider"]: round(row["annual_pmpm_avg"], 2)
                for _, row in summary_df.groupby("provider")["pmpm"].mean().reset_index().iterrows()
            } if "provider" in summary_df.columns and "pmpm" in summary_df.columns else {},
        }
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def detect_spending_anomalies(file_path: str) -> str:
    """
    Detect anomalies in the claims data:
    - Month-over-month PMPM drops > 25%
    - Provider spend spikes (> 2 standard deviations from mean)
    - LOB membership changes > 10%
    - December seasonality effects
    Returns a list of detected anomalies with descriptions.
    """
    try:
        df = load_claims_data(file_path)
        anomalies = detect_anomalies(df)
        return json.dumps({"anomalies": anomalies, "count": len(anomalies)}, default=str)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def export_exhibit_workbook(file_path: str, output_path: str) -> str:
    """
    Generate an Excel exhibit workbook from the claims data.
    Creates two tabs:
    - Exhibit 1 – Summary: Monthly PMPM trend + membership by provider
    - Exhibit 2 – Detail: Month-by-month breakdown by LOB and provider
    Returns the path to the created workbook.
    """
    try:
        df = load_claims_data(file_path)
        result_path = export_excel_exhibit(df, output_path)
        return json.dumps({"status": "success", "output_path": result_path})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


TOOLS = [
    load_and_validate_data,
    compute_pmpm_metrics,
    detect_spending_anomalies,
    export_exhibit_workbook,
]

LLM_WITH_TOOLS = LLM.bind_tools(TOOLS)


# ── Graph Nodes ────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert healthcare actuarial analyst AI agent.
Your job is to analyze medical claims and enrollment data and produce professional,
insight-rich reports for insurance carriers.

When given a data file, you will:
1. First load and validate the data using the load_and_validate_data tool
2. Compute PMPM metrics using compute_pmpm_metrics tool
3. Detect anomalies using detect_spending_anomalies tool
4. Export an Excel exhibit using export_exhibit_workbook tool
5. Then synthesize all findings into a clear, professional narrative report

Your narrative should cover:
- Overall membership trends and stability
- PMPM spending by provider (who is highest/lowest, trends over time)
- PMPM spending by line of business (HMO/POS, PPO, Medicaid, Medicare)
- Notable anomalies (December drops, seasonal patterns, outliers)
- Key takeaways and recommendations for the carrier

Write in a professional but accessible tone suitable for a client deliverable.
Use specific numbers from the data. Structure with clear headers."""


def analyst_node(state: AgentState) -> AgentState:
    """Main LLM agent node — reasons and calls tools."""
    messages = state["messages"]
    if not messages:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Please analyze the claims data at: {state['data_path']}\n"
                        f"Export the exhibit to: {state['output_path']}\n"
                        "Run a complete analysis and generate a narrative findings report."
            ),
        ]
    response = LLM_WITH_TOOLS.invoke(messages)
    return {**state, "messages": messages + [response]}


def should_continue(state: AgentState) -> str:
    """Route: if the LLM called tools → run them; otherwise → finalize."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "finalize"


def finalize_node(state: AgentState) -> AgentState:
    """Extract the final narrative from the last AI message."""
    last = state["messages"][-1]
    narrative = last.content if isinstance(last.content, str) else str(last.content)
    return {**state, "narrative": narrative}


# ── Build the LangGraph ────────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("analyst", analyst_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "analyst")
    graph.add_conditional_edges("analyst", should_continue, {
        "tools": "tools",
        "finalize": "finalize",
    })
    graph.add_edge("tools", "analyst")   # loop back after tool execution
    graph.add_edge("finalize", END)

    return graph.compile()


# ── CLI Entry Point ────────────────────────────────────────────────────────────
def run_agent(input_path: str, output_path: str = "exhibit_output.xlsx") -> str:
    """Run the full agentic claims analysis pipeline."""
    graph = build_graph()

    print(f"\n🤖 Starting Agentic Claims Analyst...")
    print(f"   Input : {input_path}")
    print(f"   Output: {output_path}\n")

    initial_state: AgentState = {
        "messages": [],
        "data_path": input_path,
        "raw_df": None,
        "metrics": {},
        "anomalies": [],
        "narrative": "",
        "output_path": output_path,
    }

    final_state = graph.invoke(initial_state, {"recursion_limit": 20})
    narrative = final_state.get("narrative", "")

    # Save narrative report
    report_path = Path(output_path).with_suffix(".md")
    report_path.write_text(f"# Claims Analysis Report\n\n{narrative}")
    print(f"\n✅ Narrative report saved → {report_path}")
    print(f"✅ Excel exhibit saved    → {output_path}\n")
    return narrative


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentic Claims Analyst")
    parser.add_argument("--input",  required=True, help="Path to claims Excel or CSV file")
    parser.add_argument("--output", default="exhibit_output.xlsx", help="Output Excel path")
    args = parser.parse_args()

    narrative = run_agent(args.input, args.output)
    print("─" * 60)
    print(narrative)
