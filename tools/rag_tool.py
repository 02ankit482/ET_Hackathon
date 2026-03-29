# tools/rag_tool.py
# ─────────────────────────────────────────────────────────────
# Wraps the existing HybridRetriever as a CrewAI tool.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from typing import Type
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RAGSearchInput(BaseModel):
    query: str = Field(description="The search query about Indian finance, investing, tax, insurance, etc.")


class FinanceRAGTool(BaseTool):
    name: str = "finance_knowledge_search"
    description: str = """Search the financial knowledge base for information about Indian 
personal finance topics including: mutual funds, stocks, bonds, insurance, tax planning, 
retirement, SIP strategies, asset allocation, SEBI regulations, ELSS, PPF, NPS, EPF, 
and investment strategies. Returns relevant excerpts from Zerodha Varsity and other 
financial education materials.

Use this when you need factual information about financial concepts, rules, or strategies.
Do NOT use this for numerical calculations — use the financial_calculator tool instead."""
    args_schema: Type[BaseModel] = RAGSearchInput

    _retriever: object = None

    def _get_retriever(self):
        """Lazy-load the retriever to avoid import issues."""
        if self._retriever is None:
            from retriever import HybridRetriever
            self._retriever = HybridRetriever()
        return self._retriever

    def _run(self, query: str) -> str:
        try:
            retriever = self._get_retriever()
            hits = retriever.retrieve(query, top_n=5)

            if not hits:
                return "No relevant information found in the knowledge base for this query."

            # Format context from hits
            context_parts = []
            for i, hit in enumerate(hits, 1):
                doc = hit.get("document", hit.get("text", ""))
                metadata = hit.get("metadata", {})
                source = metadata.get("source", "Unknown")
                topic = metadata.get("topic", "general")

                context_parts.append(
                    f"[Source {i}: {source} | Topic: {topic}]\n{doc}\n"
                )

            return "\n---\n".join(context_parts)

        except Exception as e:
            return f"Knowledge search error: {str(e)}. Proceeding without RAG context."
