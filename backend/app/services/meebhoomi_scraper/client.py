import os
import re
import logging
from typing import Dict, Any, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

from .captcha_solver import MeeBhoomiCaptchaSolver
from .parser import MeeBhoomiParser

logger = logging.getLogger(__name__)

class MeeBhoomiPortalError(Exception):
    """Custom exception raised when AP MeeBhoomi portal is unreachable or returns server errors."""
    pass

class MeeBhoomiClient:
    """
    Headless async HTTP client for Andhra Pradesh MeeBhoomi / Webland revenue portals.
    Orchestrates ASP.NET WebForms session negotiation, ViewState extraction,
    captcha acquisition & solving, and query postbacks.
    """

    DEFAULT_BASE_URL = os.getenv("MEEBHOOMI_PORTAL_URL", "https://meebhoomi.ap.gov.in")
    DEFAULT_TIMEOUT = float(os.getenv("MEEBHOOMI_TIMEOUT", "4.0"))
    DEFAULT_MAX_RETRIES = int(os.getenv("MEEBHOOMI_RETRIES", "1"))
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        proxy: Optional[str] = None,
        mock_mode: bool = False
    ):
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else self.DEFAULT_MAX_RETRIES
        self.proxy = proxy or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        self.mock_mode = mock_mode or (os.getenv("MEEBHOOMI_MOCK_MODE", "false").lower() == "true")
        
        self.captcha_solver = MeeBhoomiCaptchaSolver()
        self.parser = MeeBhoomiParser()

    def _get_client(self) -> httpx.AsyncClient:
        """Configures httpx AsyncClient with cookiejar and proxy if provided."""
        kwargs: Dict[str, Any] = {
            "timeout": httpx.Timeout(self.timeout),
            "follow_redirects": True,
            "verify": False,  # NIC portals frequently have internal or expired cert chains
            "headers": {
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,te;q=0.8",
                "Connection": "keep-alive"
            }
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.AsyncClient(**kwargs)

    def _extract_aspnet_tokens(self, html: str) -> Dict[str, str]:
        """Extracts __VIEWSTATE, __EVENTVALIDATION, and __VIEWSTATEGENERATOR hidden fields."""
        soup = BeautifulSoup(html, "html.parser")
        tokens: Dict[str, str] = {}
        for field in ["__VIEWSTATE", "__EVENTVALIDATION", "__VIEWSTATEGENERATOR", "__EVENTTARGET", "__EVENTARGUMENT"]:
            tag = soup.find("input", {"id": field}) or soup.find("input", {"name": field})
            if tag and tag.get("value"):
                tokens[field] = tag.get("value", "")
            else:
                tokens[field] = ""
        return tokens

    async def fetch_adangal(
        self,
        village_name: str,
        survey_number: str,
        district_name: str = "Visakhapatnam",
        mandal_name: str = "Anandapuram"
    ) -> Dict[str, Any]:
        """
        Executes end-to-end headless scrape of MeeBhoomi Adangal record.
        Negotiates ASP.NET session, solves captcha, posts query, and returns parsed record.
        """
        if self.mock_mode:
            logger.info(f"[Mock Mode] Generating simulated MeeBhoomi response for {village_name} #{survey_number}")
            return self._generate_simulated_adangal(village_name, survey_number, district_name, mandal_name)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._get_client() as client:
                    # 1. Initial GET to acquire session cookies and ASP.NET tokens
                    adangal_url = f"{self.base_url}/Adangal.aspx"
                    logger.info(f"Connecting to MeeBhoomi portal: {adangal_url} (Attempt {attempt}/{self.max_retries})")
                    resp = await client.get(adangal_url)
                    
                    if resp.status_code != 200:
                        raise MeeBhoomiPortalError(f"MeeBhoomi returned HTTP status {resp.status_code}")

                    tokens = self._extract_aspnet_tokens(resp.text)

                    # 2. Extract or fetch captcha image
                    captcha_img_bytes = await self._fetch_captcha_image(client, resp.text)
                    if not captcha_img_bytes:
                        raise MeeBhoomiPortalError("Unable to acquire captcha from portal")

                    # 3. Solve captcha via self-contained OpenCV solver
                    solved_captcha = self.captcha_solver.solve(captcha_img_bytes)
                    if not solved_captcha:
                        raise MeeBhoomiPortalError("Captcha solver returned empty string")

                    # 4. Construct ASP.NET postback payload
                    payload = {
                        "__VIEWSTATE": tokens.get("__VIEWSTATE", ""),
                        "__VIEWSTATEGENERATOR": tokens.get("__VIEWSTATEGENERATOR", ""),
                        "__EVENTVALIDATION": tokens.get("__EVENTVALIDATION", ""),
                        "txtDistrict": district_name,
                        "txtMandal": mandal_name,
                        "txtVillage": village_name,
                        "txtSurveyNo": str(survey_number),
                        "txtCaptcha": solved_captcha,
                        "btnSubmit": "Search"
                    }

                    # 5. POST query form
                    post_resp = await client.post(adangal_url, data=payload)
                    if post_resp.status_code != 200:
                        raise MeeBhoomiPortalError(f"Postback failed with status {post_resp.status_code}")

                    # 6. Parse response HTML
                    parsed = self.parser.parse_adangal_html(
                        post_resp.text, default_village=village_name, default_survey=str(survey_number)
                    )

                    if parsed.get("table_data_found"):
                        parsed["source_portal"] = "AP MeeBhoomi / Webland Revenue Portal (Live Verified)"
                        parsed["scrape_status"] = "SUCCESS"
                        return parsed
                    else:
                        # Check if captcha was reported invalid by portal
                        if "invalid captcha" in post_resp.text.lower() or "సరైన కాప్చా" in post_resp.text:
                            logger.warning(f"Captcha rejection on attempt {attempt}, retrying...")
                            continue
                        # Valid page but survey parcel not found
                        logger.warning(f"MeeBhoomi query returned empty table for {village_name} #{survey_number}")
                        break

            except Exception as e:
                logger.warning(f"MeeBhoomi connection attempt {attempt} failed: {e}")
                last_error = e

        raise MeeBhoomiPortalError(f"MeeBhoomi live query failed after {self.max_retries} attempts: {last_error}")

    async def _fetch_captcha_image(self, client: httpx.AsyncClient, page_html: str) -> Optional[bytes]:
        """Finds captcha image in page (inline base64 or CaptchaImage.ashx URL) and fetches bytes."""
        soup = BeautifulSoup(page_html, "html.parser")
        
        # Look for captcha image element
        img_tags = soup.find_all("img")
        for img in img_tags:
            src = img.get("src", "")
            img_id = (img.get("id") or "").lower()
            if "captcha" in src.lower() or "captcha" in img_id:
                if src.startswith("data:image"):
                    # Inline base64
                    clean_b64 = re.sub(r"^data:image/.+;base64,", "", src)
                    import base64
                    return base64.b64decode(clean_b64)
                else:
                    # External relative or absolute image link
                    full_url = src if src.startswith("http") else f"{self.base_url}/{src.lstrip('/')}"
                    c_resp = await client.get(full_url)
                    if c_resp.status_code == 200:
                        return c_resp.content

        # Fallback default captcha endpoint
        try:
            c_resp = await client.get(f"{self.base_url}/CaptchaImage.ashx")
            if c_resp.status_code == 200:
                return c_resp.content
        except Exception:
            pass

        return None

    def _generate_simulated_adangal(
        self, village_name: str, survey_number: str, district_name: str, mandal_name: str
    ) -> Dict[str, Any]:
        """Deterministic simulation for offline test suites and mock environments."""
        import hashlib
        seed = int(hashlib.md5(f"{village_name}_{survey_number}".encode()).hexdigest()[:8], 16)
        s_clean = str(survey_number).strip()

        if s_clean in ["81", "18", "110", "137"]:
            return {
                "pattadar_name": "Government of Andhra Pradesh (Assigned Land Non-Alienation)",
                "anubhavadar_name": "Sri M. Appa Rao (D-Form Beneficiary - Possession Only)",
                "khata_number": f"KHT-{1000 + (seed % 8999)}",
                "survey_number": s_clean,
                "village_name": village_name,
                "mandal_name": mandal_name,
                "district_name": district_name,
                "extent_acres": 4.50,
                "land_nature": "D-Form Assigned Land (Section 22A Non-Alienation)",
                "section_22a_prohibited": True,
                "title_dispute_flag": True,
                "source_portal": "AP MeeBhoomi / Webland Revenue Record (Simulated)",
                "title_risk_score": 95.0,
                "risk_level": "Critical Risk",
                "table_data_found": True,
                "scrape_status": "SUCCESS"
            }
        else:
            return {
                "pattadar_name": "Smt. P. Lakshmi Devi & Family",
                "anubhavadar_name": "Smt. P. Lakshmi Devi & Family",
                "khata_number": f"KHT-{1000 + (seed % 8999)}",
                "survey_number": s_clean,
                "village_name": village_name,
                "mandal_name": mandal_name,
                "district_name": district_name,
                "extent_acres": round(1.50 + (seed % 350) / 100.0, 2),
                "land_nature": "Rayituwari Patta (Clear Marketable Private Title)",
                "section_22a_prohibited": False,
                "title_dispute_flag": False,
                "source_portal": "AP MeeBhoomi / Webland Revenue Record (Simulated)",
                "title_risk_score": 8.0,
                "risk_level": "Low Risk",
                "table_data_found": True,
                "scrape_status": "SUCCESS"
            }
