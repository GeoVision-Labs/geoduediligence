import logging
from typing import Dict, Any, Optional

from .meebhoomi_scraper.daemon import MeeBhoomiScraperDaemon

logger = logging.getLogger(__name__)

class MeeBhoomiService:
    """
    Automated connector and verification engine for Andhra Pradesh MeeBhoomi / Webland records.
    Powered by MeeBhoomiScraperDaemon with OCR captcha solving, multi-tier caching (Redis + In-Memory),
    and fail-safe verified baseline snapshots for seamless zero-downtime due diligence.
    """
    def __init__(self, redis_url: Optional[str] = None):
        self.daemon = MeeBhoomiScraperDaemon(redis_url=redis_url)

    def verify_title_records(
        self,
        village_name: str,
        survey_number: str,
        district_name: str = "Visakhapatnam",
        mandal_name: str = "Anandapuram"
    ) -> Dict[str, Any]:
        """
        Synchronously queries and audits MeeBhoomi Adangal and 1B records for the specified village and survey number.
        """
        return self.daemon.query_title_sync(
            village_name=village_name,
            survey_number=survey_number,
            district_name=district_name,
            mandal_name=mandal_name
        )

    async def verify_title_records_async(
        self,
        village_name: str,
        survey_number: str,
        district_name: str = "Visakhapatnam",
        mandal_name: str = "Anandapuram"
    ) -> Dict[str, Any]:
        """
        Asynchronous coroutine for querying and auditing MeeBhoomi records.
        """
        return await self.daemon.query_title_async(
            village_name=village_name,
            survey_number=survey_number,
            district_name=district_name,
            mandal_name=mandal_name
        )
