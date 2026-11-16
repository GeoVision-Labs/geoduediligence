from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class DueDiligenceQuery(BaseModel):
    district: str = Field(default="Visakhapatnam", description="District name (e.g. Visakhapatnam, Vizianagaram, Anakapalli)")
    mandal: Optional[str] = Field(default="Anandapuram", description="Mandal name")
    village_name: str = Field(..., description="Target village name (e.g. Tarluvada, Gambheeram, Bhogapuram)")
    survey_number: str = Field(..., description="Survey Number (e.g. 72, 80, 142/1)")
    purpose: Optional[str] = Field(default="Commercial / Residential Development", description="Buyer's intended land use")

class ZoningDetails(BaseModel):
    zone_code: str
    zone_name: str
    permitted_uses: List[str]
    restricted_uses: List[str]
    road_widening_reservation: str
    master_plan_reference: str = "VMRDA Master Plan 2041 (Map 4)"
    zoning_risk_score: float # 0 - 100
    risk_level: str # Low, Moderate, High, Critical

class LegalTitleDetails(BaseModel):
    pattadar_name: str
    anubhavadar_name: str
    khata_number: str
    extent_acres: float
    land_nature: str # Patta, Government Assigned, D-Form, Poramboke, Waqf, Inam
    section_22a_prohibited: bool
    title_dispute_flag: bool
    source_portal: str = "AP MeeBhoomi / Webland Revenue Record"
    title_risk_score: float
    risk_level: str
    provenance: Optional[str] = Field(default="VERIFIED_RECORD", description="Data provenance: LIVE_SCRAPER, CACHE_HIT, or BASELINE_FALLBACK")
    latency_ms: Optional[float] = Field(default=0.0, description="Query retrieval latency in milliseconds")

class LayoutLegitimacyDetails(BaseModel):
    lp_number: Optional[str]
    approval_year: Optional[int]
    layout_status: str # Approved LP, Unauthorized Layout, Unplatted Agricultural
    is_unauthorized_list: bool
    lrs_eligible: bool
    civic_utility_clearance: str
    layout_risk_score: float
    risk_level: str

class FloodTerrainDetails(BaseModel):
    elevation_meters: float
    slope_percentage: float
    catchment_drainage_type: str
    topographic_wetness_index: float
    distance_to_waterbody_meters: float
    flood_hazard_category: str # Low, Moderate, Elevated, High Risk
    climate_risk_score: float
    risk_level: str

class DueDiligenceResult(BaseModel):
    report_id: str
    generated_at: str
    target_parcel: Dict[str, Any]
    overall_risk_score: float # 0 - 100
    overall_risk_grade: str # A+, A, B, C, D, F
    risk_status: str # SAFE TO ACQUIRE, CONDITIONAL / PROCEED WITH CAUTION, HIGH RISK / DO NOT PROCEED
    red_flag_alerts: List[str]
    positive_indicators: List[str]
    zoning: ZoningDetails
    title_legal: LegalTitleDetails
    layout: LayoutLegitimacyDetails
    terrain_flood: FloodTerrainDetails
    coordinates: Dict[str, float]
    summary_verdict: str
    report_hash: str = Field(..., description="Cryptographic SHA-256 digest of the audit payload")
    verification_url: str = Field(..., description="Public digital certificate verification URL")
