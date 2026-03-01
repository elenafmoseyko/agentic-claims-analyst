"""
src/metrics.py
==============
All actuarial / statistical calculations.

Functions:
  calculate_pmpm()        → monthly PMPM per provider across all LOBs
  calculate_summary()     → PMPM by LOB + provider
  membership_by_lob()     → monthly membership by LOB
  detect_anomalies()      → list of dicts describing detected anomalies
"""

import numpy as np
import pandas as pd


# ── Core metrics ───────────────────────────────────────────────────────────────
def calculate_pmpm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute weighted-average PMPM per provider per month, across all LOBs.
    Returns a DataFrame with columns: month | provider | pmpm | members
    """
    grp = (
        df.groupby(["month", "provider"])
        .apply(lambda g: pd.Series({
            "pmpm":    _weighted_avg(g, "pmpm", "members"),
            "members": g["members"].sum(),
        }))
        .reset_index()
    )
    grp["month_label"] = pd.to_datetime(grp["month"]).dt.strftime("%b")
    return grp.sort_values(["month", "provider"])


def calculate_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    PMPM summary by LOB and provider.
    Returns: lob | provider | avg_pmpm | total_members | total_paid
    """
    grp = (
        df.groupby(["lob", "provider"])
        .apply(lambda g: pd.Series({
            "avg_pmpm":     _weighted_avg(g, "pmpm", "members"),
            "total_members": g["members"].sum(),
            "total_paid":   g["paid_claims"].sum() if "paid_claims" in g.columns else None,
        }))
        .reset_index()
    )
    return grp.sort_values(["lob", "provider"])


def membership_by_lob(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly membership aggregated by LOB."""
    grp = (
        df.groupby(["month", "lob"])["members"]
        .sum()
        .reset_index()
        .sort_values(["month", "lob"])
    )
    grp["month_label"] = pd.to_datetime(grp["month"]).dt.strftime("%b")
    return grp


# ── Anomaly detection ──────────────────────────────────────────────────────────
def detect_anomalies(df: pd.DataFrame, spike_std_thresh: float = 2.0,
                     mom_drop_thresh: float = 0.25) -> list[dict]:
    """
    Detect anomalies in claims data.  Returns a list of anomaly dicts, each with:
        type, description, month, provider, lob (where applicable), severity
    """
    anomalies = []
    pmpm_df = calculate_pmpm(df)

    for provider, grp in pmpm_df.groupby("provider"):
        grp = grp.sort_values("month").reset_index(drop=True)
        pmpm_vals = grp["pmpm"].values

        # 1. Statistical spike / trough detection (z-score)
        mean, std = np.nanmean(pmpm_vals), np.nanstd(pmpm_vals)
        for i, (_, row) in enumerate(grp.iterrows()):
            z = (row["pmpm"] - mean) / std if std > 0 else 0
            if abs(z) > spike_std_thresh:
                anomalies.append({
                    "type":        "spike" if z > 0 else "trough",
                    "provider":    provider,
                    "month":       str(row["month"])[:7],
                    "pmpm":        round(row["pmpm"], 2),
                    "z_score":     round(z, 2),
                    "description": (
                        f"{provider} PMPM of ${row['pmpm']:.2f} in "
                        f"{row['month_label']} is {abs(z):.1f} std devs "
                        f"{'above' if z > 0 else 'below'} the annual mean "
                        f"(${mean:.2f})."
                    ),
                    "severity":    "high" if abs(z) > 3 else "medium",
                })

        # 2. Month-over-month drops > threshold
        for i in range(1, len(pmpm_vals)):
            prev, curr = pmpm_vals[i - 1], pmpm_vals[i]
            if prev > 0:
                change = (curr - prev) / prev
                if change < -mom_drop_thresh:
                    prev_label = grp.loc[i - 1, "month_label"]
                    curr_label = grp.loc[i, "month_label"]
                    anomalies.append({
                        "type":        "mom_drop",
                        "provider":    provider,
                        "month":       str(grp.loc[i, "month"])[:7],
                        "pmpm":        round(curr, 2),
                        "pct_change":  round(change * 100, 1),
                        "description": (
                            f"{provider} PMPM dropped {abs(change)*100:.1f}% "
                            f"from {prev_label} (${prev:.2f}) to "
                            f"{curr_label} (${curr:.2f})."
                        ),
                        "severity":    "high" if abs(change) > 0.4 else "medium",
                    })

    # 3. December seasonality check (cross-provider)
    dec = pmpm_df[pmpm_df["month"].astype(str).str[5:7] == "12"]
    non_dec = pmpm_df[pmpm_df["month"].astype(str).str[5:7] != "12"]
    if not dec.empty and not non_dec.empty:
        dec_avg = dec["pmpm"].mean()
        non_dec_avg = non_dec["pmpm"].mean()
        if dec_avg < non_dec_avg * 0.8:
            anomalies.append({
                "type":        "december_seasonality",
                "provider":    "ALL",
                "month":       "December",
                "pmpm":        round(dec_avg, 2),
                "description": (
                    f"December PMPM (${dec_avg:.2f}) is "
                    f"{(1 - dec_avg / non_dec_avg)*100:.1f}% below the "
                    f"Jan–Nov average (${non_dec_avg:.2f}). Likely reflects "
                    "IBNR lag or provider payment timing."
                ),
                "severity":    "high",
            })

    # 4. LOB membership changes > 10%
    membership_df = membership_by_lob(df)
    for lob, grp in membership_df.groupby("lob"):
        grp = grp.sort_values("month").reset_index(drop=True)
        for i in range(1, len(grp)):
            prev, curr = grp.loc[i - 1, "members"], grp.loc[i, "members"]
            if prev > 0:
                chg = (curr - prev) / prev
                if abs(chg) > 0.10:
                    anomalies.append({
                        "type":        "membership_shift",
                        "lob":         lob,
                        "month":       str(grp.loc[i, "month"])[:7],
                        "members":     int(curr),
                        "pct_change":  round(chg * 100, 1),
                        "description": (
                            f"{lob} membership changed {chg*100:+.1f}% "
                            f"({int(prev):,} → {int(curr):,}) in "
                            f"{grp.loc[i, 'month_label']}."
                        ),
                        "severity":    "medium",
                    })

    # De-duplicate and sort by severity
    seen = set()
    unique = []
    for a in anomalies:
        key = (a["type"], a.get("provider"), a.get("month"))
        if key not in seen:
            seen.add(key)
            unique.append(a)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(unique, key=lambda x: severity_order.get(x["severity"], 99))


# ── Helper ─────────────────────────────────────────────────────────────────────
def _weighted_avg(df: pd.DataFrame, val_col: str, wt_col: str) -> float:
    total_wt = df[wt_col].sum()
    if total_wt == 0:
        return np.nan
    return (df[val_col] * df[wt_col]).sum() / total_wt
