import os
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from typing import List, Dict, Any

from ..models.schemas import DueDiligenceQuery, DueDiligenceResult
from ..services.risk_scorer import RiskAssessmentEngine
from ..services.report_generator import DueDiligenceReportGenerator

router = APIRouter(prefix="/api/v1", tags=["Due Diligence"])
public_router = APIRouter(tags=["Public Verification"])

engine = RiskAssessmentEngine()
report_gen = DueDiligenceReportGenerator()

# Cache generated results in memory for fast report download & hash verification
REPORT_CACHE: Dict[str, DueDiligenceResult] = {}
HASH_REGISTRY: Dict[str, DueDiligenceResult] = {}

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "GeoDueDiligence API",
        "version": "1.0.0",
        "jurisdiction": "VMRDA Master Plan 2041 (Visakhapatnam Metropolitan Region - 7,328 km²)",
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
        HASH_REGISTRY[result.report_hash] = result
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
        HASH_REGISTRY[result.report_hash] = result
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
        # Fallback search by hash
        result = HASH_REGISTRY.get(report_id)
        
    if not result:
        raise HTTPException(status_code=404, detail=f"Report ID {report_id} not found in active session.")
    
    pdf_path = report_gen.generate_pdf(result)
    return FileResponse(
        path=pdf_path,
        filename=f"Due_Diligence_Report_{result.report_id}.pdf",
        media_type="application/pdf"
    )

@router.get("/verify-report/{report_hash}")
def api_verify_report_hash(report_hash: str):
    """
    REST API endpoint returning JSON verification record for external banking systems.
    """
    result = HASH_REGISTRY.get(report_hash)
    if not result:
        raise HTTPException(status_code=404, detail="Document hash not found or invalid.")
        
    return {
        "status": "AUTHENTIC_DOCUMENT_VERIFIED",
        "tamper_status": "INTACT",
        "report_id": result.report_id,
        "report_hash": result.report_hash,
        "generated_at": result.generated_at,
        "overall_risk_score": result.overall_risk_score,
        "overall_risk_grade": result.overall_risk_grade,
        "risk_status": result.risk_status,
        "target_parcel": result.target_parcel,
        "title_legal": {
            "pattadar_name": result.title_legal.pattadar_name,
            "section_22a_prohibited": result.title_legal.section_22a_prohibited,
            "land_nature": result.title_legal.land_nature
        },
        "zoning": {
            "zone_code": result.zoning.zone_code,
            "zone_name": result.zoning.zone_name
        }
    }

# Public Web Verification Endpoint for QR Code scans
@public_router.get("/verify/{report_hash}", response_class=HTMLResponse)
def public_verify_page(report_hash: str):
    result = HASH_REGISTRY.get(report_hash)
    
    if not result:
        # If not in cache, fallback to checking if it's a valid demo query or show unverified page
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8"><title>Audit Certificate Verification | GeoDueDiligence</title>
          <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-6">
          <div class="max-w-md w-full bg-slate-900 border border-rose-800/80 rounded-2xl p-6 shadow-2xl text-center">
            <div class="w-16 h-16 rounded-full bg-rose-950/60 border border-rose-500/40 flex items-center justify-center mx-auto mb-4 text-rose-400 text-3xl font-black">!</div>
            <h1 class="text-xl font-bold text-white mb-2">Unrecognized Certificate Hash</h1>
            <p class="text-xs text-slate-400 mb-4 font-mono break-all">{report_hash}</p>
            <p class="text-xs text-slate-400 mb-6">This document signature could not be corroborated against the active verification registry. Please re-run the verification query on the official portal.</p>
            <a href="/" class="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition">Return to Portal</a>
          </div>
        </body>
        </html>
        """, status_code=404)

    # Render Genuine Verified Certificate
    p = result.target_parcel
    grade_color = "#16A34A" if result.overall_risk_grade in ["A+", "A"] else ("#D97706" if result.overall_risk_grade == "B" else "#DC2626")
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Official Digital Certificate — {result.report_id}</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
      </style>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-4 sm:p-6">
      <div class="max-w-2xl w-full bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl relative overflow-hidden">
        
        <!-- Glowing Ambient Backdrop -->
        <div class="absolute -top-24 -right-24 w-64 h-64 rounded-full blur-3xl opacity-20 bg-emerald-500"></div>
        <div class="absolute -bottom-24 -left-24 w-64 h-64 rounded-full blur-3xl opacity-20 bg-blue-500"></div>

        <!-- Verification Header Badge -->
        <div class="flex items-center justify-between pb-6 border-b border-slate-800">
          <div class="flex items-center gap-3">
            <div class="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center shadow-lg shadow-emerald-500/20">
              <span class="text-emerald-400 text-2xl font-black">✓</span>
            </div>
            <div>
              <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Official Audit Certificate</span>
              <h1 class="text-lg font-extrabold text-white mt-1">Verified & Tamper-Free</h1>
            </div>
          </div>
          <div class="text-right">
            <div class="text-[10px] text-slate-400 font-bold uppercase">Integrity Status</div>
            <div class="text-xs font-mono font-bold text-emerald-400">100% INTACT</div>
          </div>
        </div>

        <!-- Certificate Body -->
        <div class="mt-6 space-y-4">
          
          <!-- Parcel Hero Card -->
          <div class="bg-slate-950/80 border border-slate-800/80 rounded-2xl p-4 flex items-center justify-between">
            <div>
              <div class="text-[11px] font-mono text-slate-400">Report Ref: {result.report_id}</div>
              <div class="text-base font-bold text-white mt-0.5">{p['village_name']} &bull; Survey No. {p['survey_number']}</div>
              <div class="text-xs text-slate-400 mt-0.5">{p['mandal']} Mandal, {p['district']} District</div>
            </div>
            <div class="text-right px-4 py-2 rounded-xl border border-slate-800 bg-slate-900/90">
              <div class="text-xl font-black" style="color: {grade_color};">Grade {result.overall_risk_grade}</div>
              <div class="text-[10px] font-bold text-slate-400 font-mono">{result.overall_risk_score} / 100</div>
            </div>
          </div>

          <!-- Audit Verified Parameters Grid -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/60">
              <span class="text-[10px] uppercase font-bold text-slate-400">Pattadar (Legal Owner):</span>
              <p class="font-semibold text-slate-200 mt-0.5">{result.title_legal.pattadar_name}</p>
            </div>
            <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/60">
              <span class="text-[10px] uppercase font-bold text-slate-400">Section 22A Prohibited:</span>
              <p class="font-semibold mt-0.5 {'text-rose-400' if result.title_legal.section_22a_prohibited else 'text-emerald-400'}">
                {'PROHIBITED' if result.title_legal.section_22a_prohibited else 'CLEAR (NOT PROHIBITED)'}
              </p>
            </div>
            <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/60">
              <span class="text-[10px] uppercase font-bold text-slate-400">VMRDA 2041 Zoning:</span>
              <p class="font-semibold text-slate-200 mt-0.5">{result.zoning.zone_name}</p>
            </div>
            <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800/60">
              <span class="text-[10px] uppercase font-bold text-slate-400">Layout Clearance:</span>
              <p class="font-semibold text-slate-200 mt-0.5">{result.layout.layout_status}</p>
            </div>
          </div>

          <!-- Cryptographic SHA-256 Digest Box -->
          <div class="p-4 bg-slate-950 rounded-2xl border border-slate-800">
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-[10px] uppercase font-bold text-slate-400">Immutable SHA-256 Digest</span>
              <span class="text-[10px] font-mono text-emerald-400">Verified Match</span>
            </div>
            <div class="p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-[10px] font-mono text-slate-300 break-all select-all">
              {result.report_hash}
            </div>
            <div class="mt-2 text-[10px] text-slate-400 flex items-center justify-between">
              <span>Timestamp: {result.generated_at}</span>
              <span>Framework: APMR&UDA Act 2016</span>
            </div>
          </div>

        </div>

        <!-- Footer Actions -->
        <div class="mt-6 pt-5 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          <a href="/api/v1/report/download/{result.report_id}" class="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold transition flex items-center gap-1.5 shadow-lg shadow-blue-600/30">
            <span>Download Certified PDF Report</span>
          </a>
          <a href="/" class="text-slate-400 hover:text-white transition">Back to Geospatial Dashboard &rarr;</a>
        </div>

      </div>
    </body>
    </html>
    """)
