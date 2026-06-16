from decimal import Decimal

from app.api.routes import documents as document_routes
from app.schemas.documents import DocumentAnalysisResult, ExtractedExpenseOut, FindingOut
from app.services.ai_foundry_service import DocumentExtraction
from tests.conftest import get_client


def _auth_header(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/dev-login",
        json={"email": "reviewer@example.com", "display_name": "Reviewer", "role": "employee"},
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_scan_extract_and_fetch_document() -> None:
    client = get_client()
    headers = _auth_header(client)

    upload = client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("contract.txt", b"This contract contains indemnity and termination clauses.", "text/plain")},
    )
    assert upload.status_code == 200
    document_id = upload.json()["data"]["document"]["id"]

    scan = client.post(f"/api/documents/{document_id}/scan", headers=headers)
    assert scan.status_code == 200
    assert scan.json()["data"]["risk_level"] in {"medium", "high"}

    extracted = client.post(f"/api/documents/{document_id}/extract-expense", headers=headers)
    assert extracted.status_code == 200
    assert extracted.json()["data"]["provider_status"] in {"fallback", "azure-ai-foundry", "azure-document-intelligence"}

    latest = client.get(f"/api/documents/{document_id}/scan-result", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["data"]["document_id"] == document_id


def test_decimal_expense_payloads_do_not_break_document_scan_or_extract(monkeypatch) -> None:
    client = get_client()
    headers = _auth_header(client)

    upload = client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("invoice.txt", b"Invoice total 123.45", "text/plain")},
    )
    assert upload.status_code == 200
    document_id = upload.json()["data"]["document"]["id"]

    extracted = ExtractedExpenseOut(
        vendor_name="Acme Travel",
        invoice_number="INV-1001",
        currency="INR",
        total_amount=Decimal("123.45"),
        provider_status="azure-document-intelligence",
    )

    monkeypatch.setattr(
        document_routes.document_service.ai_service,
        "extract_text_from_document",
        lambda **kwargs: DocumentExtraction(
            text="Invoice INV-1001 total 123.45",
            extractor="azure-document-intelligence",
            invoice_fields=extracted,
        ),
    )
    monkeypatch.setattr(
        document_routes.document_service.ai_service,
        "analyze_document",
        lambda text, metadata, extracted_expense=None: DocumentAnalysisResult(
            summary="Invoice looks valid.",
            risk_level="low",
            findings=[FindingOut(title="Matched total", description="Amounts parsed successfully.", severity="info")],
            recommendations=["Approve after policy review."],
            provider_status="azure-ai-foundry",
            extracted_expense=extracted_expense,
            raw_response={"provider": "pytest"},
        ),
    )
    monkeypatch.setattr(
        document_routes.document_service.ai_service,
        "extract_expense_fields",
        lambda **kwargs: extracted,
    )

    scan = client.post(f"/api/documents/{document_id}/scan", headers=headers)
    assert scan.status_code == 200
    assert scan.json()["data"]["extracted_expense"]["total_amount"] == "123.45"

    extracted_response = client.post(f"/api/documents/{document_id}/extract-expense", headers=headers)
    assert extracted_response.status_code == 200
    assert extracted_response.json()["data"]["total_amount"] == "123.45"

    document = client.get(f"/api/documents/{document_id}", headers=headers)
    assert document.status_code == 200
    assert document.json()["data"]["metadata_json"]["extracted_expense"]["total_amount"] == "123.45"
