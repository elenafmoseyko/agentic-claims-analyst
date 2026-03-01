"""
src/data_loader.py
==================
Flexible data loader for claims + enrollment files.

Supports two schemas:
  A) LONG format  — one row per (month, lob, provider)
     columns: month | lob | provider | members | paid_claims
  B) WIDE format  — the Company ABC exhibit layout
     parsed from multi-level headers (HMO/POS / PPO / Medicaid / Medicare)

Auto-detects which format is present and normalises to LONG format.
"""

import re
from pathlib import Path
import pandas as pd
import numpy as np


LOB_ALIASES = {
    "hmo": "HMO/POS", "hmo/pos": "HMO/POS", "hmopos": "HMO/POS",
    "ppo": "PPO",
    "medicaid": "Medicaid", "mcd": "Medicaid",
    "medicare": "Medicare",  "mcr": "Medicare",
}

PROVIDER_ALIASES = {
    "a": "Provider A", "provider a": "Provider A", "prov a": "Provider A",
    "b": "Provider B", "provider b": "Provider B", "prov b": "Provider B",
    "c": "Provider C", "provider c": "Provider C", "prov c": "Provider C",
}


def load_claims_data(file_path: str) -> pd.DataFrame:
    """
    Main entry point.  Returns a normalised LONG-format DataFrame:
        month (datetime) | lob | provider | members | pmpm | paid_claims
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if path.suffix.lower() in (".xlsx", ".xls"):
        return _load_excel(path)
    elif path.suffix.lower() == ".csv":
        return _load_csv(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")


# ── Excel loader ───────────────────────────────────────────────────────────────
def _load_excel(path: Path) -> pd.DataFrame:
    xl = pd.ExcelFile(path)
    sheet_name = _pick_sheet(xl.sheet_names)

    # Try wide (exhibit) format first
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if _is_wide_exhibit(raw):
        return _parse_wide_exhibit(raw)

    # Fall back to long format
    df = pd.read_excel(path, sheet_name=sheet_name)
    return _normalise_long(df)


def _pick_sheet(sheets: list[str]) -> str:
    for s in sheets:
        if "detail" in s.lower():
            return s
    return sheets[0]


def _is_wide_exhibit(raw: pd.DataFrame) -> bool:
    """Detect the multi-level exhibit header pattern."""
    header_text = " ".join(str(v) for v in raw.iloc[:8].values.flatten() if pd.notna(v)).lower()
    return "hmo" in header_text and "ppo" in header_text and "medicaid" in header_text


def _parse_wide_exhibit(raw: pd.DataFrame) -> pd.DataFrame:
    """Parse the Company ABC multi-LOB wide exhibit layout."""
    # Column offsets discovered from the actual file:
    # month=col0 | HMO/POS: 2,3,4,5 | PPO: 7,8,9,10 | Medicaid: 12,13,14,15 | Medicare: 17,18,19,20
    OFFSETS = {
        "HMO/POS":  2,
        "PPO":      7,
        "Medicaid": 12,
        "Medicare": 17,
    }
    PROVIDERS = ["Provider A", "Provider B", "Provider C"]

    records = []
    for _, row in raw.iloc[8:20].iterrows():
        raw_month = row.iloc[0]
        if pd.isna(raw_month):
            continue
        month = pd.to_datetime(raw_month)
        for lob, col in OFFSETS.items():
            members = _to_float(row.iloc[col])
            for i, provider in enumerate(PROVIDERS):
                pmpm = _to_float(row.iloc[col + 1 + i])
                paid = members * pmpm if members and pmpm else None
                records.append({
                    "month":       month,
                    "lob":         lob,
                    "provider":    provider,
                    "members":     members,
                    "pmpm":        pmpm,
                    "paid_claims": paid,
                })

    return pd.DataFrame(records)


# ── CSV loader ─────────────────────────────────────────────────────────────────
def _load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return _normalise_long(df)


# ── Long-format normaliser ─────────────────────────────────────────────────────
def _normalise_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise a long-format DataFrame to standard schema.
    Accepts flexible column names (month/date/period, lob/line_of_business, etc.)
    """
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Map common synonyms
    renames = {}
    for col in df.columns:
        if col in ("date", "period", "service_month", "incurred_month"):
            renames[col] = "month"
        elif col in ("line_of_business", "line", "coverage"):
            renames[col] = "lob"
        elif col in ("prov", "prov_name", "provider_name"):
            renames[col] = "provider"
        elif col in ("enrollment", "member_months", "covered_lives"):
            renames[col] = "members"
        elif col in ("claims", "total_claims", "incurred_claims"):
            renames[col] = "paid_claims"
    df = df.rename(columns=renames)

    # Ensure month is datetime
    if "month" in df.columns:
        df["month"] = pd.to_datetime(df["month"], errors="coerce")

    # Standardise LOB and provider names
    if "lob" in df.columns:
        df["lob"] = df["lob"].apply(_canonicalise_lob)
    if "provider" in df.columns:
        df["provider"] = df["provider"].apply(_canonicalise_provider)

    # Calculate pmpm if not present
    if "pmpm" not in df.columns and "paid_claims" in df.columns and "members" in df.columns:
        df["pmpm"] = np.where(
            df["members"] > 0,
            df["paid_claims"] / df["members"],
            np.nan,
        )

    return df.dropna(subset=["month"])


# ── Helpers ────────────────────────────────────────────────────────────────────
def _to_float(val) -> float | None:
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _canonicalise_lob(val: str) -> str:
    key = str(val).strip().lower()
    return LOB_ALIASES.get(key, val)


def _canonicalise_provider(val: str) -> str:
    key = str(val).strip().lower()
    return PROVIDER_ALIASES.get(key, val)
