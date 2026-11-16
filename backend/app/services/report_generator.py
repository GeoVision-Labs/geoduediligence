import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, KeepTogether
)
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from ..models.schemas import DueDiligenceResult

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (Top)
        self.drawString(54, 750, "GEODUEDILIGENCE | Land Intelligence & Spatial Due Diligence Platform")
        self.drawRightString(558, 750, "CONFIDENTIAL & PROPRIETARY")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        
        # Footer (Bottom)
        self.line(54, 45, 558, 45)
        self.setFont("Helvetica", 8)
        self.drawString(54, 32, "VMRDA Master Plan 2041 Spatial Audit • MeeBhoomi Title Verification • Topo Flood Risk")
        self.drawRightString(558, 32, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


class DueDiligenceReportGenerator:
    def __init__(self, output_dir: str = None):
        if output_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            output_dir = os.path.join(base_dir, "data", "sample_reports")
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.title_style = ParagraphStyle(
            "DocTitle",
            parent=self.styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6
        )
        self.subtitle_style = ParagraphStyle(
            "DocSubTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14
        )
        self.section_h1 = ParagraphStyle(
            "SectionH1",
            parent=self.styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=10,
            spaceAfter=8
        )
        self.body_style = ParagraphStyle(
            "BodyDark",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155")
        )
        self.alert_style = ParagraphStyle(
            "AlertText",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#991B1B")
        )
        self.positive_style = ParagraphStyle(
            "PositiveText",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#166534")
        )

    def _create_qr_code(self, url: str, size: float = 75) -> Drawing:
        widget = qr.QrCodeWidget(url)
        bounds = widget.getBounds()
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
        d.add(widget)
        return d

    def generate_pdf(self, result: DueDiligenceResult) -> str:
        filename = f"Due_Diligence_Report_{result.report_id}.pdf"
        filepath = os.path.join(self.output_dir, filename)
        
        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54
        )
        
        story = []
        
        # =========================================================================
        # PAGE 1: EXECUTIVE DUE DILIGENCE SUMMARY & RISK SCORECARD
        # =========================================================================
        story.append(Paragraph("LAND INTELLIGENCE & DUE DILIGENCE REPORT", self.title_style))
        story.append(Paragraph(f"Autonomous Pre-Acquisition Risk Audit | VMRDA Region 2041 | Report #{result.report_id}", self.subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=12))
        
        # Meta parcel info
        p_info = result.target_parcel
        meta_data = [
            [Paragraph("<b>Target Village:</b>", self.body_style), Paragraph(f"<b>{p_info['village_name']}</b>", self.body_style),
             Paragraph("<b>Survey Number:</b>", self.body_style), Paragraph(f"<b>{p_info['survey_number']}</b>", self.body_style)],
            [Paragraph("<b>District:</b>", self.body_style), Paragraph(p_info['district'], self.body_style),
             Paragraph("<b>Mandal:</b>", self.body_style), Paragraph(p_info['mandal'], self.body_style)],
            [Paragraph("<b>GPS Coordinates:</b>", self.body_style), Paragraph(f"{result.coordinates['latitude']}, {result.coordinates['longitude']}", self.body_style),
             Paragraph("<b>Audit Timestamp:</b>", self.body_style), Paragraph(result.generated_at, self.body_style)],
            [Paragraph("<b>Intended Development:</b>", self.body_style), Paragraph(p_info['purpose'], self.body_style),
             Paragraph("<b>Master Plan Ref:</b>", self.body_style), Paragraph(p_info['pdf_part_reference'], self.body_style)]
        ]
        meta_table = Table(meta_data, colWidths=[110, 142, 110, 142])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#E2E8F0")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 14))
        
        # Risk Scorecard Box
        grade_color = "#16A34A" if result.overall_risk_grade in ["A+", "A"] else ("#D97706" if result.overall_risk_grade == "B" else "#DC2626")
        score_data = [
            [
                Paragraph(f"<font size='28' color='{grade_color}'><b>GRADE {result.overall_risk_grade}</b></font><br/><font size='10' color='#64748B'>Risk Index: <b>{result.overall_risk_score} / 100</b></font>", self.body_style),
                Paragraph(f"<font size='12' color='{grade_color}'><b>{result.risk_status}</b></font><br/><font size='9' color='#334155'>{result.summary_verdict}</font>", self.body_style)
            ]
        ]
        score_table = Table(score_data, colWidths=[150, 354])
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
            ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor(grade_color)),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 14))
        
        # Red Flag & Positive Alerts
        if result.red_flag_alerts:
            story.append(Paragraph("<b>CRITICAL RISK ALERTS & TITLE ENCUMBRANCES</b>", ParagraphStyle('H', parent=self.section_h1, fontSize=11, textColor=colors.HexColor("#991B1B"))))
            alert_rows = [[Paragraph(f"• {a}", self.alert_style)] for a in result.red_flag_alerts]
            alert_table = Table(alert_rows, colWidths=[504])
            alert_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEF2F2")),
                ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FCA5A5")),
                ('PADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(alert_table)
            story.append(Spacer(1, 10))
            
        story.append(Paragraph("<b>KEY CLEARANCES & POSITIVE DUE DILIGENCE SIGNALS</b>", ParagraphStyle('H2', parent=self.section_h1, fontSize=11, textColor=colors.HexColor("#166534"))))
        pos_rows = [[Paragraph(f"✓ {p}", self.positive_style)] for p in result.positive_indicators]
        pos_table = Table(pos_rows, colWidths=[504])
        pos_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#86EFAC")),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(pos_table)
        story.append(Spacer(1, 14))
        
        # Component Score Breakdown Table
        story.append(Paragraph("<b>DUE DILIGENCE PILLAR SCORECARD</b>", self.section_h1))
        pillars = [
            ["Diligence Pillar", "Governing Data Layer", "Pillar Risk Score", "Compliance Status"],
            ["1. Zoning & Master Plan", "VMRDA 2041 Polygons (Map 4)", f"{result.zoning.zoning_risk_score} / 100", result.zoning.risk_level],
            ["2. Legal Title & Encumbrance", "AP MeeBhoomi / 22A Registry", f"{result.title_legal.title_risk_score} / 100", result.title_legal.risk_level],
            ["3. Layout Legitimacy", "VMRDA LP / U-Layout Blacklist", f"{result.layout.layout_risk_score} / 100", result.layout.risk_level],
            ["4. Topographical Flood Risk", "Copernicus DEM 30m / Hydrology", f"{result.terrain_flood.climate_risk_score} / 100", result.terrain_flood.risk_level]
        ]
        p_table = Table(pillars, colWidths=[140, 164, 100, 100])
        p_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1E3A8A")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(p_table)
        story.append(PageBreak())
        
        # =========================================================================
        # PAGE 2: VMRDA MASTER PLAN 2041 ZONING COMPLIANCE
        # =========================================================================
        story.append(Paragraph("LAYER 1: VMRDA MASTER PLAN 2041 ZONING AUDIT", self.title_style))
        story.append(Paragraph("Spatial Overlay & Statutory Land Use Classification | Visakhapatnam Metropolitan Region", self.subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=14))
        
        z = result.zoning
        z_meta = [
            [Paragraph("<b>Zoning Classification:</b>", self.body_style), Paragraph(f"<b>{z.zone_name}</b>", self.body_style)],
            [Paragraph("<b>Statutory Zone Code:</b>", self.body_style), Paragraph(f"<b>{z.zone_code}</b>", self.body_style)],
            [Paragraph("<b>Master Plan Map Reference:</b>", self.body_style), Paragraph(z.master_plan_reference, self.body_style)],
            [Paragraph("<b>Road Widening / Reservation:</b>", self.body_style), Paragraph(z.road_widening_reservation, self.body_style)],
            [Paragraph("<b>Zoning Risk Assessment:</b>", self.body_style), Paragraph(f"<b>{z.zoning_risk_score} / 100 ({z.risk_level})</b>", self.body_style)]
        ]
        zt = Table(z_meta, colWidths=[160, 344])
        zt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(zt)
        story.append(Spacer(1, 14))
        
        story.append(Paragraph("<b>Permitted Statutory Uses:</b>", self.section_h1))
        perm_items = [[Paragraph(f"• {u}", self.body_style)] for u in z.permitted_uses]
        perm_t = Table(perm_items, colWidths=[504])
        perm_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BBF7D0")),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(perm_t)
        story.append(Spacer(1, 12))
        
        story.append(Paragraph("<b>Restricted / Prohibited Commercial Uses:</b>", self.section_h1))
        rest_items = [[Paragraph(f"✕ {u}", self.body_style)] for u in z.restricted_uses]
        rest_t = Table(rest_items, colWidths=[504])
        rest_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFF7ED")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FFEDD5")),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(rest_t)
        story.append(Spacer(1, 14))
        
        story.append(Paragraph("<b>Master Plan 2041 Spatial Notes:</b>", self.section_h1))
        notes_p = (
            "Under the Andhra Pradesh Metropolitan Region and Urban Development Authorities Act (APMR&UDA Act 2016), "
            "development permissions are granted strictly in adherence to the notified Master Plan 2041. "
            "Any construction or layout subdivision must conform to statutory Floor Area Ratio (FAR) caps, mandatory setback buffers, "
            "and true north alignment (-35° printing adjustment). Plots affected by proposed Master Plan Road widening reservations "
            "are subject to Transferable Development Rights (TDR) surrenders upon building approval."
        )
        story.append(Paragraph(notes_p, self.body_style))
        story.append(PageBreak())
        
        # =========================================================================
        # PAGE 3: TITLE, TENURE & AP MEEBHOOMI AUDIT
        # =========================================================================
        story.append(Paragraph("LAYER 2: TITLE & AP MEEBHOOMI RECORD AUDIT", self.title_style))
        story.append(Paragraph("Ownership Discrepancies, Adangal, 1B Records & Section 22A Prohibited Listings", self.subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=14))
        
        t = result.title_legal
        t_meta = [
            [Paragraph("<b>Pattadar (Legal Owner):</b>", self.body_style), Paragraph(f"<b>{t.pattadar_name}</b>", self.body_style)],
            [Paragraph("<b>Anubhavadar (Possessor):</b>", self.body_style), Paragraph(f"<b>{t.anubhavadar_name}</b>", self.body_style)],
            [Paragraph("<b>Khata Account Number:</b>", self.body_style), Paragraph(t.khata_number, self.body_style)],
            [Paragraph("<b>Registered Extent (Acres):</b>", self.body_style), Paragraph(f"{t.extent_acres} Acres", self.body_style)],
            [Paragraph("<b>Land Classification Nature:</b>", self.body_style), Paragraph(f"<b>{t.land_nature}</b>", self.body_style)],
            [Paragraph("<b>Section 22A Prohibited Status:</b>", self.body_style), Paragraph(f"<font color='{'#DC2626' if t.section_22a_prohibited else '#16A34A'}'><b>{'PROHIBITED (22A RESTRICTED)' if t.section_22a_prohibited else 'CLEAR (NOT ON PROHIBITED LIST)'}</b></font>", self.body_style)],
            [Paragraph("<b>Title Dispute / Mismatch Flag:</b>", self.body_style), Paragraph(f"<b>{'DISPUTE / MISMATCH FLAGGED' if t.title_dispute_flag else 'CLEAN OWNERSHIP CHAIN'}</b>", self.body_style)],
            [Paragraph("<b>Title Risk Score:</b>", self.body_style), Paragraph(f"<b>{t.title_risk_score} / 100 ({t.risk_level})</b>", self.body_style)]
        ]
        tt = Table(t_meta, colWidths=[180, 324])
        tt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(tt)
        story.append(Spacer(1, 14))
        
        story.append(Paragraph("<b>Section 22A AP Registration Act Legal Advisory:</b>", self.section_h1))
        adv_p = (
            "Section 22A of the Registration Act, 1908 (AP Amendment) explicitly prohibits registration of documents relating to: "
            "(a) Land assigned by the State Govt to landless poor (D-Form Pattas); (b) Properties belonging to the State or Central Govt; "
            "(c) Properties belonging to religious or charitable endowments / Waqf institutions; and (d) Ceiling surplus lands. "
            f"Current automated query indicates that this parcel has <b>{'VIOLATIONS under Section 22A' if t.section_22a_prohibited else 'ZERO prohibited entries'}</b>. "
            "Buyers are advised to secure a physical non-encumbrance certificate (EC) from the Sub-Registrar's Office (SRO) for 30 years prior to financial disbursement."
        )
        story.append(Paragraph(adv_p, self.body_style))
        story.append(PageBreak())
        
        # =========================================================================
        # PAGE 4: LAYOUT LEGITIMACY & VMRDA LP VALIDATION
        # =========================================================================
        story.append(Paragraph("LAYER 3: VMRDA LAYOUT APPROVAL AUDIT", self.title_style))
        story.append(Paragraph("Layout Permissions (LP Numbers), Unauthorized Registry & Regularisation Eligibility", self.subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=14))
        
        l = result.layout
        l_meta = [
            [Paragraph("<b>Layout Status Classification:</b>", self.body_style), Paragraph(f"<b>{l.layout_status}</b>", self.body_style)],
            [Paragraph("<b>VMRDA LP Number:</b>", self.body_style), Paragraph(l.lp_number if l.lp_number else "N/A (Unplatted / No LP Registered)", self.body_style)],
            [Paragraph("<b>Approval Year:</b>", self.body_style), Paragraph(str(l.approval_year) if l.approval_year else "N/A", self.body_style)],
            [Paragraph("<b>Unauthorized Layouts Blacklist:</b>", self.body_style), Paragraph(f"<font color='{'#DC2626' if l.is_unauthorized_list else '#16A34A'}'><b>{'FLAGGED UNAUTHORIZED BY VMRDA' if l.is_unauthorized_list else 'CLEAN (NOT BLACKLISTED)'}</b></font>", self.body_style)],
            [Paragraph("<b>Layout Regularisation (LRS):</b>", self.body_style), Paragraph("Eligible under AP LRS Rules" if l.lrs_eligible else "Not Applicable", self.body_style)],
            [Paragraph("<b>Civic Utilities Sanction Status:</b>", self.body_style), Paragraph(l.civic_utility_clearance, self.body_style)],
            [Paragraph("<b>Layout Risk Score:</b>", self.body_style), Paragraph(f"<b>{l.layout_risk_score} / 100 ({l.risk_level})</b>", self.body_style)]
        ]
        lt = Table(l_meta, colWidths=[180, 324])
        lt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(lt)
        story.append(Spacer(1, 14))
        
        story.append(Paragraph("<b>Enforcement & Demolition Risk Notice:</b>", self.section_h1))
        enf_p = (
            "VMRDA exercises strict municipal enforcement across the Visakhapatnam Metropolitan Region. "
            "Selling unapproved plots without an authentic Layout Permission (LP No.) attracts penal prosecution under the APMR&UDA Act 2016. "
            "GVMC and Eastern Power Distribution Company of AP (APEPDCL) are legally prohibited from granting building plans, "
            "water connections, or commercial power meters to unapproved layout subdivisions unless penal regularization compounding fee is cleared."
        )
        story.append(Paragraph(enf_p, self.body_style))
        story.append(PageBreak())
        
        # =========================================================================
        # PAGE 5: TOPOGRAPHY, SLOPE & FLOOD RESILIENCE ANALYSIS
        # =========================================================================
        story.append(Paragraph("LAYER 4: TOPOGRAPHICAL & FLOOD RESILIENCE", self.title_style))
        story.append(Paragraph("Digital Elevation Model (DEM), Natural Drainage & Climate Hazard Assessment", self.subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=14))
        
        f = result.terrain_flood
        f_meta = [
            [Paragraph("<b>Elevation Above MSL:</b>", self.body_style), Paragraph(f"<b>{f.elevation_meters} Meters</b>", self.body_style)],
            [Paragraph("<b>Slope Gradient:</b>", self.body_style), Paragraph(f"{f.slope_percentage}% Slope", self.body_style)],
            [Paragraph("<b>Topographic Wetness Index (TWI):</b>", self.body_style), Paragraph(f"{f.topographic_wetness_index} (Hydrological Catchment Index)", self.body_style)],
            [Paragraph("<b>Distance to Natural Waterbody:</b>", self.body_style), Paragraph(f"<b>{f.distance_to_waterbody_meters} Meters</b>", self.body_style)],
            [Paragraph("<b>Statutory Water Buffer Clearance:</b>", self.body_style), Paragraph(f"<font color='{'#DC2626' if f.distance_to_waterbody_meters < 30.0 else '#16A34A'}'><b>{'BUFFER ENCROACHMENT (<30m)' if f.distance_to_waterbody_meters < 30.0 else 'COMPLIANT (>30m)'}</b></font>", self.body_style)],
            [Paragraph("<b>Drainage Basin Categorization:</b>", self.body_style), Paragraph(f"<b>{f.catchment_drainage_type}</b>", self.body_style)],
            [Paragraph("<b>Flood Hazard Severity:</b>", self.body_style), Paragraph(f"<b>{f.flood_hazard_category}</b>", self.body_style)],
            [Paragraph("<b>Topography Risk Score:</b>", self.body_style), Paragraph(f"<b>{f.climate_risk_score} / 100 ({f.risk_level})</b>", self.body_style)]
        ]
        ft = Table(f_meta, colWidths=[190, 314])
        ft.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(ft)
        story.append(Spacer(1, 14))
        
        story.append(Paragraph("<b>Hydrological Advisory & Foundation Guidelines:</b>", self.section_h1))
        hydro_p = (
            "Andhra Pradesh Building Rules 2017 mandate a statutory minimum buffer of 9 meters from small irrigation channels, "
            "30 meters from medium streams / nalas, and 50–100 meters from major riverbanks and lakes. "
            "Parcels with high TWI (>10) require engineered stormwater retention ponds, elevated plinth basements, "
            "and sub-surface percolation drains to safeguard structures during severe tropical monsoon cyclones."
        )
        story.append(Paragraph(hydro_p, self.body_style))
        story.append(Spacer(1, 14))
        
        # Institutional Verification Box with QR Code & SHA-256 Digest
        story.append(Paragraph("<b>INSTITUTIONAL AUDIT TRAIL & DIGITAL CERTIFICATION</b>", self.section_h1))
        
        qr_drawing = self._create_qr_code(result.verification_url, size=75)
        
        cert_cells = [
            Paragraph("<font size='9.5' color='#1E3A8A'><b>DOCUMENT INTEGRITY: CRYPTOGRAPHICALLY VERIFIED</b></font>", self.body_style),
            Spacer(1, 2),
            Paragraph(f"<font size='8' color='#475569'><b>Report Reference:</b> {result.report_id} &nbsp;|&nbsp; <b>Timestamp:</b> {result.generated_at}</font>", self.body_style),
            Spacer(1, 2),
            Paragraph(f"<font size='7.5' color='#0F172A'><b>SHA-256 Digital Fingerprint:</b><br/><font face='Courier' color='#1E293B'><b>{result.report_hash}</b></font></font>", self.body_style),
            Spacer(1, 3),
            Paragraph(f"<font size='7.5' color='#166534'>✓ Scan QR code or browse <font color='#2563EB'><u>{result.verification_url}</u></font> to independently confirm certificate validity against the immutable registry.</font>", self.body_style)
        ]
        
        cert_table = Table([[qr_drawing, cert_cells]], colWidths=[85, 419])
        cert_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#1E3A8A")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(cert_table)
        story.append(Spacer(1, 10))
        
        # Certification & Disclaimer Box
        story.append(Paragraph("<b>REGULATORY & STATUTORY DISCLAIMER</b>", ParagraphStyle('H3', parent=self.section_h1, fontSize=9, textColor=colors.HexColor("#475569"))))
        disc_text = (
            "This report is an automated spatial due diligence evaluation generated by GeoDueDiligence SaaS platform. "
            "Data synthesized from official gazetted sources: VMRDA Master Plan 2041, MeeBhoomi AP Revenue Portal, and Copernicus 30m DEM. "
            "This document is intended for commercial risk mitigation, investment underwriting, and decision-support purposes. "
            "Independent legal verification at the concerned Sub-Registrar Office (SRO) is recommended prior to final execution of title deed."
        )
        disc_t = Table([[Paragraph(disc_text, ParagraphStyle('D', parent=self.body_style, fontSize=7.5, leading=10, textColor=colors.HexColor("#64748B")))]], colWidths=[504])
        disc_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('PADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(disc_t)
        
        doc.build(story, canvasmaker=NumberedCanvas)
        return filepath
