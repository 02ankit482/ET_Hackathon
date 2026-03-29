# Tools package for CrewAI agents

from .financial_calculator import (
    MonthlySurplusTool,
    DebtToIncomeTool,
    EmergencyFundTool,
    NetWorthTool,
    AssetAllocationTool,
    RetirementCorpusTool,
    SIPRequiredTool,
    InsuranceGapTool,
    FinancialCalculatorTool,  # Legacy combined tool
)
from .tax_calculator import TaxCalculatorTool
from .rag_tool import FinanceRAGTool
from .portfolio_overlap import PortfolioOverlapTool
from .profile_tool import ProfileReadTool, ProfileUpdateTool

__all__ = [
    # Individual financial tools (preferred)
    "MonthlySurplusTool",
    "DebtToIncomeTool",
    "EmergencyFundTool",
    "NetWorthTool",
    "AssetAllocationTool",
    "RetirementCorpusTool",
    "SIPRequiredTool",
    "InsuranceGapTool",
    # Other tools
    "TaxCalculatorTool",
    "FinanceRAGTool",
    "PortfolioOverlapTool",
    "ProfileReadTool",
    "ProfileUpdateTool",
    # Legacy
    "FinancialCalculatorTool",
]
