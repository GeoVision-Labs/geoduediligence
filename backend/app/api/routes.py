import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from typing import List, Dict, Any

from ..models.schemas import DueDiligenceQuery, DueDiligenceResult
from ..services.risk_scorer import RiskAssessmentEngine
from ..services.report_generator import DueDiligenceReportGenerator

router = APIRouter(prefix="/api/v1", tags=["Due Diligence"])

engine = RiskAssessmentEngine()
report_gen = DueDiligenceReportGenerator()

# Cache generated results in memory for fast report download
REPORT_CACHE: Dict[str, DueDiligenceResult] = {}

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "GeoDueDiligence API",
        "version": "1.0.0",
        "jurisdiction": "VMRDA Master Plan 2041 (Visakhapatnam Metropolitan Region)",
        "indexed_villages_count": len(engine.spatial_engine.data.get("villages", {}))
    }

@router.get("/villages")
def get_villages():
    """
    List all indexed villages in the VMRDA jurisdiction.
    """
    return engine.spatial_engine.list_villages()

@router.get("/villages/{village_name}/surveys")
def get_village_surveys(village_name: str):
    """
    Returns available survey numbers for a specific village.
    """
    surveys = engine.spatial_engine.list_surveys_for_village(village_name)
    if not surveys:
        raise HTTPException(status_code=404, detail=f"No survey numbers found for village: {village_name}")
    return {"village_name": village_name, "total_surveys": len(surveys), "survey_numbers": surveys}

@router.post("/verify", response_model=DueDiligenceResult)
def verify_parcel(query: DueDiligenceQuery):
    """
    Runs spatial multi-layer risk assessment on specified village and survey number.
    Returns composite risk scores, red flags, and zoning/title/layout/flood breakdowns.
    """
    try:
        result = engine.run_due_diligence(query)
        REPORT_CACHE[result.report_id] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Due diligence computation error: {str(e)}")

@router.post("/report/generate-pdf")
def generate_pdf_report(query: DueDiligenceQuery):
    """
    Generates and returns the downloadable 5-Page Investor Due Diligence PDF Report.
    """
    try:
        result = engine.run_due_diligence(query)
        REPORT_CACHE[result.report_id] = result
        pdf_path = report_gen.generate_pdf(result)
        
        return FileResponse(
            path=pdf_path,
            filename=f"Due_Diligence_Report_{result.report_id}.pdf",
            media_type="application/pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")

@router.get("/report/download/{report_id}")
def download_cached_report(report_id: str):
    """
    Download a previously computed report PDF by its Report ID.
    """
    result = REPORT_CACHE.get(report_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Report ID {report_id} not found.")
    
    pdf_path = report_gen.generate_pdf(result)
    return FileResponse(
        path=pdf_path,
        filename=f"Due_Diligence_Report_{report_id}.pdf",
        media_type="application/pdf"
    )
