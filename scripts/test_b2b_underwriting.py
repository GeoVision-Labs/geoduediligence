"""
Comprehensive Test Suite for B2B Institutional Underwriting API & Webhook Suite
Tests:
1. API Key & Bearer Token Authentication (401 Missing, 403 Invalid, 200 Authorized)
2. Sliding Window Rate Limiting & Response Telemetry Headers
3. Automated Credit Decisioning (APPROVAL_RECOMMENDED, CONDITIONAL_SANCTION, REJECTION_MANDATED)
4. Collateral Valuation & Pre-Disbursement Statutory Covenants
5. High-Volume Batch Portfolio Underwriting (JSON)
6. Multipart CSV Portfolio Upload & CSV Audit Report Export
7. HMAC-SHA256 Webhook Signature Generation & Verification
"""

import sys
import os
import io
import csv
import json
import unittest
import httpx
import asyncio

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.main import app
from backend.app.core.security import (
    DEFAULT_ORGANIZATIONS,
    generate_webhook_signature,
    rate_limiter,
    B2BOrganization
)

class TestB2BUnderwritingSuite(unittest.TestCase):

    SBI_KEY = "gdd_live_sbi_enterprise_991823"
    HDFC_KEY = "gdd_live_hdfc_capital_441209"
    CREDAI_KEY = "gdd_test_credai_developer_123456"

    @classmethod
    def setUpClass(cls):
        # Configure ASGI client for in-process async testing
        cls.transport = httpx.ASGITransport(app=app)

    def _run_async(self, coro):
        return asyncio.run(coro)

    # ----------------------------------------------------
    # 1. Authentication & Security Tests
    # ----------------------------------------------------
    def test_01_auth_missing_key(self):
        """Requests without API key must return 401 Unauthorized."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                res = await client.get("/api/v1/b2b/me")
                self.assertEqual(res.status_code, 401)
                self.assertIn("Missing institutional API Key", res.json()["detail"])
        self._run_async(run())

    def test_02_auth_invalid_key(self):
        """Requests with bogus API key must return 403 Forbidden."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                res = await client.get("/api/v1/b2b/me", headers={"X-API-Key": "gdd_live_fake_key_0000"})
                self.assertEqual(res.status_code, 403)
                self.assertIn("Invalid or deactivated API Key", res.json()["detail"])
        self._run_async(run())

    def test_03_auth_valid_header_and_bearer(self):
        """Valid keys via X-API-Key and Bearer Authorization header."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                # 1. Via X-API-Key header (SBI Enterprise)
                res1 = await client.get("/api/v1/b2b/me", headers={"X-API-Key": self.SBI_KEY})
                self.assertEqual(res1.status_code, 200)
                data1 = res1.json()
                self.assertEqual(data1["org_name"], "State Bank of India — Visakhapatnam Commercial Hub")
                self.assertEqual(data1["tier"], "ENTERPRISE")
                self.assertEqual(data1["daily_quota"], 10000)

                # 2. Via Bearer token (HDFC Capital)
                res2 = await client.get("/api/v1/b2b/me", headers={"Authorization": f"Bearer {self.HDFC_KEY}"})
                self.assertEqual(res2.status_code, 200)
                data2 = res2.json()
                self.assertEqual(data2["org_name"], "HDFC Capital & Real Estate Project Finance")
                self.assertEqual(data2["org_type"], "HFC")
        self._run_async(run())

    # ----------------------------------------------------
    # 2. Rate Limiting Telemetry Headers
    # ----------------------------------------------------
    def test_04_rate_limit_headers(self):
        """Every authenticated B2B request must include standard rate limit headers."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                res = await client.get("/api/v1/b2b/me", headers={"X-API-Key": self.SBI_KEY})
                self.assertEqual(res.status_code, 200)
                self.assertIn("x-ratelimit-limit", res.headers)
                self.assertIn("x-ratelimit-remaining", res.headers)
                self.assertIn("x-ratelimit-daily-quota", res.headers)
                self.assertIn("x-ratelimit-daily-remaining", res.headers)
        self._run_async(run())

    # ----------------------------------------------------
    # 3. Credit Underwriting Decision Tests
    # ----------------------------------------------------
    def test_05_underwrite_approval_recommended(self):
        """Clean private Patta with approved LP must receive APPROVAL_RECOMMENDED at 75% LTV."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                payload = {
                    "case_ref": "SBI-VSP-2024-001",
                    "applicant_name": "Sri K. Satyanarayana Raju",
                    "loan_amount_inr": 25000000.0,
                    "district": "Visakhapatnam",
                    "mandal": "Anandapuram",
                    "village_name": "Tarluvada",
                    "survey_number": "72",
                    "proposed_end_use": "Residential Plotted Layout"
                }
                res = await client.post("/api/v1/b2b/underwrite", json=payload, headers={"X-API-Key": self.SBI_KEY})
                self.assertEqual(res.status_code, 200)
                data = res.json()
                
                self.assertEqual(data["decision"], "APPROVAL_RECOMMENDED")
                self.assertIn(data["risk_grade"], ["A+", "A"])
                self.assertEqual(data["collateral_valuation"]["max_recommended_ltv_pct"], 75.0)
                self.assertGreater(data["collateral_valuation"]["max_sanctionable_loan_amount_inr"], 0.0)
                self.assertTrue(len(data["pre_disbursement_covenants"]) > 0)
                self.assertEqual(len(data["report_hash"]), 64)
                print(f"\n[Test 5] Case 1 Approved: Max Sanction INR {data['collateral_valuation']['max_sanctionable_loan_amount_inr']:,.0f}")
        self._run_async(run())

    def test_06_underwrite_rejection_mandated_22a(self):
        """Section 22A Prohibited assigned land must receive REJECTION_MANDATED with 0% LTV."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                payload = {
                    "case_ref": "HDFC-VSP-2024-002",
                    "applicant_name": "Prospective Buyer M/s Apex Developers",
                    "loan_amount_inr": 50000000.0,
                    "district": "Visakhapatnam",
                    "mandal": "Anandapuram",
                    "village_name": "Tarluvada",
                    "survey_number": "81",
                    "proposed_end_use": "Commercial IT Complex"
                }
                res = await client.post("/api/v1/b2b/underwrite", json=payload, headers={"X-API-Key": self.HDFC_KEY})
                self.assertEqual(res.status_code, 200)
                data = res.json()
                
                self.assertEqual(data["decision"], "REJECTION_MANDATED")
                self.assertEqual(data["collateral_valuation"]["max_recommended_ltv_pct"], 0.0)
                self.assertEqual(data["collateral_valuation"]["max_sanctionable_loan_amount_inr"], 0.0)
                self.assertIn("Section 22A", data["decision_summary"])
                print(f"\n[Test 6] Case 2 Rejected: {data['decision_summary'][:90]}...")
        self._run_async(run())

    def test_07_underwrite_rejection_unauthorized_layout(self):
        """Unauthorized layout notified for demolition must receive REJECTION_MANDATED."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                payload = {
                    "case_ref": "CREDAI-AUDIT-003",
                    "applicant_name": "Unregistered Layout Promoter",
                    "loan_amount_inr": 15000000.0,
                    "district": "Visakhapatnam",
                    "mandal": "Anandapuram",
                    "village_name": "Tarluvada",
                    "survey_number": "64"
                }
                res = await client.post("/api/v1/b2b/underwrite", json=payload, headers={"X-API-Key": self.CREDAI_KEY})
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["decision"], "REJECTION_MANDATED")
                self.assertIn("Unauthorized Layout", data["decision_summary"])
        self._run_async(run())

    # ----------------------------------------------------
    # 4. Batch JSON Portfolio Underwriting
    # ----------------------------------------------------
    def test_08_batch_json_underwriting(self):
        """Batch underwriting processes multiple parcels and returns portfolio aggregated metrics."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                batch_payload = {
                    "batch_title": "SBI Anandapuram Housing Portfolio Audit",
                    "items": [
                        {
                            "case_ref": "SBI-B1-72",
                            "applicant_name": "Sri K. Satyanarayana Raju",
                            "loan_amount_inr": 20000000.0,
                            "district": "Visakhapatnam",
                            "mandal": "Anandapuram",
                            "village_name": "Tarluvada",
                            "survey_number": "72"
                        },
                        {
                            "case_ref": "SBI-B1-81",
                            "applicant_name": "Sri M. Appa Rao (D-Form)",
                            "loan_amount_inr": 15000000.0,
                            "district": "Visakhapatnam",
                            "mandal": "Anandapuram",
                            "village_name": "Tarluvada",
                            "survey_number": "81"
                        },
                        {
                            "case_ref": "SBI-B1-64",
                            "applicant_name": "Unapproved Layout Developer",
                            "loan_amount_inr": 10000000.0,
                            "district": "Visakhapatnam",
                            "mandal": "Anandapuram",
                            "village_name": "Tarluvada",
                            "survey_number": "64"
                        }
                    ]
                }
                res = await client.post(
                    "/api/v1/b2b/batch-underwrite", json=batch_payload, headers={"X-API-Key": self.SBI_KEY}
                )
                self.assertEqual(res.status_code, 200)
                batch = res.json()
                self.assertEqual(batch["status"], "COMPLETED")
                self.assertEqual(batch["total_records"], 3)
                self.assertEqual(batch["approved_count"], 1)
                self.assertEqual(batch["rejected_count"], 2)
                self.assertGreater(batch["total_recommended_sanction_inr"], 0.0)
                print(f"\n[Test 8] Batch Completed: 1 Approved, 2 Rejected | Recommended: INR {batch['total_recommended_sanction_inr']:,.0f}")
        self._run_async(run())

    # ----------------------------------------------------
    # 5. Multipart CSV Upload & CSV Export
    # ----------------------------------------------------
    def test_09_batch_csv_upload_and_export(self):
        """Uploads portfolio CSV file, audits records, and downloads audited result CSV."""
        async def run():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://test") as client:
                # 1. Create in-memory CSV
                csv_buffer = io.StringIO()
                writer = csv.writer(csv_buffer)
                writer.writerow(["case_ref", "applicant_name", "loan_amount_inr", "district", "mandal", "village_name", "survey_number", "extent_acres"])
                writer.writerow(["CSV-001", "Sri B. Narasimha", "12000000", "Visakhapatnam", "Anandapuram", "Tarluvada", "72", "2.5"])
                writer.writerow(["CSV-002", "Sri G. Govinda", "8000000", "Visakhapatnam", "Anandapuram", "Tarluvada", "81", "3.0"])
                csv_bytes = csv_buffer.getvalue().encode("utf-8")

                # 2. Upload CSV
                files = {"file": ("portfolio_audit.csv", csv_bytes, "text/csv")}
                data = {"batch_title": "CSV Ingestion Test"}
                res = await client.post(
                    "/api/v1/b2b/batch-upload-csv",
                    files=files,
                    data=data,
                    headers={"X-API-Key": self.SBI_KEY}
                )
                self.assertEqual(res.status_code, 200)
                job = res.json()
                batch_id = job["batch_id"]
                self.assertEqual(job["total_records"], 2)
                self.assertEqual(job["status"], "COMPLETED")

                # 3. Download Audited CSV Export
                export_res = await client.get(
                    f"/api/v1/b2b/batch-export/{batch_id}", headers={"X-API-Key": self.SBI_KEY}
                )
                self.assertEqual(export_res.status_code, 200)
                self.assertIn("text/csv", export_res.headers["content-type"])
                exported_text = export_res.text
                self.assertIn("CSV-001", exported_text)
                self.assertIn("CSV-002", exported_text)
                self.assertIn("APPROVAL_RECOMMENDED", exported_text)
                self.assertIn("REJECTION_MANDATED", exported_text)
                self.assertIn("SHA-256 Digital Fingerprint", exported_text)
                print(f"\n[Test 9] CSV Export Downloaded ({len(exported_text)} bytes) with verified verdicts.")
        self._run_async(run())

    # ----------------------------------------------------
    # 6. Webhook HMAC-SHA256 Signature Test
    # ----------------------------------------------------
    def test_10_webhook_hmac_signature(self):
        """Validates HMAC-SHA256 cryptographic signature computation for webhooks."""
        secret = "whsec_sbi_live_7718923a10b441f9"
        payload_bytes = b'{"event":"underwrite.completed","data":{"case_ref":"SBI-001"}}'
        sig = generate_webhook_signature(payload_bytes, secret)
        self.assertTrue(sig.startswith("sha256="))
        self.assertEqual(len(sig), 7 + 64)  # 'sha256=' + 64 hex characters
        print(f"\n[Test 10] HMAC-SHA256 Webhook Signature: {sig[:24]}...")

if __name__ == "__main__":
    unittest.main()
