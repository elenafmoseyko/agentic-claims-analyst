# Agentic-claims-analyst

An AI agent that ingests raw medical claims + enrollment data (Excel or CSV) and
autonomously computes PMPM metrics, detects anomalies, and generates professional
narrative findings reports — with optional LangGraph.


---

## What it does

| Step | What happens |
|------|-------------|
| **Load** | Reads Excel / CSV — auto-detects wide exhibit or long format |
| **Calculate** | PMPM by provider, LOB, month — membership-weighted |
| **Detect** | Anomalies: spending spikes, December IBNR lag, membership shifts |
| **Export** | Excel workbook with formatted Exhibit 1 + Exhibit 2 tabs |
| **Narrate** | LLM-generated (or template) professional findings report |

---

## Quick Start (no API key needed)

```bash
git clone https://github.com/YOUR_USERNAME/agentic-claims-analyst
cd agentic-claims-analyst
pip install -r requirements.txt

# Run with your Excel file
python run_local.py --input data/your_claims_file.xlsx
```

Outputs:
- `output/exhibit_output.xlsx` — formatted Excel exhibit with two tabs
- `output/exhibit_output.md`   — narrative findings report

---

## With LangGraph + Claude AI (full agentic mode)

```bash
# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run the full agent
python -m src.agent --input data/your_claims_file.xlsx --output output/exhibit.xlsx
```

The agent autonomously:
1. Calls `load_and_validate_data` tool
2. Calls `compute_pmpm_metrics` tool
3. Calls `detect_spending_anomalies` tool
4. Calls `export_exhibit_workbook` tool
5. Synthesizes all tool outputs into a professional narrative

---

## Input Data Formats

### Format A — Long format (recommended for new data)
```
month       | lob     | provider   | members | paid_claims
2024-01-01  | HMO/POS | Provider A | 47226   | 1,102,345
```

### Format B — Wide exhibit format (Company ABC style)
The loader auto-detects and parses multi-level headers with separate columns
per LOB block (Members + Provider A/B/C PMPM per block).

---

## Project Structure
```
agentic-claims-analyst/
├── src/
│   ├── agent.py           # LangGraph agent orchestrator
│   ├── data_loader.py     # Excel/CSV ingestion + schema normalisation
│   ├── metrics.py         # PMPM calculations + anomaly detection
│   └── report_exporter.py # Excel exhibit builder (openpyxl)
├── run_local.py           # Standalone runner (no API key required)
├── data/                  # Place your input files here
├── output/                # Generated exhibits land here
├── tests/                 # Pytest test suite
└── requirements.txt
```

---

## Why this project?

This repo demonstrates the same architectural patterns used in production
document-AI and agentic automation systems:

- **Flexible schema detection** — handles messy real-world Excel files without brittle hardcoding
- **Tool-calling agent loop** — LangGraph state machine with structured tool calls
- **Separation of concerns** — loader / metrics / exporter are independently testable
- **Production-grade output** — styled Excel workbook suitable for client delivery


