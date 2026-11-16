"""
Comprehensive Test & Benchmark Suite for AP MeeBhoomi Headless Scraper Daemon
Tests:
1. Self-contained OpenCV Captcha OCR Solver & Synthetic Generation
2. Bilingual Telugu/English HTML Parser for Adangal and Section 22A
3. Session Negotiation and Client Error Resilience
4. Multi-tier Caching (In-Memory + Redis) and Verified Baseline Fallbacks
5. End-to-End Due Diligence Integration
"""

import sys
import os
import time
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.meebhoomi_scraper import (
    MeeBhoomiCaptchaSolver,
    MeeBhoomiParser,
    MeeBhoomiClient,
    MeeBhoomiScraperDaemon
)
from backend.app.services.meebhoomi_service import MeeBhoomiService
from backend.app.services.risk_scorer import RiskAssessmentEngine
from backend.app.models.schemas import DueDiligenceQuery

class TestMeeBhoomiScraperDaemon(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.solver = MeeBhoomiCaptchaSolver()
        cls.parser = MeeBhoomiParser()
        cls.client = MeeBhoomiClient(mock_mode=True)
        cls.daemon = MeeBhoomiScraperDaemon()
        cls.engine = RiskAssessmentEngine()

    # ----------------------------------------------------
    # 1. Captcha Solver Tests
    # ----------------------------------------------------
    def test_01_captcha_solver_synthetic_accuracy(self):
        """Test OCR solver against authentic synthetic AP MeeBhoomi captchas."""
        test_samples = ["14920", "83715", "29468", "60135", "71928"]
        solved_count = 0
        for text in test_samples:
            raw_bytes, truth = self.solver.generate_synthetic_captcha(text)
            predicted = self.solver.solve(raw_bytes)
            if predicted == truth:
                solved_count += 1
        
        accuracy = (solved_count / len(test_samples)) * 100.0
        print(f"\n[Test 1] Captcha Solver Accuracy: {solved_count}/{len(test_samples)} ({accuracy:.1f}%)")
        self.assertGreaterEqual(accuracy, 80.0, "Captcha solver accuracy should be at least 80%")

    def test_02_captcha_solver_base64_support(self):
        """Test solver with base64 data URI string."""
        raw_bytes, truth = self.solver.generate_synthetic_captcha("58203")
        import base64
        b64_str = f"data:image/png;base64,{base64.b64encode(raw_bytes).decode('utf-8')}"
        solved = self.solver.solve(b64_str)
        self.assertEqual(solved, "58203")

    # ----------------------------------------------------
    # 2. HTML Parser Tests
    # ----------------------------------------------------
    def test_03_parser_telugu_adangal(self):
        """Test parsing Telugu GridView Adangal records."""
        html = """
        <table id='grdAdangal'>
          <tr>
            <th>క్రమ సంఖ్య</th><th>జిల్లా</th><th>మండలం</th><th>గ్రామం</th>
            <th>ఖాతా నెంబరు</th><th>సర్వే నెంబరు</th><th>మొత్తం విస్తీర్ణం</th>
            <th>భూమి స్వభావం</th><th>పట్టాదారు పేరు</th><th>తండ్రి / భర్త పేరు</th>
            <th>అనుభవదారు పేరు</th>
          </tr>
          <tr>
            <td>1</td><td>Visakhapatnam</td><td>Anandapuram</td><td>Tarluvada</td>
            <td>1042</td><td>72</td><td>2.45</td>
            <td>రైతువారీ పట్టా</td><td>శ్రీమతి పి. లక్ష్మీ దేవి</td><td>శ్రీ పి. రామకృష్ణ</td>
            <td>శ్రీమతి పి. లక్ష్మీ దేవి</td>
          </tr>
        </table>
        """
        rec = self.parser.parse_adangal_html(html)
        self.assertTrue(rec["table_data_found"])
        self.assertEqual(rec["pattadar_name"], "శ్రీమతి పి. లక్ష్మీ దేవి")
        self.assertEqual(rec["anubhavadar_name"], "శ్రీమతి పి. లక్ష్మీ దేవి")
        self.assertEqual(rec["khata_number"], "1042")
        self.assertEqual(rec["extent_acres"], 2.45)
        self.assertIn("Rayituwari Patta", rec["land_nature"])
        self.assertFalse(rec["section_22a_prohibited"])
        self.assertFalse(rec["title_dispute_flag"])
        self.assertEqual(rec["risk_level"], "Low Risk")

    def test_04_parser_section_22a_prohibited(self):
        """Test detecting and classifying Section 22A Prohibited Property records."""
        html_22a = """
        <table id='grdSec22A'>
          <tr>
            <th>S.No</th><th>District</th><th>Mandal</th><th>Village</th><th>Survey No</th><th>Extent</th><th>22A Notification</th>
          </tr>
          <tr>
            <td>1</td><td>Visakhapatnam</td><td>Anandapuram</td><td>Tarluvada</td><td>81</td><td>4.50</td>
            <td>Section 22A(1)(a) Assigned Land Non-Alienation Act 9/77 G.O.Ms.No. 575 Revenue Dt 16-11-2018</td>
          </tr>
        </table>
        """
        res_22a = self.parser.parse_section_22a_html(html_22a, target_survey="81")
        self.assertTrue(res_22a["section_22a_prohibited"])
        self.assertIn("Section 22A(1)(a)", res_22a["prohibition_clause"])
        self.assertIn("G.O.Ms.No. 575", res_22a["gazette_reference"])

    def test_05_parser_pattadar_anubhavadar_discrepancy(self):
        """Test detecting mismatch between owner (Pattadar) and possessor (Anubhavadar)."""
        html_mismatch = """
        <table>
          <tr><td>పట్టాదారు పేరు:</td><td>Sri V. Ramachandra Murthy</td></tr>
          <tr><td>అనుభవదారుని పేరు:</td><td>Sri G. Venkata Rao</td></tr>
          <tr><td>ఖాతా సంఖ్య:</td><td>1890</td></tr>
          <tr><td>విస్తీర్ణం:</td><td>3.20</td></tr>
          <tr><td>భూమి స్వభావం:</td><td>పట్టా</td></tr>
        </table>
        """
        rec = self.parser.parse_adangal_html(html_mismatch)
        self.assertTrue(rec["table_data_found"])
        self.assertTrue(rec["title_dispute_flag"], "Dispute flag should be set for Pattadar != Anubhavadar")
        self.assertEqual(rec["risk_level"], "Moderate Risk")
        self.assertGreater(rec["title_risk_score"], 40.0)

    # ----------------------------------------------------
    # 3. Client & Session Tests
    # ----------------------------------------------------
    def test_06_client_aspnet_tokens(self):
        """Test ASP.NET WebForms ViewState token extraction."""
        html = """
        <html><body>
          <input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="wEPDwULLTE1MzMzNzExMzgPZBYCAgEPZBYCZg8WAh4EVGV4dAUH" />
          <input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="/wEdAAM12345" />
          <input type="hidden" name="__VIEWSTATEGENERATOR" id="__VIEWSTATEGENERATOR" value="B8B9B123" />
        </body></html>
        """
        tokens = self.client._extract_aspnet_tokens(html)
        self.assertIn("__VIEWSTATE", tokens)
        self.assertEqual(tokens["__VIEWSTATEGENERATOR"], "B8B9B123")

    # ----------------------------------------------------
    # 4. Multi-tier Daemon & Cache Tests
    # ----------------------------------------------------
    def test_07_daemon_cache_hit_and_fallback(self):
        """Test 3-tier hierarchy: Baseline Fallback -> Cache Hit with latency telemetry."""
        # Query 1: Cold start (Baseline Fallback)
        t0 = time.time()
        res1 = self.daemon.query_title_sync(
            village_name="Tarluvada", survey_number="72", district_name="Visakhapatnam"
        )
        self.assertIn(res1["provenance"], ["LIVE_SCRAPER", "BASELINE_FALLBACK", "CACHE_HIT"])
        self.assertEqual(res1["survey_number"], "72")
        self.assertFalse(res1["section_22a_prohibited"])

        # Query 2: Immediate Cache Hit
        res2 = self.daemon.query_title_sync(
            village_name="Tarluvada", survey_number="72", district_name="Visakhapatnam"
        )
        self.assertEqual(res2["provenance"], "CACHE_HIT")
        self.assertLess(res2["latency_ms"], 10.0, "Cache hit latency should be sub-10ms")

    def test_08_daemon_prohibited_parcel(self):
        """Test daemon correctly flags Section 22A prohibited survey parcel."""
        res_proh = self.daemon.query_title_sync(
            village_name="Tarluvada", survey_number="81", district_name="Visakhapatnam"
        )
        self.assertTrue(res_proh["section_22a_prohibited"])
        self.assertEqual(res_proh["risk_level"], "Critical Risk")
        self.assertGreaterEqual(res_proh["title_risk_score"], 90.0)

    def test_09_daemon_warm_village_cache(self):
        """Test pre-fetching and cache warming."""
        count = self.daemon.warm_village_cache(
            village_name="Gambheeram",
            survey_numbers=["10", "11", "12", "13", "14"]
        )
        self.assertGreaterEqual(count, 0)
        # Immediate read should be a cache hit
        res = self.daemon.query_title_sync("Gambheeram", "10")
        self.assertEqual(res["provenance"], "CACHE_HIT")

    # ----------------------------------------------------
    # 5. Full End-to-End Due Diligence Integration
    # ----------------------------------------------------
    def test_10_end_to_end_due_diligence_pipeline(self):
        """Test complete pipeline from query -> title audit -> risk scoring -> SHA-256 digital signature."""
        query = DueDiligenceQuery(
            district="Visakhapatnam",
            mandal="Anandapuram",
            village_name="Tarluvada",
            survey_number="72",
            purpose="Commercial IT Park"
        )
        result = self.engine.run_due_diligence(query)
        self.assertIsNotNone(result.report_id)
        self.assertIsNotNone(result.report_hash)
        self.assertEqual(len(result.report_hash), 64, "Digital signature must be SHA-256 (64 hex characters)")
        self.assertEqual(result.title_legal.risk_level, "Low Risk")
        self.assertFalse(result.title_legal.section_22a_prohibited)
        print(f"\n[Test 10] E2E Result: {result.report_id} | Hash: {result.report_hash[:16]}... | Grade: {result.overall_risk_grade}")

if __name__ == "__main__":
    unittest.main()
