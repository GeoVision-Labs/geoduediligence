from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class UnderwritingDecision(str, Enum):
    APPROVAL_RECOMMENDED = "APPROVAL_RECOMMENDED"      # Grade A+, A: Clear Title, Compliant Zoning, Approved LP
    CONDITIONAL_SANCTION = "CONDITIONAL_SANCTION"      # Grade B: Conditional (road widening setback, tenancy NOC)
    REJECTION_MANDATED   = "REJECTION_MANDATED"        # Grade C, D, F: Section 22A Prohibited, Unauthorized Layout, Nala buffer violation

class B2BUnderwritingRequest(BaseModel):
    case_ref: str = Field(..., example="SBI-VSP-2024-8841", description="Bank Loan Application ID / Case Reference")
    applicant_name: str = Field(..., example="Sri K. Satyanarayana Raju", description="Borrower or Developer Entity")
    loan_amount_inr: float = Field(..., example=25000000.0, description="Requested credit facility in INR")
    district: str = Field(default="Visakhapatnam", description="District (Visakhapatnam, Vizianagaram, Anakapalli)")
    mandal: Optional[str] = Field(default="Anandapuram", description="Mandal")
    village_name: str = Field(..., example="Tarluvada", description="Revenue Village Name")
    survey_number: str = Field(..., example="72", description="Cadastral Survey Number")
    extent_acres: Optional[float] = Field(default=None, description="Land extent in acres (resolved from MeeBhoomi if omitted)")
    proposed_end_use: Optional[str] = Field(default="Residential Plotted Development", description="Proposed mortgage purpose")
    webhook_url: Optional[str] = Field(default=None, description="Callback URL for asynchronous webhook events")
    include_pdf_report: Optional[bool] = Field(default=False, description="Whether to generate downloadable investor PDF")

class CollateralValuation(BaseModel):
    extent_acres: float
    guidance_rate_per_acre_inr: float
    market_estimate_per_acre_inr: float
    total_indicative_collateral_value_inr: float
    max_recommended_ltv_pct: float
    max_sanctionable_loan_amount_inr: float
    valuation_basis: str

class B2BUnderwritingResponse(BaseModel):
    case_ref: str
    underwriting_id: str
    decision: UnderwritingDecision
    decision_summary: str
    risk_grade: str
    composite_risk_score: float
    collateral_valuation: CollateralValuation
    pre_disbursement_covenants: List[str]
    critical_statutory_breaches: List[str]
    positive_credit_indicators: List[str]
    title_audit: Dict[str, Any]
    zoning_audit: Dict[str, Any]
    layout_audit: Dict[str, Any]
    flood_audit: Dict[str, Any]
    report_hash: str
    digital_verification_url: str
    underwritten_at: str
    borrower_name: str
    sanctioning_org: str

class BatchUnderwriteItem(BaseModel):
    case_ref: str
    applicant_name: str
    loan_amount_inr: float
    district: str = "Visakhapatnam"
    mandal: Optional[str] = "Anandapuram"
    village_name: str
    survey_number: str
    extent_acres: Optional[float] = None
    proposed_end_use: Optional[str] = "Residential Plotted Layout"

class BatchUnderwriteRequest(BaseModel):
    batch_title: str = Field(default="Portfolio Audit", description="Batch identification title")
    webhook_url: Optional[str] = None
    items: List[BatchUnderwriteItem]

class BatchJobStatus(BaseModel):
    batch_id: str
    org_id: str
    batch_title: str
    status: str  # PENDING, PROCESSING, COMPLETED, FAILED
    total_records: int
    processed_records: int
    approved_count: int
    conditional_count: int
    rejected_count: int
    total_requested_amount_inr: float
    total_recommended_sanction_inr: float
    created_at: str
    completed_at: Optional[str] = None
    results: Optional[List[B2BUnderwritingResponse]] = None
    export_csv_url: Optional[str] = None

class WebhookTestRequest(BaseModel):
    target_url: str = Field(..., example="https://webhook.site/uuid")
    event_type: str = Field(default="underwrite.completed", example="underwrite.completed")
