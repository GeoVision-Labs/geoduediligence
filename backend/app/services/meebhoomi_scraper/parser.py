import re
import logging
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class MeeBhoomiParser:
    """
    Parser for Andhra Pradesh MeeBhoomi revenue records (Adangal/Pahani, 1B ROR, and Section 22A).
    Supports bilingual extraction (Telugu Unicode & English), GridView table structures,
    two-column key-value tables, and Section 22A statutory prohibition detection.
    """

    TELUGU_TO_ENGLISH_MAP = {
        # Land Nature
        "రైతువారీ పట్టా": "Rayituwari Patta (Clear Marketable Private Title)",
        "పట్టా": "Private Patta Land",
        "డి-ఫారం": "D-Form Assigned Land (Section 22A Non-Alienation)",
        "అసైన్డ్": "Government Assigned Land (POT Act 9/77)",
        "పోరంబోకు": "Government Poramboke Land",
        "దేవాదాయ": "Endowments / Temple Land (Section 22A(1)(c))",
        "వక్ఫ్": "Waqf Board Property (Section 22A(1)(c))",
        "ఇనాం": "Inam Abolition Regulated Land",
        "గ్రామ కంఠం": "Grama Kantam (Village Habitation Common Land)",
        "కాల్బాట": "Public Pathway / Cart Track (Poramboke)",
        "వాగు": "Waterbody / Stream Nala (Statutory Buffer Non-Buildable)",
        "చెరువు": "Tank / Lake Waterbody (Absolute Non-Development Zone)",
        "కొండ": "Government Hill / Forest Parcel"
    }

    def __init__(self):
        pass

    def clean_text(self, text: Optional[str]) -> str:
        """Strips HTML artifacts, zero-width characters, and normalizes spacing."""
        if not text:
            return ""
        # Remove zero-width spaces, non-breaking spaces, and excess whitespace
        cleaned = re.sub(r"[\u200b\u200c\u200d\uFEFF\xa0]", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def parse_extent(self, extent_str: Optional[str]) -> float:
        """
        Parses Telugu/English extent notations into float acres:
        e.g., '2.45', '2-45', '2 Ac. 45 Cts', '2.45 ఎకరాలు', '0.75'
        """
        if not extent_str:
            return 0.0
        cleaned = self.clean_text(str(extent_str))
        # Match standard numeric decimal (e.g. 2.45)
        m = re.search(r"(\d+)(?:[.\-](\d+))?", cleaned)
        if m:
            whole = m.group(1)
            frac = m.group(2)
            if frac:
                return float(f"{whole}.{frac}")
            return float(whole)
        return 0.0

    def parse_adangal_html(self, html_content: str, default_village: str = "", default_survey: str = "") -> Dict[str, Any]:
        """
        Parses MeeBhoomi Adangal / Pahani HTML output.
        Handles both tabular GridView layout and key-value card structures.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Default fallbacks
        record: Dict[str, Any] = {
            "pattadar_name": "",
            "father_husband_name": "",
            "anubhavadar_name": "",
            "khata_number": "",
            "survey_number": default_survey,
            "village_name": default_village,
            "mandal_name": "",
            "district_name": "",
            "extent_acres": 0.0,
            "land_nature": "Private Patta Land",
            "right_type": "Pattadar",
            "section_22a_prohibited": False,
            "title_dispute_flag": False,
            "raw_remarks": "",
            "table_data_found": False
        }

        # 1. Try finding tabular GridView (tables with >= 3 columns or explicit <th>)
        tables = soup.find_all("table")
        for tbl in tables:
            rows = tbl.find_all("tr")
            if not rows:
                continue

            header_cells = rows[0].find_all(["th", "td"])
            # GridView requires at least 3 columns or explicit <th> tags in row 0
            has_th = bool(rows[0].find_all("th"))
            if len(header_cells) < 3 and not has_th:
                continue

            header_texts = [self.clean_text(th.text).lower() for th in header_cells]

            # Check if this table has Adangal columns
            is_adangal_table = any(
                k in " ".join(header_texts)
                for k in ["పట్టాదారు", "pattadar", "అనుభవదారు", "anubhavadar", "ఖాతా", "khata", "సర్వే", "survey"]
            )

            if is_adangal_table and len(rows) > 1:
                col_map: Dict[str, int] = {}
                for idx, h in enumerate(header_texts):
                    if any(x in h for x in ["పట్టాదారు పేరు", "pattadar name", "pattadar"]):
                        col_map["pattadar"] = idx
                    elif any(x in h for x in ["తండ్రి", "భర్త", "father", "husband"]):
                        col_map["father"] = idx
                    elif any(x in h for x in ["అనుభవదారు", "anubhavadar"]):
                        col_map["anubhavadar"] = idx
                    elif any(x in h for x in ["ఖాతా", "khata"]):
                        col_map["khata"] = idx
                    elif any(x in h for x in ["సర్వే", "survey"]):
                        col_map["survey"] = idx
                    elif any(x in h for x in ["విస్తీర్ణం", "extent", "area"]):
                        col_map["extent"] = idx
                    elif any(x in h for x in ["స్వభావం", "రకం", "nature", "classification"]):
                        col_map["nature"] = idx
                    elif any(x in h for x in ["హక్కు", "right", "tenure"]):
                        col_map["right"] = idx
                    elif any(x in h for x in ["రిమార్కులు", "remarks", "dispute", "వివాదాలు"]):
                        col_map["remarks"] = idx

                # Process the first data row
                data_row = rows[1].find_all("td")
                if len(data_row) >= 2:
                    record["table_data_found"] = True
                    if "pattadar" in col_map and col_map["pattadar"] < len(data_row):
                        record["pattadar_name"] = self.clean_text(data_row[col_map["pattadar"]].text)
                    if "father" in col_map and col_map["father"] < len(data_row):
                        record["father_husband_name"] = self.clean_text(data_row[col_map["father"]].text)
                    if "anubhavadar" in col_map and col_map["anubhavadar"] < len(data_row):
                        record["anubhavadar_name"] = self.clean_text(data_row[col_map["anubhavadar"]].text)
                    if "khata" in col_map and col_map["khata"] < len(data_row):
                        record["khata_number"] = self.clean_text(data_row[col_map["khata"]].text)
                    if "survey" in col_map and col_map["survey"] < len(data_row):
                        record["survey_number"] = self.clean_text(data_row[col_map["survey"]].text) or default_survey
                    if "extent" in col_map and col_map["extent"] < len(data_row):
                        record["extent_acres"] = self.parse_extent(data_row[col_map["extent"]].text)
                    if "nature" in col_map and col_map["nature"] < len(data_row):
                        raw_nature = self.clean_text(data_row[col_map["nature"]].text)
                        record["land_nature"] = self._standardize_land_nature(raw_nature)
                    if "right" in col_map and col_map["right"] < len(data_row):
                        record["right_type"] = self.clean_text(data_row[col_map["right"]].text)
                    if "remarks" in col_map and col_map["remarks"] < len(data_row):
                        record["raw_remarks"] = self.clean_text(data_row[col_map["remarks"]].text)
                break

        # 2. Check two-column key-value tables if GridView was not found or incomplete
        if not record["table_data_found"] or not record["pattadar_name"]:
            for tr in soup.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) == 2:
                    k = self.clean_text(cells[0].text).lower()
                    v = self.clean_text(cells[1].text)
                    if any(x in k for x in ["పట్టాదారు పేరు", "pattadar name"]):
                        record["pattadar_name"] = v
                        record["table_data_found"] = True
                    elif any(x in k for x in ["అనుభవదారుని పేరు", "anubhavadar name"]):
                        record["anubhavadar_name"] = v
                        record["table_data_found"] = True
                    elif any(x in k for x in ["ఖాతా సంఖ్య", "khata no", "khata number"]):
                        record["khata_number"] = v
                    elif any(x in k for x in ["విస్తీర్ణం", "extent", "total extent"]):
                        record["extent_acres"] = self.parse_extent(v)
                    elif any(x in k for x in ["భూమి స్వభావం", "భూమి రకం", "land nature"]):
                        record["land_nature"] = self._standardize_land_nature(v)
                    elif any(x in k for x in ["సర్వే నెం", "survey no"]):
                        record["survey_number"] = v

        # If Anubhavadar was not explicitly given, default to Pattadar
        if record["pattadar_name"] and not record["anubhavadar_name"]:
            record["anubhavadar_name"] = record["pattadar_name"]

        # 3. Analyze Discrepancies and Risk
        self._audit_legal_risk(record)
        return record

    def parse_section_22a_html(self, html_content: str, target_survey: str = "") -> Dict[str, Any]:
        """
        Parses MeeBhoomi / Webland Section 22A Prohibited Property Register output.
        Extracts prohibition category (22A(1)(a)-(e)), gazette notifications, and prohibited extent.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        is_prohibited = False
        prohibition_clause = ""
        gazette_ref = ""
        remarks = ""
        prohibited_extent = 0.0

        tables = soup.find_all("table")
        for tbl in tables:
            rows = tbl.find_all("tr")
            if len(rows) < 2:
                continue

            headers = [self.clean_text(th.text).lower() for th in rows[0].find_all(["th", "td"])]
            has_22a_cols = any(x in " ".join(headers) for x in ["22a", "నిషేధిత", "prohibited", "notification", "గెజిట్"])

            if has_22a_cols:
                for r in rows[1:]:
                    tds = r.find_all("td")
                    row_text = " ".join([self.clean_text(td.text) for td in tds])
                    
                    # If target survey specified, ensure row matches
                    if target_survey and target_survey not in row_text:
                        continue

                    # Found prohibited property record
                    is_prohibited = True
                    # Check clauses
                    if "22a(1)(a)" in row_text.lower() or "assigned" in row_text.lower() or "డి-ఫారం" in row_text:
                        prohibition_clause = "Section 22A(1)(a) - Assigned Land (AP Non-Alienation Act 9/77)"
                    elif "22a(1)(b)" in row_text.lower() or "government" in row_text.lower() or "పోరంబోకు" in row_text:
                        prohibition_clause = "Section 22A(1)(b) - State / Central Government Property"
                    elif "22a(1)(c)" in row_text.lower() or "endowment" in row_text.lower() or "waqf" in row_text or "దేవాదాయ" in row_text:
                        prohibition_clause = "Section 22A(1)(c) - Religious / Endowments / Waqf Board Land"
                    elif "22a(1)(d)" in row_text.lower() or "ceiling" in row_text.lower():
                        prohibition_clause = "Section 22A(1)(d) - Surplus Land under Urban/Agri Ceiling Act"
                    elif "22a(1)(e)" in row_text.lower() or "court" in row_text.lower() or "వివాదం" in row_text:
                        prohibition_clause = "Section 22A(1)(e) - Court Injunction / Attachment Order"
                    else:
                        prohibition_clause = "Section 22A AP Registration Act Prohibited Property"

                    gazette_match = re.search(r"(?:G\.O\.Ms\.No\.|Gazette|గెజిట్)[\w\s\.\-\/]+", row_text, re.IGNORECASE)
                    if gazette_match:
                        gazette_ref = gazette_match.group(0).strip()
                    remarks = row_text
                    break

        return {
            "section_22a_prohibited": is_prohibited,
            "prohibition_clause": prohibition_clause,
            "gazette_reference": gazette_ref,
            "remarks": remarks
        }

    def _standardize_land_nature(self, raw: str) -> str:
        """Translates and maps Telugu/English revenue land classifications."""
        cleaned = self.clean_text(raw)
        for telugu_kw, english_desc in self.TELUGU_TO_ENGLISH_MAP.items():
            if telugu_kw in cleaned:
                return english_desc
        # English fallbacks
        lower = cleaned.lower()
        if "assigned" in lower or "d-form" in lower or "pot" in lower:
            return "D-Form Assigned Land (Section 22A Non-Alienation)"
        if "poramboke" in lower or "gayalu" in lower:
            return "Government Poramboke Land"
        if "waqf" in lower or "wakf" in lower:
            return "Waqf Board Property (Section 22A(1)(c))"
        if "endowment" in lower or "temple" in lower or "devasthanam" in lower:
            return "Endowments / Temple Land (Section 22A(1)(c))"
        if "patta" in lower or "rayituwari" in lower:
            return "Rayituwari Patta (Clear Marketable Private Title)"
        return cleaned or "Private Patta Land"

    def _audit_legal_risk(self, record: Dict[str, Any]):
        """
        Calculates AP statutory title risk score and sets dispute/prohibition flags.
        """
        nature = record.get("land_nature", "")
        pattadar = record.get("pattadar_name", "").strip().lower()
        anubhavadar = record.get("anubhavadar_name", "").strip().lower()

        # Check for Section 22A prohibited flags in land nature
        if any(x in nature.lower() for x in ["assigned", "d-form", "poramboke", "waqf", "endowment", "22a"]):
            record["section_22a_prohibited"] = True
            record["title_dispute_flag"] = True
            record["title_risk_score"] = 95.0
            record["risk_level"] = "Critical Risk"
            return

        # Check Pattadar vs Anubhavadar mismatch (Possession discrepancy / tenancy / un-mutated agreement)
        if pattadar and anubhavadar and pattadar != anubhavadar:
            # Check if one is a substring of another (e.g. "Smt P. Lakshmi" vs "P. Lakshmi Devi")
            name_similarity = (pattadar in anubhavadar) or (anubhavadar in pattadar)
            if not name_similarity:
                record["title_dispute_flag"] = True
                record["title_risk_score"] = 52.0
                record["risk_level"] = "Moderate Risk"
                record["land_nature"] = f"{record.get('land_nature', 'Private Patta')} (Pattadar / Possessor Mismatch)"
                return

        # Default: Clean Patta
        record["section_22a_prohibited"] = False
        record["title_dispute_flag"] = False
        record["title_risk_score"] = 8.0
        record["risk_level"] = "Low Risk"
