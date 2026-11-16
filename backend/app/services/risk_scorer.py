import uuid
from datetime import datetime
from typing import Dict, Any, List

from .spatial_engine import SpatialEngine
from .meebhoomi_service import MeeBhoomiService
from .layout_service import LayoutService
from .flood_service import FloodTerrainService
from ..models.schemas import (
    DueDiligenceQuery,
    DueDiligenceResult,
    ZoningDetails,
    LegalTitleDetails,
    LayoutLegitimacyDetails,
    FloodTerrainDetails
)

class RiskAssessmentEngine:
    def __init__(self):
        self.spatial_engine = SpatialEngine()
        self.meebhoomi_service = MeeBhoomiService()
        self.layout_service = LayoutService()
        self.flood_service = FloodTerrainService()

    def run_due_diligence(self, query: DueDiligenceQuery) -> DueDiligenceResult:
        v_name = query.village_name.strip()
        s_no = query.survey_number.strip()
        
        # 1. Spatial & Zoning Query
        survey_rec = self.spatial_engine.get_survey_record(v_name, s_no)
        zoning_data = self.spatial_engine.query_zoning(
            v_name, s_no, district=query.district, mandal=query.mandal or "Anandapuram"
        )
        
        lat = survey_rec["latitude"] if survey_rec else 17.8920
        lon = survey_rec["longitude"] if survey_rec else 83.3950
        
        # 2. MeeBhoomi Title & 22A Check
        title_data = self.meebhoomi_service.verify_title_records(v_name, s_no)
        
        # 3. Layout Clearance Check
        layout_data = self.layout_service.check_layout_clearance(v_name, s_no)
        
        # 4. Flood & Topography Check
        flood_data = self.flood_service.evaluate_flood_hazard(v_name, s_no, lat, lon)
        
        # 5. Composite Weighted Risk Calculation
        # Weights: Zoning 30%, Title 35%, Layout 20%, Flood 15%
        w_zoning = 0.30
        w_title = 0.35
        w_layout = 0.20
        w_flood = 0.15
        
        rz = zoning_data["zoning_risk_score"]
        rt = title_data["title_risk_score"]
        rl = layout_data["layout_risk_score"]
        rf = flood_data["climate_risk_score"]
        
        # Severe penalty overrides for critical legal blocks
        if title_data["section_22a_prohibited"]:
            rt = 100.0
        if layout_data["is_unauthorized_list"]:
            rl = max(rl, 85.0)
            
        composite_score = round(w_zoning * rz + w_title * rt + w_layout * rl + w_flood * rf, 1)
        
        # 6. Assign Grade and Verdict
        red_flags: List[str] = []
        positive_indicators: List[str] = []
        
        if title_data["section_22a_prohibited"]:
            red_flags.append("CRITICAL: Land listed under Section 22A AP Registration Prohibited Property (Non-alienable government/assigned land).")
        else:
            positive_indicators.append("Verified clear title under MeeBhoomi Rayituwari Patta registry.")
            
        if layout_data["is_unauthorized_list"]:
            red_flags.append("ALERT: Plot falls inside an unauthorized layout notified by VMRDA Enforcement Wing (Demolition / utility sanction freeze risk).")
        elif layout_data.get("lp_number"):
            positive_indicators.append(f"Approved Layout Permission ({layout_data['lp_number']}) confirmed in VMRDA database.")
            
        if flood_data["distance_to_waterbody_meters"] < 30.0:
            red_flags.append(f"ENVIRONMENTAL BUFFER VIOLATION: Parcel is within {flood_data['distance_to_waterbody_meters']}m of natural drainage canal (violates 30m statutory buffer).")
        else:
            positive_indicators.append(f"Well-elevated terrain ({flood_data['elevation_meters']}m MSL) with natural stormwater drainage.")
            
        if zoning_data["zoning_risk_score"] > 60:
            red_flags.append(f"ZONING MISMATCH: Master Plan 2041 designates parcel as '{zoning_data['zone_name']}'. Incompatible with unapproved residential development.")
        else:
            positive_indicators.append(f"Conforming Master Plan 2041 zoning ({zoning_data['zone_name']}).")

        # Grade calculation
        if composite_score <= 18:
            grade = "A+"
            status = "SAFE TO ACQUIRE / PRIME ASSET"
            verdict = "Clear title, compliant VMRDA 2041 zoning, and no municipal or environmental encumbrances detected."
        elif composite_score <= 32:
            grade = "A"
            status = "LOW RISK / PROCEED WITH STANDARD DUE DILIGENCE"
            verdict = "Overall low risk. Standard conversion (NALA) or layout plan submission required prior to construction."
        elif composite_score <= 48:
            grade = "B"
            status = "MODERATE RISK / CONDITIONAL ACQUISITION"
            verdict = "Notable conditions detected (e.g. road widening setback reservation or tenancy verification needed)."
        elif composite_score <= 65:
            grade = "C"
            status = "ELEVATED RISK / LEGAL REMEDIATION REQUIRED"
            verdict = "Requires Layout Regularisation Scheme (LRS) or Master Plan zoning variance before purchase."
        elif composite_score <= 80:
            grade = "D"
            status = "HIGH RISK / TRANSACTION DISCOURAGED"
            verdict = "Severe zoning or flood catchment risk. Capital loss potential is substantial."
        else:
            grade = "F"
            status = "CRITICAL RISK / DO NOT PROCEED (PROHIBITED)"
            verdict = "Acquisition is illegal or blocked by Section 22A prohibited property or municipal demolition order."

        report_uuid = f"GDD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        return DueDiligenceResult(
            report_id=report_uuid,
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            target_parcel={
                "district": query.district,
                "mandal": query.mandal,
                "village_name": v_name,
                "survey_number": s_no,
                "purpose": query.purpose,
                "pdf_part_reference": zoning_data.get("master_plan_reference", "VMR Master Plan 2041 (Full 7,328 km² Jurisdiction)")
            },
            overall_risk_score=composite_score,
            overall_risk_grade=grade,
            risk_status=status,
            red_flag_alerts=red_flags,
            positive_indicators=positive_indicators,
            zoning=ZoningDetails(**zoning_data),
            title_legal=LegalTitleDetails(**title_data),
            layout=LayoutLegitimacyDetails(**layout_data),
            terrain_flood=FloodTerrainDetails(**flood_data),
            coordinates={"latitude": lat, "longitude": lon},
            summary_verdict=verdict
        )
