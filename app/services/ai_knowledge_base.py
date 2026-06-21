from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeBaseEntry:
    topic: str
    summary: str
    keywords: tuple[str, ...]


KNOWLEDGE_BASE: tuple[KnowledgeBaseEntry, ...] = (
    KnowledgeBaseEntry(
        topic="platform_overview",
        summary=(
            "SpendPilot is a finance operations platform for budgets, approvals, variable expenses, recurring "
            "payments, and document intake. The assistant should stay grounded in the authenticated user's "
            "tenant data plus curated product knowledge."
        ),
        keywords=("spendpilot", "platform", "overview", "what is spendpilot", "assistant"),
    ),
    KnowledgeBaseEntry(
        topic="roles_and_visibility",
        summary=(
            "Supported business roles are org_owner, dept_head, and employee. org_owner can view organization-wide "
            "finance data, dept_head is limited to the assigned department scope, and employee access is limited "
            "to personal or explicitly permitted records."
        ),
        keywords=("role", "roles", "visibility", "org_owner", "dept_head", "employee", "permissions"),
    ),
    KnowledgeBaseEntry(
        topic="approval_flow",
        summary=(
            "Variable expenses typically start in pending_dept_head for employees. Department heads can approve, "
            "reject, or forward to the org owner. org_owner performs the final approval for items that exceed "
            "policy thresholds or were escalated."
        ),
        keywords=("approval", "approve", "workflow", "pending", "dept head", "org owner"),
    ),
    KnowledgeBaseEntry(
        topic="budgets",
        summary=(
            "Budgets are tracked monthly and can be company-wide or department-scoped. Company budgets define the "
            "top-level monthly envelope, and department budgets must fit within the company budget."
        ),
        keywords=("budget", "budgets", "company budget", "department budget", "monthly budget"),
    ),
    KnowledgeBaseEntry(
        topic="expense_types",
        summary=(
            "SpendPilot supports variable expenses and recurring expenses. Variable expenses are user-submitted "
            "operational spends, while recurring expenses model repeating vendor obligations with due dates and "
            "payment priorities."
        ),
        keywords=("expense", "expenses", "variable", "recurring", "payments"),
    ),
    KnowledgeBaseEntry(
        topic="departments_and_teams",
        summary=(
            "Department assignment affects approvals, budget visibility, and finance reporting. Department heads "
            "operate within their department scope and employees typically submit expenses inside their assigned "
            "department."
        ),
        keywords=("department", "team", "teams", "cost center"),
    ),
    KnowledgeBaseEntry(
        topic="documents_and_invoices",
        summary=(
            "Document upload supports OCR, invoice extraction, and risk analysis. The document pipeline may use "
            "Azure Document Intelligence and Azure AI Foundry, while the chat assistant should only read document "
            "metadata, scan summaries, and small safe excerpts when needed."
        ),
        keywords=("document", "documents", "invoice", "ocr", "scan", "upload"),
    ),
    KnowledgeBaseEntry(
        topic="assistant_boundaries",
        summary=(
            "The assistant should not invent finance numbers, expose cross-tenant data, generate SQL, dump full "
            "tables, or return entire document bodies. It should prefer bounded tool calls, safe defaults, and "
            "clear limitation notes when data is unavailable."
        ),
        keywords=("safety", "boundary", "boundaries", "limit", "limits", "sql", "tenant"),
    ),
    KnowledgeBaseEntry(
        topic="assistant_capabilities",
        summary=(
            "The assistant can summarize dashboards, budgets, department spend, pending approvals, urgent payments, "
            "recurring expenses, expense lookups, and relevant document metadata. For conceptual product questions, "
            "it may answer directly from the curated knowledge base."
        ),
        keywords=("capabilities", "can you", "what can", "help", "finance dashboard"),
    ),
)


def render_knowledge_base() -> str:
    return "\n".join(f"- {entry.topic}: {entry.summary}" for entry in KNOWLEDGE_BASE)


def find_relevant_entries(query: str, limit: int = 3) -> list[KnowledgeBaseEntry]:
    terms = {term for term in re.findall(r"[a-z0-9_]+", query.lower()) if term}
    ranked: list[tuple[int, KnowledgeBaseEntry]] = []
    for entry in KNOWLEDGE_BASE:
        score = sum(1 for keyword in entry.keywords if keyword.lower() in query.lower())
        score += sum(1 for term in terms if term in entry.summary.lower())
        if score:
            ranked.append((score, entry))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in ranked[:limit]]


def explain_concept(query: str) -> dict:
    matches = find_relevant_entries(query, limit=3)
    if not matches:
        matches = [entry for entry in KNOWLEDGE_BASE if entry.topic in {"platform_overview", "assistant_boundaries"}]
    return {
        "query": query,
        "topics": [entry.topic for entry in matches],
        "summary": " ".join(entry.summary for entry in matches),
    }
