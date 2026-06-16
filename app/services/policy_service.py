from __future__ import annotations

from app.schemas.documents import DocumentAnalysisResult, ExtractedExpenseOut, FindingOut

VALID_LEVELS = {"low", "medium", "high"}
VALID_SEVERITIES = {"low", "medium", "high"}


def normalize_analysis_result(payload: dict) -> DocumentAnalysisResult:
    findings: list[FindingOut] = []
    for item in payload.get("findings", [])[:8]:
        severity = str(item.get("severity", "medium")).lower()
        findings.append(
            FindingOut(
                title=str(item.get("title", "Finding")).strip() or "Finding",
                description=str(item.get("description", "No description provided.")).strip(),
                severity=severity if severity in VALID_SEVERITIES else "medium",
            )
        )

    if findings:
        derived_level = "high" if any(f.severity == "high" for f in findings) else "medium"
    else:
        derived_level = "low"

    risk_level = str(payload.get("risk_level", derived_level)).lower()
    if risk_level not in VALID_LEVELS:
        risk_level = derived_level

    recommendations = [str(item).strip() for item in payload.get("recommendations", []) if str(item).strip()][:6]
    if not recommendations:
        recommendations = ["Review flagged items with a finance owner before posting the expense."]

    summary = str(payload.get("summary", "")).strip() or "Document processed with a minimal risk review."
    provider_status = str(payload.get("provider_status", "fallback")).strip() or "fallback"

    extracted_expense = payload.get("extracted_expense")
    return DocumentAnalysisResult(
        summary=summary,
        risk_level=risk_level,
        findings=findings,
        recommendations=recommendations,
        provider_status=provider_status,
        extracted_expense=ExtractedExpenseOut.model_validate(extracted_expense) if extracted_expense else None,
        raw_response=payload.get("raw_response"),
    )


def build_fallback_analysis(text: str, metadata: dict | None = None) -> DocumentAnalysisResult:
    metadata = metadata or {}
    lowered = text.lower()
    findings: list[dict] = []

    keyword_map = [
        ("auto renew", "Possible auto-renewal language detected.", "medium"),
        ("penalty", "Penalty language appears in the document.", "medium"),
        ("termination", "Termination terms appear in the document.", "medium"),
        ("confidential", "Confidentiality terms appear in the document.", "low"),
        ("indemn", "Indemnity language appears in the document.", "high"),
        ("personal data", "Personal data handling language appears in the document.", "high"),
        ("tax", "Tax-related amounts appear in the document.", "low"),
    ]

    for keyword, description, severity in keyword_map:
        if keyword in lowered:
            findings.append(
                {
                    "title": keyword.title(),
                    "description": description,
                    "severity": severity,
                }
            )

    if not findings and text.strip():
        findings.append(
            {
                "title": "Human review suggested",
                "description": "No obvious risk phrases were detected, but a quick finance review is still recommended.",
                "severity": "low",
            }
        )

    filename = metadata.get("filename", "document")
    summary = f"{filename} was reviewed using the built-in fallback analyzer because Azure AI services are not fully configured."

    return normalize_analysis_result(
        {
            "summary": summary,
            "risk_level": "high" if any(item["severity"] == "high" for item in findings) else "medium" if findings else "low",
            "findings": findings,
            "recommendations": [
                "Configure Azure Document Intelligence invoice extraction for receipts and invoices.",
                "Connect an Azure AI Foundry model deployment for richer expense policy summaries.",
            ],
            "provider_status": "fallback",
        }
    )
