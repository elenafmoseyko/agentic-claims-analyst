# Company ABC – Medical Claims Analysis Report

## Executive Summary

This report presents a comprehensive analysis of Company ABC's medical claims and enrollment data. Over the period analyzed, total membership averaged **292,862** members per month, ranging from a low of **285,231** to a high of **300,312**.

## Membership Overview

Membership remained relatively stable throughout the period, with only modest fluctuations across all lines of business. The HMO/POS line of business consistently maintained the largest member population, while Medicare had the smallest membership base.

## PMPM Spending by Provider

Provider A consistently drove the highest per-member per-month spending with an annual average of **$22.5**, significantly exceeding Provider B ($2.29) and Provider C ($0.49). This disparity warrants further investigation into Provider A's service mix and unit cost structure.

## PMPM Spending by Line of Business

Among the lines of business, PPO recorded the highest average PMPM for Provider A, suggesting a higher-acuity or richer benefit design relative to other segments. Medicare had the lowest average PMPM, which may reflect program-specific utilization controls or lower service intensity.

## Anomalies and Notable Findings

**December Seasonality:** December PMPM ($4.75) is 45.7% below the Jan–Nov average ($8.76). Likely reflects IBNR lag or provider payment timing. This pattern is common in healthcare claims data and typically reflects Incurred-But-Not-Reported (IBNR) lag rather than a true reduction in utilization.

**Additional Anomalies Detected:**
- Provider B PMPM dropped 49.6% from Nov ($2.27) to Dec ($1.15).
- Provider C PMPM dropped 52.1% from Nov ($0.50) to Dec ($0.24).

## Methodology

All PMPM figures are calculated as membership-weighted averages across lines of business. Claims are incurred-basis, paid through the end of the period. Anomalies are detected using a combination of z-score analysis (±2 standard deviations) and month-over-month change thresholds (>25% decline).

## Recommendations

1. **Investigate Provider A cost drivers** — at $22.5 average PMPM, Provider A warrants a deeper unit-cost and utilization review.
2. **Monitor December runout** — establish a reserving process to account for IBNR claims not captured in the paid-through date.
3. **LOB benchmarking** — compare PPO PMPM against market benchmarks to assess competitive positioning.
4. **Membership retention analysis** — given the gradual membership decline observed toward year-end, conduct a lapse and disenrollment study.