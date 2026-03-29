# tools/portfolio_overlap.py
# ─────────────────────────────────────────────────────────────
# Detects portfolio overlap when user has CAS data with
# multiple MF schemes holding the same underlying stocks.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from typing import Type
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class OverlapInput(BaseModel):
    """Input schema for portfolio overlap detection."""
    funds_json: str = Field(
        description=(
            "JSON string containing a list of fund objects. Each fund should have: "
            "'scheme' (name of the fund), 'category' (SEBI category like large_cap, "
            "mid_cap, flexi_cap, etc.), and optionally 'value' (current value in INR). "
            "Example: '[{\"scheme\": \"HDFC Top 100\", \"category\": \"large_cap\", \"value\": 500000}]'"
        )
    )


# Common top holdings by SEBI category (simplified for overlap estimation)
# In production, this would query live data from AMFI/Groww API
CATEGORY_TOP_HOLDINGS = {
    "large_cap": [
        "Reliance Industries", "HDFC Bank", "ICICI Bank", "Infosys",
        "TCS", "Bharti Airtel", "ITC", "State Bank of India",
        "Kotak Mahindra Bank", "L&T",
    ],
    "flexi_cap": [
        "HDFC Bank", "ICICI Bank", "Reliance Industries", "Infosys",
        "TCS", "Bharti Airtel", "Axis Bank", "Sun Pharma",
        "State Bank of India", "L&T",
    ],
    "multi_cap": [
        "HDFC Bank", "ICICI Bank", "Reliance Industries", "Infosys",
        "TCS", "Bajaj Finance", "Axis Bank", "Kotak Mahindra Bank",
        "L&T", "HCL Technologies",
    ],
    "large_mid_cap": [
        "HDFC Bank", "ICICI Bank", "Reliance Industries", "Infosys",
        "Bajaj Finance", "Persistent Systems", "Trent", "Coforge",
        "APL Apollo Tubes", "PI Industries",
    ],
    "mid_cap": [
        "Persistent Systems", "Coforge", "APL Apollo Tubes",
        "PI Industries", "Trent", "Mphasis",
        "Crompton Greaves", "Voltas", "Indian Hotels", "Federal Bank",
    ],
    "small_cap": [
        "Kaynes Technology", "KPIT Technologies", "CMS Info Systems",
        "Ratnamani Metals", "KPI Green Energy", "Mastek",
        "Data Patterns", "CDSL", "Carysil", "Route Mobile",
    ],
    "focused": [
        "HDFC Bank", "ICICI Bank", "Reliance Industries", "Infosys",
        "TCS", "Bajaj Finance", "Titan", "Asian Paints",
        "Kotak Mahindra Bank", "Nestle India",
    ],
    "elss": [
        "HDFC Bank", "ICICI Bank", "Reliance Industries", "Infosys",
        "TCS", "Axis Bank", "State Bank of India", "Bharti Airtel",
        "L&T", "Kotak Mahindra Bank",
    ],
}


class PortfolioOverlapTool(BaseTool):
    name: str = "portfolio_overlap_detector"
    description: str = """Analyzes a user's mutual fund portfolio for overlap — 
multiple funds holding the same underlying stocks. This is important because:
- High overlap means you're not truly diversified
- You're paying multiple expense ratios for essentially the same exposure

Provide a list of funds with their SEBI categories. Returns overlap score (0-100%),
overlapping stocks, and consolidation advice.

Categories supported: large_cap, mid_cap, small_cap, large_mid_cap, multi_cap, 
flexi_cap, focused, elss"""
    args_schema: Type[BaseModel] = OverlapInput

    def _run(self, funds_json: str) -> str:
        try:
            # Parse the JSON string input
            funds = json.loads(funds_json) if isinstance(funds_json, str) else funds_json

            if len(funds) < 2:
                return json.dumps({
                    "overlap_score": 0,
                    "message": "Need at least 2 funds to check overlap",
                })

            # Get holdings for each fund's category
            fund_holdings = {}
            for i, fund in enumerate(funds):
                category = fund.get("category", "").lower().replace(" ", "_")
                scheme = fund.get("scheme", f"Fund {i+1}")
                holdings = CATEGORY_TOP_HOLDINGS.get(category, [])
                fund_holdings[scheme] = set(holdings)

            # Compute pairwise overlaps
            schemes = list(fund_holdings.keys())
            overlaps = []
            all_overlapping_stocks = set()

            for i in range(len(schemes)):
                for j in range(i + 1, len(schemes)):
                    s1, s2 = schemes[i], schemes[j]
                    h1, h2 = fund_holdings[s1], fund_holdings[s2]

                    if not h1 or not h2:
                        continue

                    common = h1 & h2
                    union = h1 | h2
                    overlap_pct = (len(common) / len(union) * 100) if union else 0

                    if overlap_pct > 20:  # Only flag significant overlaps
                        overlaps.append({
                            "fund_1": s1,
                            "fund_2": s2,
                            "overlap_pct": round(overlap_pct, 1),
                            "common_stocks": sorted(list(common)),
                        })
                        all_overlapping_stocks |= common

            # Overall overlap score (average of pairwise overlaps)
            if overlaps:
                avg_overlap = sum(o["overlap_pct"] for o in overlaps) / len(overlaps)
            else:
                avg_overlap = 0

            # Sort by overlap severity
            overlaps.sort(key=lambda x: x["overlap_pct"], reverse=True)

            # Generate consolidation advice
            total_funds = len(funds)
            high_overlap_categories = set()
            for o in overlaps:
                if o["overlap_pct"] > 40:
                    for f in funds:
                        if f.get("scheme") in (o["fund_1"], o["fund_2"]):
                            high_overlap_categories.add(
                                f.get("category", "unknown")
                            )

            if avg_overlap > 50:
                advice = (
                    f"HIGH OVERLAP ({avg_overlap:.0f}%): Your {total_funds} schemes have "
                    f"significant overlap. Consider consolidating to {max(2, total_funds // 2)} "
                    f"schemes across distinct SEBI categories to improve diversification. "
                    f"Categories with most overlap: {', '.join(high_overlap_categories)}."
                )
            elif avg_overlap > 25:
                advice = (
                    f"MODERATE OVERLAP ({avg_overlap:.0f}%): Some overlap detected between "
                    f"schemes. Review whether you need {total_funds} separate schemes or "
                    f"could consolidate similar categories."
                )
            else:
                advice = (
                    f"LOW OVERLAP ({avg_overlap:.0f}%): Your portfolio is well-diversified "
                    f"across different categories."
                )

            return json.dumps({
                "overlap_score": round(avg_overlap, 1),
                "total_funds_analyzed": total_funds,
                "overlapping_stocks": sorted(list(all_overlapping_stocks)),
                "pairwise_overlaps": overlaps[:10],  # Top 10
                "consolidation_advice": advice,
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)})
