import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx

from ..models.b2b_schemas import (
    B2BUnderwritingRequest,
    B2BUnderwritingResponse,
    UnderwritingDecision,
    CollateralValuation
)
from ..models.schemas import DueDiligenceQuery, DueDiligenceResult
from ..services.risk_scorer import RiskAssessmentEngine
from ..core.security import B2BOrganization, generate_webhook_signature

logger = logging.getLogger(__name__)

class UnderwritingService:
    """
    Automated credit risk and land collateral underwriting engine for Banks, HFCs, and CREDAI developers.
    Applies RBI / NHB macro-prudential LTV constraints, statutory VMRDA encumbrance covenants,
    and market guidance collateral valuations.
    """

    # VMRDA Corridor Land Guidance & Market Value Baselines (in INR per Acre)
    CORRIDOR_RATES: Dict[str, Dict[str, float]] = {
        "anandapuram": {"guidance": 6500000.0, "market": 16000000.0},
        "tarluvada": {"guidance": 6500000.0, "market": 16000000.0},
        "gambheeram": {"guidance": 7500000.0, "market": 19000000.0},
        "madhurawada": {"guidance": 12000000.0, "market": 32000000.0},
        "bhogapuram": {"guidance": 5500000.0, "market": 14000000.0},
        "atchutapuram": {"guidance": 4500000.0, "market": 11000000.0},
        "paravada": {"guidance": 4800000.0, "market": 12000000.0},
        "pendurthi": {"guidance": 7000000.0, "market": 17500000.0},
        "default": {"guidance": 3500000.0, "market": 8500000.0}
    }

    def __init__(self):
        self.risk_engine = RiskAssessmentEngine()

    def _resolve_valuation_rates(self, village_name: str, mandal_name: str) -> Dict[str, float]:
        v_key = village_name.strip().lower()
        m_key = mandal_name.strip().lower()
        if v_key in self.CORRIDOR_RATES:
            return self.CORRIDOR_RATES[v_key]
        if m_key in self.CORRIDOR_RATES:
            return self.CORRIDOR_RATES[m_key]
        return self.CORRIDOR_RATES["default"]

    def evaluate_underwriting(
        self,
        request: B2BUnderwritingRequest,
        org: B2BOrganization
    ) -> B2BUnderwritingResponse:
        """
        Executes end-to-end institutional underwriting analysis on the target parcel.
        """
        now_utc = datetime.now(timezone.utc)
        underwriting_id = f"UW-{org.org_type[:3]}-{now_utc.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # 1. Run Spatial & Statutory Due Diligence
        dd_query = DueDiligenceQuery(
            district=request.district,
            mandal=request.mandal or "Anandapuram",
            village_name=request.village_name,
            survey_number=request.survey_number,
            purpose=request.proposed_end_use or "Institutional Mortgage"
        )
        dd_result: DueDiligenceResult = self.risk_engine.run_due_diligence(dd_query)

        # 2. Collateral Valuation Estimation
        extent = request.extent_acres or dd_result.title_legal.extent_acres or 1.0
        rates = self._resolve_valuation_rates(request.village_name, request.mandal or "Anandapuram")
        guidance_rate = rates["guidance"]
        market_rate = rates["market"]
        total_market_val = round(extent * market_rate, 2)

        # 3. Formulate Underwriting Decision, Max LTV, and Covenants
        composite_score = dd_result.overall_risk_score
        is_prohibited = dd_result.title_legal.section_22a_prohibited
        is_unauth = dd_result.layout.is_unauthorized_list
        is_buffer_violation = dd_result.terrain_flood.distance_to_waterbody_meters < 30.0

        covenants: List[str] = []
        critical_breaches: List[str] = list(dd_result.red_flag_alerts)
        positive_indicators: List[str] = list(dd_result.positive_indicators)

        if is_prohibited or is_unauth or composite_score > 48.0:
            # Mandated Rejection
            decision = UnderwritingDecision.REJECTION_MANDATED
            max_ltv_pct = 0.0
            max_sanctionable = 0.0
            if is_prohibited:
                decision_summary = (
                    "MANDATORY REJECTION: Collateral is classified under Section 22A AP Registration Act "
                    "(Non-alienable government/assigned land). Creation of mortgage is legally void under Indian law."
                )
            elif is_unauth:
                decision_summary = (
                    "MANDATORY REJECTION: Parcel falls inside an Unauthorized Layout notified for demolition by VMRDA. "
                    "Mortgage facility prohibited by state urban development regulations."
                )
            else:
                decision_summary = (
                    f"MANDATORY REJECTION: Elevated statutory risk grade ({dd_result.overall_risk_grade}, Score: {composite_score:.1f}). "
                    "Fails institutional credit underwriting criteria."
                )

        elif composite_score > 32.0:
            # Conditional Sanction (Grade B)
            decision = UnderwritingDecision.CONDITIONAL_SANCTION
            max_ltv_pct = 50.0  # 50% LTV cap for conditional properties
            max_sanctionable = min(request.loan_amount_inr, round(total_market_val * 0.50, 2))
            decision_summary = (
                f"CONDITIONAL SANCTION: Facility recommended at capped 50% LTV (Max: INR {max_sanctionable:,.0f}). "
                "Disbursement subject to satisfaction of pre-disbursement legal and technical covenants."
            )

            # Specific conditional covenants
            if "Road Widening" in dd_result.zoning.road_widening_reservation:
                covenants.append(
                    f"Setback Covenant: Borrower must execute statutory Registered Relinquishment Deed (Gift Deed) "
                    f"to VMRDA for {dd_result.zoning.road_widening_reservation} before facility drawdown."
                )
            if dd_result.title_legal.title_dispute_flag:
                covenants.append(
                    "Title Covenant: Discrepancy detected between Pattadar and Anubhavadar. "
                    "Obtain registered Partition / Release Deed and Tahsildar Webland mutation certificate."
                )
            covenants.append("Obtain SRO Non-Encumbrance Certificate (Form 15) for preceding 30 years prior to disbursement.")
            covenants.append("Deposition of original registered title deeds with Bank/HFC to establish equitable mortgage by title deposit.")

        else:
            # Prime Sanction (Grade A+ or A)
            decision = UnderwritingDecision.APPROVAL_RECOMMENDED
            max_ltv_pct = 75.0  # Full 75% LTV sanctioned for prime titles
            max_sanctionable = min(request.loan_amount_inr, round(total_market_val * 0.75, 2))
            decision_summary = (
                f"APPROVAL RECOMMENDED: Clear marketable title, compliant VMRDA zoning, and verified layout clearance. "
                f"Full facility of INR {max_sanctionable:,.0f} approved at 75% LTV."
            )
            covenants.append("SRO Non-Encumbrance Certificate (Form 15) for preceding 30 years confirming NIL charges.")
            covenants.append("Creation and registration of Simple Mortgage / Deposit of Title Deeds at local Sub-Registrar Office.")
            covenants.append("VMRDA approved building plan / development permission copy prior to secondary tranche drawdown.")

        collateral_val = CollateralValuation(
            extent_acres=round(extent, 2),
            guidance_rate_per_acre_inr=guidance_rate,
            market_estimate_per_acre_inr=market_rate,
            total_indicative_collateral_value_inr=total_market_val,
            max_recommended_ltv_pct=max_ltv_pct,
            max_sanctionable_loan_amount_inr=max_sanctionable,
            valuation_basis=f"VMRDA 2041 {rates.get('market', 0)/10000000:.1f} Cr/Ac corridor model"
        )

        response = B2BUnderwritingResponse(
            case_ref=request.case_ref,
            underwriting_id=underwriting_id,
            decision=decision,
            decision_summary=decision_summary,
            risk_grade=dd_result.overall_risk_grade,
            composite_risk_score=dd_result.overall_risk_score,
            collateral_valuation=collateral_val,
            pre_disbursement_covenants=covenants,
            critical_statutory_breaches=critical_breaches,
            positive_credit_indicators=positive_indicators,
            title_audit=dd_result.title_legal.model_dump(),
            zoning_audit=dd_result.zoning.model_dump(),
            layout_audit=dd_result.layout.model_dump(),
            flood_audit=dd_result.terrain_flood.model_dump(),
            report_hash=dd_result.report_hash,
            digital_verification_url=dd_result.verification_url,
            underwritten_at=now_utc.isoformat(),
            borrower_name=request.applicant_name,
            sanctioning_org=org.org_name
        )

        return response

    async def dispatch_webhook(
        self,
        target_url: str,
        secret: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        Asynchronously dispatches an HMAC-SHA256 authenticated webhook event to subscriber URL.
        """
        import json
        payload_obj = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        payload_bytes = json.dumps(payload_obj, default=str).encode("utf-8")
        signature = generate_webhook_signature(payload_bytes, secret)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "GeoDueDiligence-Webhook/1.0",
            "X-GDD-Signature": signature,
            "X-GDD-Event": event_type
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(target_url, content=payload_bytes, headers=headers)
                logger.info(f"Dispatched webhook to {target_url} (HTTP {resp.status_code})")
                return 200 <= resp.status_code < 300
        except Exception as e:
            logger.warning(f"Failed to dispatch webhook to {target_url}: {e}")
            return False
