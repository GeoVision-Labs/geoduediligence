import os
import time
import hmac
import hashlib
from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel
from fastapi import Request, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_AUTH = HTTPBearer(auto_error=False)

class B2BOrganization(BaseModel):
    org_id: str
    org_name: str
    org_type: str  # BANK, HFC, CREDAI_DEVELOPER, NBFC
    tier: str      # TRIAL, GROWTH, ENTERPRISE
    api_key: str
    webhook_secret: str
    requests_per_minute: int
    daily_quota: int
    contact_email: str
    created_at: str

# Default Pre-seeded Institutional Enterprise Keys
DEFAULT_ORGANIZATIONS: Dict[str, B2BOrganization] = {
    "gdd_live_sbi_enterprise_991823": B2BOrganization(
        org_id="ORG-SBI-001",
        org_name="State Bank of India — Visakhapatnam Commercial Hub",
        org_type="BANK",
        tier="ENTERPRISE",
        api_key="gdd_live_sbi_enterprise_991823",
        webhook_secret="whsec_sbi_live_7718923a10b441f9",
        requests_per_minute=300,
        daily_quota=10000,
        contact_email="commercial.vsp@sbi.co.in",
        created_at="2026-01-01T00:00:00Z"
    ),
    "gdd_live_hdfc_capital_441209": B2BOrganization(
        org_id="ORG-HDFC-002",
        org_name="HDFC Capital & Real Estate Project Finance",
        org_type="HFC",
        tier="ENTERPRISE",
        api_key="gdd_live_hdfc_capital_441209",
        webhook_secret="whsec_hdfc_live_389271a00cc9121a",
        requests_per_minute=300,
        daily_quota=10000,
        contact_email="realestate.underwriting@hdfc.com",
        created_at="2026-01-15T00:00:00Z"
    ),
    "gdd_live_lic_housing_771802": B2BOrganization(
        org_id="ORG-LICHFL-003",
        org_name="LIC Housing Finance Ltd — Andhra Pradesh Regional Office",
        org_type="HFC",
        tier="GROWTH",
        api_key="gdd_live_lic_housing_771802",
        webhook_secret="whsec_lichfl_991820aabbccddeeff",
        requests_per_minute=120,
        daily_quota=2000,
        contact_email="ap.underwriting@lichousing.com",
        created_at="2026-02-01T00:00:00Z"
    ),
    "gdd_test_credai_developer_123456": B2BOrganization(
        org_id="ORG-CREDAI-004",
        org_name="CREDAI Andhra Pradesh Developer Sandbox",
        org_type="CREDAI_DEVELOPER",
        tier="TRIAL",
        api_key="gdd_test_credai_developer_123456",
        webhook_secret="whsec_credai_sandbox_1122334455",
        requests_per_minute=30,
        daily_quota=100,
        contact_email="developer.sandbox@credai-ap.org",
        created_at="2026-03-01T00:00:00Z"
    )
}

class SlidingWindowRateLimiter:
    """
    Sliding window in-memory rate limiter tracking minute-level and day-level quotas per API key.
    """
    def __init__(self):
        # Maps api_key -> list of timestamp floats
        self._minute_buckets: Dict[str, List[float]] = {}
        # Maps api_key -> list of timestamp floats for current 24-hour window
        self._day_buckets: Dict[str, List[float]] = {}

    def check_and_record(self, org: B2BOrganization) -> Tuple[bool, Dict[str, int]]:
        now = time.time()
        api_key = org.api_key

        # 1. Clean up minute window (> 60s ago)
        min_cutoff = now - 60.0
        min_timestamps = [t for t in self._minute_buckets.get(api_key, []) if t > min_cutoff]
        self._minute_buckets[api_key] = min_timestamps

        # 2. Clean up daily window (> 86400s ago)
        day_cutoff = now - 86400.0
        day_timestamps = [t for t in self._day_buckets.get(api_key, []) if t > day_cutoff]
        self._day_buckets[api_key] = day_timestamps

        # 3. Check quotas
        minute_limit = org.requests_per_minute
        daily_limit = org.daily_quota

        minute_remaining = max(0, minute_limit - len(min_timestamps))
        daily_remaining = max(0, daily_limit - len(day_timestamps))

        telemetry = {
            "limit_minute": minute_limit,
            "remaining_minute": minute_remaining,
            "limit_day": daily_limit,
            "remaining_day": daily_remaining,
            "reset_seconds": 60 - int(now - min_timestamps[0]) if min_timestamps else 60
        }

        if len(min_timestamps) >= minute_limit:
            return False, telemetry
        if len(day_timestamps) >= daily_limit:
            return False, telemetry

        # Record this request
        min_timestamps.append(now)
        day_timestamps.append(now)
        self._minute_buckets[api_key] = min_timestamps
        self._day_buckets[api_key] = day_timestamps

        telemetry["remaining_minute"] = max(0, minute_limit - len(min_timestamps))
        telemetry["remaining_day"] = max(0, daily_limit - len(day_timestamps))

        return True, telemetry

rate_limiter = SlidingWindowRateLimiter()

def generate_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """
    Generates HMAC-SHA256 signature for webhook authenticity verification.
    """
    sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"

async def get_current_b2b_org(
    request: Request,
    api_key_header: Optional[str] = Security(API_KEY_HEADER),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(BEARER_AUTH)
) -> B2BOrganization:
    """
    FastAPI security dependency validating enterprise API keys and applying sliding-window rate limiting.
    Accepts keys via 'X-API-Key' header or 'Authorization: Bearer <key>'.
    """
    token = api_key_header
    if not token and bearer_creds:
        token = bearer_creds.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing institutional API Key. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    org = DEFAULT_ORGANIZATIONS.get(token)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or deactivated API Key. Contact GeoVision Labs enterprise support at enterprise@geovision.ai."
        )

    # Enforce Rate Limiting
    allowed, limits = rate_limiter.check_and_record(org)
    
    # Attach rate limit telemetry to request state for response headers
    request.state.rate_limits = limits

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit or daily quota exceeded for institutional tier",
                "org_name": org.org_name,
                "tier": org.tier,
                "minute_quota": f"{limits['remaining_minute']}/{limits['limit_minute']}",
                "daily_quota": f"{limits['remaining_day']}/{limits['limit_day']}",
                "retry_after_seconds": limits["reset_seconds"]
            },
            headers={
                "Retry-After": str(limits["reset_seconds"]),
                "X-RateLimit-Limit": str(limits["limit_minute"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(limits["reset_seconds"])
            }
        )

    return org
