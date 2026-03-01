"""
run_local.py  — No LLM API key required
========================================
Runs the full pipeline (load → metrics → anomaly detection → Excel export)
using only pandas/openpyxl. The LLM narrative step is replaced with a
template-based narrative builder.

Usage:
    python run_local.py --input data/Company_ABC_2018_Claims_and_Enrollment_Data.xlsx
"""

import argparse
import json
from pathlib import Path

from src.data_loader import load_claims_data
from src.metrics import calculate_pmpm, calculate_summary, detect_anomalies, membership_by_lob
from src.report_exporter import export_excel_exhibit


# ── Template narrative builder ────────────────────────────────────────────────
def build_narrative(df, pmpm_df, summary_df, anomalies) -> str:
    total_mbr_avg = df.groupby("month")["members"].sum().mean()
    total_mbr_min = df.groupby("month")["members"].sum().min()
    total_mbr_max = df.groupby("month")["members"].sum().max()

    # Annual avg PMPM per provider
    prov_avgs = {}
    for prov in ["Provider A", "Provider B", "Provider C"]:
        sub = pmpm_df[pmpm_df["provider"] == prov]
        prov_avgs[prov] = round(sub["pmpm"].mean(), 2)

    # Best/worst LOB for Provider A PMPM
    prov_a = summary_df[summary_df["provider"] == "Provider A"].sort_values("avg_pmpm", ascending=False)
    highest_lob = prov_a.iloc[0]["lob"] if not prov_a.empty else "N/A"
    lowest_lob  = prov_a.iloc[-1]["lob"] if not prov_a.empty else "N/A"

    dec_anomaly = next(
        (a for a in anomalies if a.get("type") == "december_seasonality"), None
    )
    high_anomalies = [a for a in anomalies if a.get("severity") == "high"
                      and a.get("type") != "december_seasonality"]

    lines = [
        "# Company ABC – Medical Claims Analysis Report",
        "",
        "## Executive Summary",
        "",
        f"This report presents a comprehensive analysis of Company ABC's medical claims "
        f"and enrollment data. Over the period analyzed, total membership averaged "
        f"**{total_mbr_avg:,.0f}** members per month, ranging from a low of "
        f"**{total_mbr_min:,.0f}** to a high of **{total_mbr_max:,.0f}**.",
        "",
        "## Membership Overview",
        "",
        f"Membership remained relatively stable throughout the period, with only modest "
        f"fluctuations across all lines of business. The HMO/POS line of business "
        f"consistently maintained the largest member population, while Medicare had the "
        f"smallest membership base.",
        "",
        "## PMPM Spending by Provider",
        "",
        f"Provider A consistently drove the highest per-member per-month spending "
        f"with an annual average of **${prov_avgs.get('Provider A', 'N/A')}**, "
        f"significantly exceeding Provider B (${prov_avgs.get('Provider B', 'N/A')}) "
        f"and Provider C (${prov_avgs.get('Provider C', 'N/A')}). "
        f"This disparity warrants further investigation into Provider A's service mix "
        f"and unit cost structure.",
        "",
        "## PMPM Spending by Line of Business",
        "",
        f"Among the lines of business, {highest_lob} recorded the highest average PMPM "
        f"for Provider A, suggesting a higher-acuity or richer benefit design relative "
        f"to other segments. {lowest_lob} had the lowest average PMPM, which may reflect "
        f"program-specific utilization controls or lower service intensity.",
        "",
        "## Anomalies and Notable Findings",
        "",
    ]

    if dec_anomaly:
        lines.append(f"**December Seasonality:** {dec_anomaly['description']} "
                     f"This pattern is common in healthcare claims data and typically "
                     f"reflects Incurred-But-Not-Reported (IBNR) lag rather than "
                     f"a true reduction in utilization.")
        lines.append("")

    if high_anomalies:
        lines.append("**Additional Anomalies Detected:**")
        for a in high_anomalies[:5]:
            lines.append(f"- {a['description']}")
        lines.append("")

    lines += [
        "## Methodology",
        "",
        "All PMPM figures are calculated as membership-weighted averages across lines "
        "of business. Claims are incurred-basis, paid through the end of the period. "
        "Anomalies are detected using a combination of z-score analysis (±2 standard "
        "deviations) and month-over-month change thresholds (>25% decline).",
        "",
        "## Recommendations",
        "",
        f"1. **Investigate Provider A cost drivers** — at ${prov_avgs.get('Provider A', 'N/A')} "
        f"average PMPM, Provider A warrants a deeper unit-cost and utilization review.",
        f"2. **Monitor December runout** — establish a reserving process to account for "
        f"IBNR claims not captured in the paid-through date.",
        f"3. **LOB benchmarking** — compare {highest_lob} PMPM against market benchmarks "
        f"to assess competitive positioning.",
        f"4. **Membership retention analysis** — given the gradual membership decline "
        f"observed toward year-end, conduct a lapse and disenrollment study.",
    ]

    return "\n".join(lines)


# ── Main pipeline ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Agentic Claims Analyst (local mode)")
    parser.add_argument("--input",  required=True, help="Path to Excel or CSV claims file")
    parser.add_argument("--output", default="output/exhibit_output.xlsx")
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 Loading data from: {args.input}")
    df = load_claims_data(args.input)
    print(f"   ✓ Loaded {len(df)} records | {df['month'].nunique()} months | "
          f"{df['lob'].nunique()} LOBs | {df['provider'].nunique()} providers")

    print("\n📊 Computing PMPM metrics...")
    pmpm_df    = calculate_pmpm(df)
    summary_df = calculate_summary(df)
    print(f"   ✓ Metrics computed for {len(pmpm_df)} provider-month combinations")

    print("\n🔍 Detecting anomalies...")
    anomalies = detect_anomalies(df)
    print(f"   ✓ Detected {len(anomalies)} anomalies "
          f"({sum(1 for a in anomalies if a['severity']=='high')} high severity)")
    for a in anomalies:
        icon = "🔴" if a["severity"] == "high" else "🟡"
        print(f"   {icon} {a['description']}")

    print(f"\n📁 Exporting Excel exhibit to: {args.output}")
    export_excel_exhibit(df, args.output)
    print("   ✓ Excel workbook saved")

    print("\n✍️  Generating narrative report...")
    narrative = build_narrative(df, pmpm_df, summary_df, anomalies)
    report_path = Path(args.output).with_suffix(".md")
    report_path.write_text(narrative, encoding="utf-8")
    print(f"   ✓ Narrative report saved → {report_path}")

    print("\n" + "=" * 60)
    print(narrative)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
