from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Response, status
from typing import Optional, List, Dict, Any

from ..core.security import B2BOrganization, get_current_b2b_org, generate_webhook_signature
from ..models.b2b_schemas import (
    B2BUnderwritingRequest,
    B2BUnderwritingResponse,
    BatchUnderwriteRequest,
    BatchJobStatus,
    WebhookTestRequest
)
from ..services.underwriting_service import UnderwritingService
from ..services.batch_processor import BatchProcessor, BATCH_REGISTRY

router = APIRouter(prefix="/api/v1/b2b", tags=["B2B Institutional Underwriting"])

underwriting_service = UnderwritingService()
batch_processor = BatchProcessor()

@router.get("/me")
def get_organization_profile(org: B2BOrganization = Depends(get_current_b2b_org)):
    """
    Returns authenticated institutional organization details, tier quotas, and webhook configuration.
    """
    return {
        "org_id": org.org_id,
        "org_name": org.org_name,
        "org_type": org.org_type,
        "tier": org.tier,
        "requests_per_minute": org.requests_per_minute,
        "daily_quota": org.daily_quota,
        "contact_email": org.contact_email,
        "webhook_secret_prefix": f"{org.webhook_secret[:10]}..."
    }

@router.post("/underwrite", response_model=B2BUnderwritingResponse)
async def underwrite_loan_application(
    request: B2BUnderwritingRequest,
    background_tasks: BackgroundTasks,
    org: B2BOrganization = Depends(get_current_b2b_org)
):
    """
    Executes automated statutory due diligence and credit underwriting on a single mortgaged parcel.
    Returns credit decision (APPROVAL_RECOMMENDED, CONDITIONAL_SANCTION, REJECTION_MANDATED),
    maximum recommended LTV, collateral valuation, and statutory pre-disbursement covenants.
    """
    try:
        response = underwriting_service.evaluate_underwriting(request, org)

        # Trigger async webhook if URL was provided
        if request.webhook_url:
            background_tasks.add_task(
                underwriting_service.dispatch_webhook,
                target_url=request.webhook_url,
                secret=org.webhook_secret,
                event_type="underwrite.completed",
                data=response.model_dump()
            )

        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Underwriting evaluation error: {str(e)}"
        )

@router.post("/batch-underwrite", response_model=BatchJobStatus)
def batch_underwrite_parcels(
    batch_req: BatchUnderwriteRequest,
    org: B2BOrganization = Depends(get_current_b2b_org)
):
    """
    Submits a batch portfolio of up to 500 loan parcels for automated multi-layer underwriting.
    Returns real-time aggregated portfolio audit statistics and CSV export link.
    """
    if not batch_req.items:
        raise HTTPException(status_code=400, detail="Batch item list cannot be empty")

    if len(batch_req.items) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 parcels allowed per batch query")

    job = batch_processor.create_batch_job(
        title=batch_req.batch_title,
        org=org,
        items=batch_req.items,
        webhook_url=batch_req.webhook_url
    )

    completed_job = batch_processor.process_batch_sync(
        batch_id=job.batch_id,
        org=org,
        items=batch_req.items,
        webhook_url=batch_req.webhook_url
    )

    return completed_job

@router.post("/batch-upload-csv", response_model=BatchJobStatus)
async def batch_upload_csv(
    file: UploadFile = File(...),
    batch_title: str = Form("CSV Portfolio Audit"),
    webhook_url: Optional[str] = Form(None),
    org: B2BOrganization = Depends(get_current_b2b_org)
):
    """
    Accepts CSV upload of loan portfolio or developer layouts and processes full statutory underwriting.
    Accepted columns: case_ref, applicant_name, loan_amount_inr, district, mandal, village_name, survey_number, extent_acres.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    content = await file.read()
    csv_text = content.decode("utf-8", errors="replace")

    items = batch_processor.parse_csv_to_items(csv_text)
    if not items:
        raise HTTPException(status_code=400, detail="Unable to parse valid parcel records from CSV file")

    job = batch_processor.create_batch_job(
        title=batch_title,
        org=org,
        items=items,
        webhook_url=webhook_url
    )

    completed_job = batch_processor.process_batch_sync(
        batch_id=job.batch_id,
        org=org,
        items=items,
        webhook_url=webhook_url
    )

    return completed_job

@router.get("/batch-status/{batch_id}", response_model=BatchJobStatus)
def get_batch_job_status(
    batch_id: str,
    org: B2BOrganization = Depends(get_current_b2b_org)
):
    """
    Returns real-time processing status, sanction summary counters, and results for a batch audit.
    """
    job = BATCH_REGISTRY.get(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Batch job {batch_id} not found")

    if job.org_id != org.org_id and org.tier != "ENTERPRISE":
        raise HTTPException(status_code=403, detail="Unauthorized access to tenant batch record")

    return job

@router.get("/batch-export/{batch_id}")
def export_batch_audit_csv(
    batch_id: str,
    org: B2BOrganization = Depends(get_current_b2b_org)
):
    """
    Downloads full audited CSV export with Section 22A prohibited flags, layout clearances,
    risk grades, collateral valuations, and SHA-256 verification links.
    """
    job = BATCH_REGISTRY.get(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Batch job {batch_id} not found")

    csv_data = batch_processor.export_batch_to_csv(batch_id)
    if not csv_data:
        raise HTTPException(status_code=400, detail="Batch results are empty or not yet completed")

    filename = f"Due_Diligence_Portfolio_Audit_{batch_id}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/webhooks/test")
async def test_webhook_endpoint(
    req: WebhookTestRequest,
    org: B2BOrganization = Depends(get_current_b2b_org)
):
    """
    Sends a test HMAC-SHA256 authenticated webhook event to subscriber URL to verify integration.
    """
    sample_data = {
        "event_id": f"evt_test_{org.org_id.lower()}",
        "message": "GeoVision Due Diligence Webhook handshake successful",
        "org_name": org.org_name,
        "tier": org.tier
    }
    success = await underwriting_service.dispatch_webhook(
        target_url=req.target_url,
        secret=org.webhook_secret,
        event_type=req.event_type,
        data=sample_data
    )
    return {
        "status": "success" if success else "failed",
        "target_url": req.target_url,
        "event_type": req.event_type,
        "webhook_dispatched": success,
        "webhook_secret_used": f"{org.webhook_secret[:8]}..."
    }
