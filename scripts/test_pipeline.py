import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

from app.models.schemas import DueDiligenceQuery
from app.services.risk_scorer import RiskAssessmentEngine
from app.services.report_generator import DueDiligenceReportGenerator

def test_pipeline():
    print("Initializing RiskAssessmentEngine...")
    engine = RiskAssessmentEngine()
    
    # Test case 1: Tarluvada 72 (Approved LP, Clean Private Patta)
    print("\n--- TEST CASE 1: Tarluvada Survey 72 (Clean Approved LP) ---")
    q1 = DueDiligenceQuery(
        district="Visakhapatnam",
        mandal="Anandapuram",
        village_name="Tarluvada",
        survey_number="72",
        purpose="Residential Gated Community Development"
    )
    res1 = engine.run_due_diligence(q1)
    print(f"Report ID: {res1.report_id}")
    print(f"Overall Score: {res1.overall_risk_score} -> Grade {res1.overall_risk_grade} ({res1.risk_status})")
    print(f"Zoning: {res1.zoning.zone_name}")
    print(f"Title: {res1.title_legal.land_nature} (22A Prohibited: {res1.title_legal.section_22a_prohibited})")
    print(f"Layout: {res1.layout.layout_status} (LP: {res1.layout.lp_number})")
    print(f"Flood: {res1.terrain_flood.flood_hazard_category}")
    
    # Test case 2: Tarluvada 81 (Government Assigned / Section 22A Prohibited)
    print("\n--- TEST CASE 2: Tarluvada Survey 81 (Section 22A Prohibited) ---")
    q2 = DueDiligenceQuery(
        district="Visakhapatnam",
        mandal="Anandapuram",
        village_name="Tarluvada",
        survey_number="81",
        purpose="Commercial Real Estate Purchase"
    )
    res2 = engine.run_due_diligence(q2)
    print(f"Report ID: {res2.report_id}")
    print(f"Overall Score: {res2.overall_risk_score} -> Grade {res2.overall_risk_grade} ({res2.risk_status})")
    print(f"Title: {res2.title_legal.land_nature} (22A Prohibited: {res2.title_legal.section_22a_prohibited})")
    print(f"Red Flags: {res2.red_flag_alerts}")
    
    # Test case 3: Tarluvada 64 (Unauthorized Layout)
    print("\n--- TEST CASE 3: Tarluvada Survey 64 (Unauthorized Layout) ---")
    q3 = DueDiligenceQuery(
        district="Visakhapatnam",
        mandal="Anandapuram",
        village_name="Tarluvada",
        survey_number="64",
        purpose="Villa Subdivision"
    )
    res3 = engine.run_due_diligence(q3)
    print(f"Report ID: {res3.report_id}")
    print(f"Overall Score: {res3.overall_risk_score} -> Grade {res3.overall_risk_grade} ({res3.risk_status})")
    print(f"Layout: {res3.layout.layout_status} (Is Unauthorized: {res3.layout.is_unauthorized_list})")
    
    # Generate 5-Page PDF for Case 1
    print("\nGenerating 5-Page PDF Report for Case 1 with QR Code & SHA-256 Digest...")
    pdf_gen = DueDiligenceReportGenerator()
    pdf_path = pdf_gen.generate_pdf(res1)
    print(f"PDF successfully generated at: {pdf_path}")
    print(f"File size: {os.path.getsize(pdf_path)} bytes")
    print(f"Digital SHA-256 Digest: {res1.report_hash}")
    print(f"Public Verification URL: {res1.verification_url}")

if __name__ == "__main__":
    test_pipeline()
