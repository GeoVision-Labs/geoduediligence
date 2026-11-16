import io
import csv
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from ..models.b2b_schemas import (
    BatchUnderwriteRequest,
    BatchUnderwriteItem,
    BatchJobStatus,
    B2BUnderwritingRequest,
    B2BUnderwritingResponse,
    UnderwritingDecision
)
from ..core.security import B2BOrganization
from .underwriting_service import UnderwritingService

logger = logging.getLogger(__name__)

# In-memory registry for batch jobs
BATCH_REGISTRY: Dict[str, BatchJobStatus] = {}

class BatchProcessor:
    """
    High-volume portfolio audit and batch underwriting engine.
    Processes CSV portfolios and JSON arrays asynchronously with status tracking and CSV exports.
    """

    def __init__(self):
        self.underwriting_service = UnderwritingService()

    @staticmethod
    def parse_csv_to_items(csv_content: str) -> List[BatchUnderwriteItem]:
        """
        Parses uploaded CSV text into structured BatchUnderwriteItem models.
        Supports flexible column headers commonly used by banks and CREDAI developers.
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        items: List[BatchUnderwriteItem] = []

        for idx, row in enumerate(reader, start=1):
            # Normalize column keys
            normalized = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            
            case_ref = (
                normalized.get("case_ref")
                or normalized.get("application_id")
                or normalized.get("loan_no")
                or f"CASE-{idx:04d}"
            )
            applicant = (
                normalized.get("applicant_name")
                or normalized.get("borrower")
                or normalized.get("customer_name")
                or "Applicant"
            )
            
            raw_amt = (
                normalized.get("loan_amount_inr")
                or normalized.get("loan_amount")
                or normalized.get("amount")
                or "10000000"
            )
            try:
                loan_amount = float(raw_amt.replace(",", "").replace("₹", ""))
            except ValueError:
                loan_amount = 10000000.0

            district = normalized.get("district") or "Visakhapatnam"
            mandal = normalized.get("mandal") or "Anandapuram"
            village = normalized.get("village_name") or normalized.get("village") or "Tarluvada"
            survey = normalized.get("survey_number") or normalized.get("survey_no") or normalized.get("sy_no") or "72"
            
            extent = None
            if "extent_acres" in normalized or "extent" in normalized:
                try:
                    extent = float((normalized.get("extent_acres") or normalized.get("extent")).replace(",", ""))
                except Exception:
                    extent = None

            end_use = normalized.get("proposed_end_use") or normalized.get("end_use") or "Residential Plotted Layout"

            items.append(
                BatchUnderwriteItem(
                    case_ref=case_ref,
                    applicant_name=applicant,
                    loan_amount_inr=loan_amount,
                    district=district,
                    mandal=mandal,
                    village_name=village,
                    survey_number=survey,
                    extent_acres=extent,
                    proposed_end_use=end_use
                )
            )

        return items

    def create_batch_job(
        self,
        title: str,
        org: B2BOrganization,
        items: List[BatchUnderwriteItem],
        webhook_url: Optional[str] = None
    ) -> BatchJobStatus:
        """Initializes a new batch job in PENDING state."""
        now_utc = datetime.now(timezone.utc).isoformat()
        batch_id = f"BATCH-{now_utc[:10].replace('-', '')}-{uuid.uuid4().hex[:8].upper()}"

        total_req = sum(item.loan_amount_inr for item in items)

        job = BatchJobStatus(
            batch_id=batch_id,
            org_id=org.org_id,
            batch_title=title,
            status="PENDING",
            total_records=len(items),
            processed_records=0,
            approved_count=0,
            conditional_count=0,
            rejected_count=0,
            total_requested_amount_inr=total_req,
            total_recommended_sanction_inr=0.0,
            created_at=now_utc,
            results=[],
            export_csv_url=f"/api/v1/b2b/batch-export/{batch_id}"
        )
        BATCH_REGISTRY[batch_id] = job
        return job

    def process_batch_sync(
        self,
        batch_id: str,
        org: B2BOrganization,
        items: List[BatchUnderwriteItem],
        webhook_url: Optional[str] = None
    ) -> BatchJobStatus:
        """
        Executes underwriting sequentially or asynchronously across all parcels in the batch.
        """
        job = BATCH_REGISTRY.get(batch_id)
        if not job:
            raise ValueError(f"Batch ID {batch_id} not found")

        job.status = "PROCESSING"
        results: List[B2BUnderwritingResponse] = []
        approved = 0
        conditional = 0
        rejected = 0
        total_sanction = 0.0

        for item in items:
            req = B2BUnderwritingRequest(
                case_ref=item.case_ref,
                applicant_name=item.applicant_name,
                loan_amount_inr=item.loan_amount_inr,
                district=item.district,
                mandal=item.mandal,
                village_name=item.village_name,
                survey_number=item.survey_number,
                extent_acres=item.extent_acres,
                proposed_end_use=item.proposed_end_use
            )
            res = self.underwriting_service.evaluate_underwriting(req, org)
            results.append(res)
            job.processed_records += 1

            if res.decision == UnderwritingDecision.APPROVAL_RECOMMENDED:
                approved += 1
                total_sanction += res.collateral_valuation.max_sanctionable_loan_amount_inr
            elif res.decision == UnderwritingDecision.CONDITIONAL_SANCTION:
                conditional += 1
                total_sanction += res.collateral_valuation.max_sanctionable_loan_amount_inr
            else:
                rejected += 1

        job.approved_count = approved
        job.conditional_count = conditional
        job.rejected_count = rejected
        job.total_recommended_sanction_inr = round(total_sanction, 2)
        job.status = "COMPLETED"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.results = results

        # Trigger webhook if specified
        if webhook_url:
            asyncio.create_task(
                self.underwriting_service.dispatch_webhook(
                    target_url=webhook_url,
                    secret=org.webhook_secret,
                    event_type="batch.completed",
                    data={
                        "batch_id": batch_id,
                        "batch_title": job.batch_title,
                        "total_records": job.total_records,
                        "approved_count": approved,
                        "conditional_count": conditional,
                        "rejected_count": rejected,
                        "total_sanction_inr": total_sanction,
                        "completed_at": job.completed_at
                    }
                )
            )

        return job

    def export_batch_to_csv(self, batch_id: str) -> str:
        """
        Generates comprehensive CSV string containing audit and underwriting verdicts for all parcels.
        """
        job = BATCH_REGISTRY.get(batch_id)
        if not job or not job.results:
            return ""

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Case Reference",
            "Borrower Entity",
            "Village",
            "Survey Number",
            "Extent (Acres)",
            "Underwriting Decision",
            "Risk Grade",
            "Composite Risk Score",
            "Section 22A Prohibited",
            "Layout Legitimacy",
            "Flood Risk",
            "Indicative Collateral Value (INR)",
            "Max Sanctionable Amount (INR)",
            "Max Recommended LTV (%)",
            "Decision Summary",
            "SHA-256 Digital Fingerprint",
            "Public Verification Certificate"
        ])

        for r in job.results:
            writer.writerow([
                r.case_ref,
                r.borrower_name,
                r.title_audit.get("village_name", ""),
                r.title_audit.get("survey_number", ""),
                r.collateral_valuation.extent_acres,
                r.decision.value,
                r.risk_grade,
                r.composite_risk_score,
                r.title_audit.get("section_22a_prohibited", False),
                r.layout_audit.get("layout_status", ""),
                r.flood_audit.get("flood_hazard_category", ""),
                r.collateral_valuation.total_indicative_collateral_value_inr,
                r.collateral_valuation.max_sanctionable_loan_amount_inr,
                r.collateral_valuation.max_recommended_ltv_pct,
                r.decision_summary,
                r.report_hash,
                r.digital_verification_url
            ])

        return output.getvalue()
