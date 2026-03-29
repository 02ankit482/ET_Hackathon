# cas_parser.py
# ─────────────────────────────────────────────────────────────
# CAS PDF parser using the casparser library.
# Parses CAMS/KFintech Consolidated Account Statements.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from typing import Optional


def parse_cas_pdf(file_path: str, password: str = "") -> dict:
    """
    Parse a CAMS/KFintech CAS PDF file.

    Args:
        file_path: Path to the CAS PDF file
        password: PDF password (usually PAN in lowercase)

    Returns:
        Parsed CAS data dict with investor_info, folios, schemes, transactions
    """
    try:
        import casparser
        data = casparser.read_cas_pdf(file_path, password)
        return data
    except ImportError:
        raise ImportError(
            "casparser not installed. Run: pip install 'casparser[fast]'"
        )
    except Exception as e:
        raise ValueError(f"Failed to parse CAS PDF: {str(e)}")


def extract_mf_summary(cas_data: dict) -> dict:
    """
    Aggregate CAS data into a profile-compatible summary.

    Returns:
        {
            "total_mf_value": float,
            "fund_count": int,
            "total_invested": float,
            "funds": [{scheme, amc, category, units, nav, value, transactions}, ...],
            "investor_info": {name, email, mobile},
        }
    """
    total_value = 0.0
    total_invested = 0.0
    funds = []

    investor_info = cas_data.get("investor_info", {})

    for folio in cas_data.get("folios", []):
        amc = folio.get("amc", "Unknown AMC")

        for scheme in folio.get("schemes", []):
            scheme_name = scheme.get("scheme", "Unknown Scheme")
            close_units = float(scheme.get("close", 0))

            # Valuation
            valuation = scheme.get("valuation", {})
            nav = float(valuation.get("nav", 0))
            value = float(valuation.get("value", 0))
            total_value += value

            # Infer category from scheme name (simplified heuristic)
            category = _infer_category(scheme_name)

            # Transaction summary
            transactions = scheme.get("transactions", [])
            invested = sum(
                float(t.get("amount", 0))
                for t in transactions
                if t.get("type", "").upper() in ("PURCHASE", "PURCHASE_SIP", "SWITCH_IN")
            )
            total_invested += max(0, invested)

            funds.append({
                "scheme": scheme_name,
                "amc": amc,
                "category": category,
                "folio": folio.get("folio", ""),
                "units": close_units,
                "nav": nav,
                "value": value,
                "invested": round(invested, 2),
                "gain_loss": round(value - invested, 2) if invested > 0 else 0,
                "transaction_count": len(transactions),
            })

    return {
        "total_mf_value": round(total_value, 2),
        "total_invested": round(total_invested, 2),
        "total_gain_loss": round(total_value - total_invested, 2),
        "fund_count": len(funds),
        "funds": funds,
        "investor_info": {
            "name": investor_info.get("name", ""),
            "email": investor_info.get("email", ""),
            "mobile": investor_info.get("mobile", ""),
        },
    }


def _infer_category(scheme_name: str) -> str:
    """Heuristic to infer SEBI MF category from scheme name."""
    name = scheme_name.lower()

    if "small cap" in name or "smallcap" in name:
        return "small_cap"
    if "mid cap" in name or "midcap" in name:
        if "large" in name:
            return "large_mid_cap"
        return "mid_cap"
    if "large cap" in name or "largecap" in name or "bluechip" in name:
        return "large_cap"
    if "flexi" in name or "flexicap" in name:
        return "flexi_cap"
    if "multi cap" in name or "multicap" in name:
        return "multi_cap"
    if "focused" in name:
        return "focused"
    if "elss" in name or "tax saver" in name or "taxsaver" in name:
        return "elss"
    if "index" in name or "nifty" in name or "sensex" in name:
        return "index_fund"
    if "liquid" in name:
        return "debt_liquid"
    if "gilt" in name or "government" in name:
        return "debt_gilt"
    if "short" in name and ("duration" in name or "term" in name):
        return "debt_short_duration"
    if "hybrid" in name or "balanced" in name:
        if "aggressive" in name or "equity" in name:
            return "hybrid_aggressive"
        return "hybrid_conservative"
    if "gold" in name:
        return "gold_fund"
    if "debt" in name or "bond" in name or "income" in name or "corporate" in name:
        return "debt_medium_duration"

    return "flexi_cap"  # Default assumption
