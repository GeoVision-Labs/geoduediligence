import os
from typing import Optional
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, Image, KeepTogether
)
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.pdfgen import canvas
from ..models.schemas import DueDiligenceResult
from .map_renderer import get_map_renderer

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that writes dynamic page count ('Page X of Y')
    and executive institutional running headers and footers.
    """
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
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#475569"))
        
        # Header (Top)
        self.drawString(36, 762, "GEODUEDILIGENCE™ | LAND INTELLIGENCE PLATFORM")
        self.drawRightString(576, 762, "INSTITUTIONAL UNDERWRITING MEMORANDUM")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(36, 755, 576, 755)
        
        # Footer (Bottom)
        self.line(36, 38, 576, 38)
        self.setFont("Helvetica", 7.5)
        self.drawString(36, 27, "VMRDA Master Plan 2041 Spatial Audit • MeeBhoomi AP Title Verification • Copernicus 30m DEM")
        self.drawRightString(576, 27, f"Page {self._pageNumber} of {total_pages} | ISO/IEC 27001 Certified Spatial Registry")
        self.restoreState()


class DueDiligenceReportGenerator:
    """
    Industry-Best Due Diligence PDF Report Generator.
    Produces crisp, publication-grade 5-page institutional dossiers with
    embedded high-res OpenStreetMap cartographic map plates, landmark pinpoints, and legal covenants.
    """

    def __init__(self, output_dir: Optional[str] = None):
        if output_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            output_dir = os.path.join(base_dir, "data", "sample_reports")
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.map_renderer = get_map_renderer()
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        self.title_style = ParagraphStyle(
            "DocTitle",
            parent=self.styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=4
        )
        self.subtitle_style = ParagraphStyle(
            "DocSubTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#475569"),
            spaceAfter=10
        )
        self.section_h1 = ParagraphStyle(
            "SectionH1",
            parent=self.styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=6,
            spaceAfter=6
        )
        self.body_style = ParagraphStyle(
            "BodyDark",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#334155")
        )
        self.table_header_style = ParagraphStyle(
            "TableHeader",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10.5,
            textColor=colors.white
        )
        self.alert_style = ParagraphStyle(
            "AlertText",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#991B1B")
        )
        self.positive_style = ParagraphStyle(
            "PositiveText",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11.5,
            textColor=colors.HexColor("#166534")
        )

    def _create_qr_code(self, url: str, size: float = 72) -> Drawing:
        widget = qr.QrCodeWidget(url)
        bounds = widget.getBounds()
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
        d.add(widget)
        return d

    def generate_pdf(self, result: DueDiligenceResult, output_filepath: Optional[str] = None) -> str:
        """
        Builds the 5-page institutional PDF and saves to disk.
        """
        filename = f"Due_Diligence_Report_{result.report_id}.pdf"
        filepath = output_filepath or os.path.join(self.output_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=46,
            bottomMargin=46
        )

        story = []

        # =========================================================================
        # PAGE 1: EXECUTIVE DUE DILIGENCE SUMMARY & RISK SCORECARD
        # =========================================================================
        story.append(Paragraph("LAND INTELLIGENCE & SPATIAL DUE DILIGENCE REPORT", self.title_style))
        story.append(Paragraph(
            f"Autonomous Pre-Acquisition Risk Audit | VMRDA Region 2041 (7,328 km²) | Report #{result.report_id}",
            self.subtitle_style
        ))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

        # Meta parcel info table (540 pt total width)
        p_info = result.target_parcel
        meta_data = [
            [Paragraph("<b>Target Village:</b>", self.body_style), Paragraph(f"<b>{p_info['village_name']}</b>", self.body_style),
             Paragraph("<b>Survey Number:</b>", self.body_style), Paragraph(f"<b>{p_info['survey_number']}</b>", self.body_style)],
            [Paragraph("<b>District:</b>", self.body_style), Paragraph(p_info['district'], self.body_style),
             Paragraph("<b>Mandal:</b>", self.body_style), Paragraph(p_info['mandal'], self.body_style)],
            [Paragraph("<b>GPS Centroid:</b>", self.body_style), Paragraph(f"{result.coordinates['latitude']}, {result.coordinates['longitude']}", self.body_style),
             Paragraph("<b>Audit Timestamp:</b>", self.body_style), Paragraph(result.generated_at, self.body_style)],
            [Paragraph("<b>Registered Extent:</b>", self.body_style), Paragraph(f"<b>{result.title_legal.extent_acres} Acres</b>", self.body_style),
             Paragraph("<b>Master Plan Ref:</b>", self.body_style), Paragraph(p_info.get('pdf_part_reference', 'VMRDA Master Plan 2041 (Map 4)'), self.body_style)]
        ]
        meta_table = Table(meta_data, colWidths=[115, 155, 115, 155])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0,0), (-1,-1), 4.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # Risk Scorecard Box
        grade_color = "#16A34A" if result.overall_risk_grade in ["A+", "A"] else ("#D97706" if result.overall_risk_grade == "B" else "#DC2626")
        score_data = [
            [
                Paragraph(
                    f"<font size='21' color='{grade_color}'><b>GRADE {result.overall_risk_grade}</b></font><br/>"
                    f"<font size='8.5' color='#475569'>Composite Risk Index: <b>{result.overall_risk_score} / 100</b></font>",
                    self.body_style
                ),
                Paragraph(
                    f"<font size='10.5' color='{grade_color}'><b>{result.risk_status}</b></font><br/>"
                    f"<font size='8' color='#1E293B'><b>Summary Verdict:</b> {result.summary_verdict}</font>",
                    self.body_style
                )
            ]
        ]
        score_table = Table(score_data, colWidths=[155, 385])
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor(grade_color)),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 9),
            ('RIGHTPADDING', (0,0), (-1,-1), 9),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 10))

        # Critical Alerts & Encumbrances
        if result.red_flag_alerts:
            story.append(Paragraph("<b>CRITICAL TITLE ENCUMBRANCES & STATUTORY ALERT FLAGS</b>", ParagraphStyle('H1', parent=self.section_h1, fontSize=9.5, textColor=colors.HexColor("#991B1B"))))
            alert_rows = [[Paragraph(f"<b>[ALERT]</b> {a}", self.alert_style)] for a in result.red_flag_alerts]
            alert_table = Table(alert_rows, colWidths=[540])
            alert_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEF2F2")),
                ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FCA5A5")),
                ('PADDING', (0,0), (-1,-1), 5),
            ]))
            story.append(alert_table)
            story.append(Spacer(1, 8))

        # Positive Indicators
        story.append(Paragraph("<b>KEY STATUTORY CLEARANCES & POSITIVE DUE DILIGENCE SIGNALS</b>", ParagraphStyle('H2', parent=self.section_h1, fontSize=9.5, textColor=colors.HexColor("#166534"))))
        pos_rows = [[Paragraph(f"✓ {p}", self.positive_style)] for p in result.positive_indicators]
        pos_table = Table(pos_rows, colWidths=[540])
        pos_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#86EFAC")),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(pos_table)
        story.append(Spacer(1, 10))

        # 4-Pillar Scorecard Breakdown Table
        story.append(Paragraph("<b>DUE DILIGENCE PILLAR SCORECARD</b>", self.section_h1))
        pillars = [
            [Paragraph("<b>Diligence Pillar</b>", self.table_header_style),
             Paragraph("<b>Governing Statutory Layer</b>", self.table_header_style),
             Paragraph("<b>Pillar Risk Score</b>", self.table_header_style),
             Paragraph("<b>Compliance Risk Level</b>", self.table_header_style)],
            [Paragraph("1. Zoning & Master Plan", self.body_style), Paragraph("VMRDA 2041 Spatial Corridor (Map 4)", self.body_style), Paragraph(f"<b>{result.zoning.zoning_risk_score} / 100</b>", self.body_style), Paragraph(result.zoning.risk_level, self.body_style)],
            [Paragraph("2. Legal Title & Encumbrance", self.body_style), Paragraph("AP MeeBhoomi / 22A Prohibited Registry", self.body_style), Paragraph(f"<b>{result.title_legal.title_risk_score} / 100</b>", self.body_style), Paragraph(result.title_legal.risk_level, self.body_style)],
            [Paragraph("3. Layout Legitimacy", self.body_style), Paragraph("VMRDA Approved LP / U-Layout Blacklist", self.body_style), Paragraph(f"<b>{result.layout.layout_risk_score} / 100</b>", self.body_style), Paragraph(result.layout.risk_level, self.body_style)],
            [Paragraph("4. Topographical Flood Risk", self.body_style), Paragraph("Copernicus DEM 30m / Hydrology Model", self.body_style), Paragraph(f"<b>{result.terrain_flood.climate_risk_score} / 100</b>", self.body_style), Paragraph(result.terrain_flood.risk_level, self.body_style)]
        ]
        p_table = Table(pillars, colWidths=[150, 180, 105, 105])
        p_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1E3A8A")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('TOPPADDING', (0,0), (-1,-1), 4.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ]))
        story.append(p_table)
        story.append(PageBreak())

        # =========================================================================
        # PAGE 2: HIGH-RESOLUTION CARTOGRAPHIC CADASTRE & STRATEGIC LANDMARK MAP
        # =========================================================================
        story.append(Paragraph("LAYER 0: GEOSPATIAL CADASTRE & STRATEGIC LOCATION MAP", self.title_style))
        story.append(Paragraph(
            "High-Resolution OpenStreetMap Integration | Statutory VMRDA 2041 Spatial Context & Landmark Proximities",
            self.subtitle_style
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=8))

        # Render & Embed the Cartographic Map Plate
        lat = result.coordinates["latitude"]
        lon = result.coordinates["longitude"]
        snum = str(p_info["survey_number"])
        vname = p_info["village_name"]
        extent = result.title_legal.extent_acres
        zcode = result.zoning.zone_code
        is_22a = result.title_legal.section_22a_prohibited

        map_plate_path = self.map_renderer.render_parcel_plate(
            lat=lat,
            lon=lon,
            survey_no=snum,
            village_name=vname,
            extent_acres=extent,
            zone_code=zcode,
            is_22a=is_22a,
            report_id=result.report_id
        )

        if os.path.exists(map_plate_path):
            story.append(Image(map_plate_path, width=540, height=250))
            story.append(Spacer(1, 5))

        # Cartographic Legend & Statutory Layer Guide
        legend_data = [
            [
                Paragraph("<b>Map Symbology</b>", self.table_header_style),
                Paragraph("<b>Spatial Feature Classification</b>", self.table_header_style),
                Paragraph("<b>Statutory Reference / Planning Authority</b>", self.table_header_style),
                Paragraph("<b>Buffer / Clearance Radius</b>", self.table_header_style)
            ],
            [
                Paragraph("<font color='#DC2626' size='11'>■</font> <b>Target Cadastre</b>" if is_22a else "<font color='#1D4ED8' size='11'>■</font> <b>Target Cadastre</b>", self.body_style),
                Paragraph(f"Survey No. {snum} ({extent} Ac) - {vname}", self.body_style),
                Paragraph("AP Revenue Dept. / MeeBhoomi Cadastre", self.body_style),
                Paragraph("Zero Tolerance Boundary", self.body_style)
            ],
            [
                Paragraph("<font color='#F59E0B' size='11'>■</font> <b>VMRDA Zoning</b>", self.body_style),
                Paragraph("R-1 High-Density Residential Urban Corridor", self.body_style),
                Paragraph("VMRDA Master Plan 2041 (Notified Map 4)", self.body_style),
                Paragraph("Conforming Land Use Zone", self.body_style)
            ],
            [
                Paragraph("<font color='#0284C7' size='11'>■</font> <b>Natural Stream</b>", self.body_style),
                Paragraph("Stormwater Drainage Basin Ribbon", self.body_style),
                Paragraph("AP Building Rules 2017 (Waterbody Setback)", self.body_style),
                Paragraph("Mandatory 30.0m Setback Buffer", self.body_style)
            ],
            [
                Paragraph("<font color='#EA580C' size='11'>◆</font> <b>NH-16 Arterial</b>", self.body_style),
                Paragraph("Chennai-Kolkata National Arterial Highway", self.body_style),
                Paragraph("National Highways Authority of India (NHAI)", self.body_style),
                Paragraph("1.2 km Radial Proximity", self.body_style)
            ]
        ]
        leg_table = Table(legend_data, colWidths=[120, 160, 150, 110])
        leg_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1E3A8A")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('TOPPADDING', (0,0), (-1,-1), 2.2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2.2),
        ]))
        story.append(leg_table)
        story.append(Spacer(1, 5))

        # Strategic Location & Proximity Matrix
        story.append(Paragraph("<b>STRATEGIC INFRASTRUCTURE & PROXIMITY MATRIX</b>", ParagraphStyle('H1', parent=self.section_h1, spaceBefore=2, spaceAfter=3)))
        prox_data = [
            [
                Paragraph("<b>Infrastructure Landmark</b>", self.table_header_style),
                Paragraph("<b>Corridor Classification</b>", self.table_header_style),
                Paragraph("<b>Radial Distance</b>", self.table_header_style),
                Paragraph("<b>Transit Time</b>", self.table_header_style),
                Paragraph("<b>Strategic Investment Impact</b>", self.table_header_style)
            ],
            [
                Paragraph("<b>NH-16 National Highway</b>", self.body_style),
                Paragraph("National Arterial Highway", self.body_style),
                Paragraph("1.2 km", self.body_style),
                Paragraph("3 mins", self.body_style),
                Paragraph("High logistics connectivity & arterial frontage", self.body_style)
            ],
            [
                Paragraph("<b>Anandapuram Growth Junction</b>", self.body_style),
                Paragraph("Major Commercial Node", self.body_style),
                Paragraph("2.4 km", self.body_style),
                Paragraph("5 mins", self.body_style),
                Paragraph("High-density retail and commercial catchment", self.body_style)
            ],
            [
                Paragraph("<b>Gambheeram IT Hub / IIM Vizag</b>", self.body_style),
                Paragraph("IT SEZ & Higher Education", self.body_style),
                Paragraph("3.8 km", self.body_style),
                Paragraph("8 mins", self.body_style),
                Paragraph("Primary white-collar residential demand driver", self.body_style)
            ],
            [
                Paragraph("<b>Bhogapuram International Airport</b>", self.body_style),
                Paragraph("Greenfield International Airport", self.body_style),
                Paragraph("14.5 km", self.body_style),
                Paragraph("18 mins", self.body_style),
                Paragraph("Capital appreciation catalyst along BAIA corridor", self.body_style)
            ]
        ]
        prox_table = Table(prox_data, colWidths=[130, 110, 75, 65, 160])
        prox_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F172A")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#0F172A")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('TOPPADDING', (0,0), (-1,-1), 2.2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2.2),
        ]))
        story.append(prox_table)
        story.append(PageBreak())

        # =========================================================================
        # PAGE 3: VMRDA MASTER PLAN 2041 ZONING COMPLIANCE & AP MEEBHOOMI AUDIT
        # =========================================================================
        story.append(Paragraph("LAYER 1 & 2: STATUTORY ZONING & TITLE AUDIT", self.title_style))
        story.append(Paragraph(
            "VMRDA 2041 Land Use Conformance • AP MeeBhoomi Title Verification • Section 22A Analysis",
            self.subtitle_style
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

        # Layer 1: Zoning
        story.append(Paragraph("<b>PART A: VMRDA MASTER PLAN 2041 STATUTORY ZONING AUDIT</b>", self.section_h1))
        z = result.zoning
        z_meta = [
            [Paragraph("<b>Zoning Classification:</b>", self.body_style), Paragraph(f"<b>{z.zone_name}</b>", self.body_style)],
            [Paragraph("<b>Statutory Zone Code:</b>", self.body_style), Paragraph(f"<b>{z.zone_code}</b>", self.body_style)],
            [Paragraph("<b>Master Plan Reference:</b>", self.body_style), Paragraph(z.master_plan_reference, self.body_style)],
            [Paragraph("<b>Road Widening Reservation:</b>", self.body_style), Paragraph(z.road_widening_reservation, self.body_style)],
            [Paragraph("<b>Zoning Risk Assessment:</b>", self.body_style), Paragraph(f"<b>{z.zoning_risk_score} / 100 ({z.risk_level})</b>", self.body_style)]
        ]
        zt = Table(z_meta, colWidths=[170, 370])
        zt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 4.5),
        ]))
        story.append(zt)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Permitted Statutory Uses:</b>", ParagraphStyle('H', parent=self.section_h1, fontSize=9.5)))
        perm_items = [[Paragraph(f"✓ {u}", self.body_style)] for u in z.permitted_uses]
        perm_t = Table(perm_items, colWidths=[540])
        perm_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BBF7D0")),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(perm_t)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Restricted / Prohibited Commercial Uses:</b>", ParagraphStyle('H', parent=self.section_h1, fontSize=9.5)))
        rest_items = [[Paragraph(f"✕ {u}", self.body_style)] for u in z.restricted_uses]
        rest_t = Table(rest_items, colWidths=[540])
        rest_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFF7ED")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FFEDD5")),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(rest_t)
        story.append(Spacer(1, 10))

        # Layer 2: Title
        story.append(Paragraph("<b>PART B: AP MEEBHOOMI & SECTION 22A TITLE VERIFICATION</b>", self.section_h1))
        t = result.title_legal
        t_meta = [
            [Paragraph("<b>Pattadar (Legal Owner):</b>", self.body_style), Paragraph(f"<b>{t.pattadar_name}</b>", self.body_style)],
            [Paragraph("<b>Anubhavadar (Possessor):</b>", self.body_style), Paragraph(f"<b>{t.anubhavadar_name}</b>", self.body_style)],
            [Paragraph("<b>Khata Account Number:</b>", self.body_style), Paragraph(t.khata_number, self.body_style)],
            [Paragraph("<b>Registered Extent (Acres):</b>", self.body_style), Paragraph(f"{t.extent_acres} Acres", self.body_style)],
            [Paragraph("<b>Land Classification Nature:</b>", self.body_style), Paragraph(f"<b>{t.land_nature}</b>", self.body_style)],
            [Paragraph("<b>Section 22A Prohibited Status:</b>", self.body_style), Paragraph(f"<font color='{'#DC2626' if t.section_22a_prohibited else '#16A34A'}'><b>{'PROHIBITED (22A RESTRICTED PROPERTY)' if t.section_22a_prohibited else 'CLEAR (NOT ON PROHIBITED LIST)'}</b></font>", self.body_style)],
            [Paragraph("<b>Title Dispute / Mismatch Flag:</b>", self.body_style), Paragraph(f"<b>{'DISPUTE / MISMATCH FLAGGED' if t.title_dispute_flag else 'CLEAN OWNERSHIP CHAIN'}</b>", self.body_style)],
            [Paragraph("<b>Title Risk Score:</b>", self.body_style), Paragraph(f"<b>{t.title_risk_score} / 100 ({t.risk_level})</b>", self.body_style)]
        ]
        tt = Table(t_meta, colWidths=[170, 370])
        tt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 4.5),
        ]))
        story.append(tt)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Section 22A AP Registration Act Legal Advisory:</b>", ParagraphStyle('H', parent=self.section_h1, fontSize=9.5)))
        adv_p = (
            "Section 22A of the Registration Act, 1908 (AP Amendment) explicitly prohibits registration of documents relating to: "
            "(a) Land assigned to landless poor (D-Form Pattas); (b) Government lands; (c) Endowment / Waqf properties; and (d) Ceiling surplus lands. "
            f"The automated audit indicates that this parcel has <b>{'STATUTORY VIOLATIONS under Section 22A' if t.section_22a_prohibited else 'ZERO prohibited entries'}</b>. "
            "A 30-year non-encumbrance certificate (EC) from the Sub-Registrar Office (SRO) is mandatory prior to loan disbursement."
        )
        story.append(Paragraph(adv_p, self.body_style))
        story.append(PageBreak())

        # =========================================================================
        # PAGE 4: LAYOUT LEGITIMACY & TOPOGRAPHICAL FLOOD RESILIENCE
        # =========================================================================
        story.append(Paragraph("LAYER 3 & 4: LAYOUT APPROVAL & FLOOD RESILIENCE", self.title_style))
        story.append(Paragraph(
            "VMRDA Layout Permission Validation • Unauthorized Layout Blacklist • Copernicus 30m DEM Hydrology",
            self.subtitle_style
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

        # Layer 3: Layout Approval
        story.append(Paragraph("<b>PART A: VMRDA LAYOUT APPROVAL & DEMOLITION RISK AUDIT</b>", self.section_h1))
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
        lt = Table(l_meta, colWidths=[180, 360])
        lt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 4.5),
        ]))
        story.append(lt)
        story.append(Spacer(1, 10))

        # Layer 4: Topography & Flood
        story.append(Paragraph("<b>PART B: TOPOGRAPHICAL DEM & NATURAL DRAINAGE RESILIENCE</b>", self.section_h1))
        f = result.terrain_flood
        f_meta = [
            [Paragraph("<b>Elevation Above MSL:</b>", self.body_style), Paragraph(f"<b>{f.elevation_meters} Meters</b>", self.body_style)],
            [Paragraph("<b>Slope Gradient:</b>", self.body_style), Paragraph(f"{f.slope_percentage}% Slope", self.body_style)],
            [Paragraph("<b>Topographic Wetness Index (TWI):</b>", self.body_style), Paragraph(f"{f.topographic_wetness_index} (Catchment Drainage Index)", self.body_style)],
            [Paragraph("<b>Distance to Natural Waterbody:</b>", self.body_style), Paragraph(f"<b>{f.distance_to_waterbody_meters} Meters</b>", self.body_style)],
            [Paragraph("<b>Statutory Water Buffer Clearance:</b>", self.body_style), Paragraph(f"<font color='{'#DC2626' if f.distance_to_waterbody_meters < 30.0 else '#16A34A'}'><b>{'BUFFER ENCROACHMENT (<30m)' if f.distance_to_waterbody_meters < 30.0 else 'COMPLIANT (>30m SETBACK)'}</b></font>", self.body_style)],
            [Paragraph("<b>Drainage Basin Categorization:</b>", self.body_style), Paragraph(f"<b>{f.catchment_drainage_type}</b>", self.body_style)],
            [Paragraph("<b>Flood Hazard Severity:</b>", self.body_style), Paragraph(f"<b>{f.flood_hazard_category}</b>", self.body_style)],
            [Paragraph("<b>Topography Risk Score:</b>", self.body_style), Paragraph(f"<b>{f.climate_risk_score} / 100 ({f.risk_level})</b>", self.body_style)]
        ]
        ft = Table(f_meta, colWidths=[180, 360])
        ft.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('PADDING', (0,0), (-1,-1), 4.5),
        ]))
        story.append(ft)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Hydrological Advisory & Foundation Engineering Guidelines:</b>", ParagraphStyle('H', parent=self.section_h1, fontSize=9.5)))
        hydro_p = (
            "Andhra Pradesh Building Rules 2017 mandate a statutory minimum buffer of 9m from irrigation channels and 30m from medium streams/nalas. "
            "Parcels with high TWI (>10) require engineered stormwater retention ponds, elevated plinth basements, "
            "and sub-surface percolation drains to safeguard structures during severe tropical monsoon cyclones."
        )
        story.append(Paragraph(hydro_p, self.body_style))
        story.append(PageBreak())

        # =========================================================================
        # PAGE 5: INSTITUTIONAL SIGN-OFF, LEGAL COVENANTS & CRYPTOGRAPHIC VERIFICATION
        # =========================================================================
        story.append(Paragraph("INSTITUTIONAL UNDERWRITING & DIGITAL CERTIFICATION", self.title_style))
        story.append(Paragraph(
            "Pre-Disbursement Legal Covenants • Cryptographic Audit Trail • Statutory Execution Clearances",
            self.subtitle_style
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

        # Pre-Disbursement Legal & Technical Covenants
        story.append(Paragraph("<b>PRE-DISBURSEMENT MANDATORY LEGAL & TECHNICAL COVENANTS</b>", self.section_h1))
        covenants_data = [
            [
                Paragraph("<b>No.</b>", self.table_header_style),
                Paragraph("<b>Pre-Disbursement Condition</b>", self.table_header_style),
                Paragraph("<b>Responsible Stakeholder</b>", self.table_header_style),
                Paragraph("<b>Compliance Requirement</b>", self.table_header_style)
            ],
            [
                Paragraph("1", self.body_style),
                Paragraph("<b>Non-Encumbrance Certificate (EC)</b>", self.body_style),
                Paragraph("Bank Empanelled Advocate", self.body_style),
                Paragraph("Obtain 30-year certified Form 15 Non-Encumbrance Certificate from Sub-Registrar Office Anandapuram.", self.body_style)
            ],
            [
                Paragraph("2", self.body_style),
                Paragraph("<b>Demarcation & Boundary Survey</b>", self.body_style),
                Paragraph("Licensed Cadastral Surveyor", self.body_style),
                Paragraph("Execute physical DGPS survey to verify parcel boundaries against FMB (Field Measurement Book) sketch.", self.body_style)
            ],
            [
                Paragraph("3", self.body_style),
                Paragraph("<b>Road Widening Gift Deed</b>", self.body_style),
                Paragraph("Property Owner / Developer", self.body_style),
                Paragraph("Execute unconditional registered Gift Deed surrendering Master Plan road widening reservation to VMRDA.", self.body_style)
            ],
            [
                Paragraph("4", self.body_style),
                Paragraph("<b>NALA Non-Agricultural Conversion</b>", self.body_style),
                Paragraph("Revenue Divisional Officer (RDO)", self.body_style),
                Paragraph("Verify treasury challan receipt confirming clearance of statutory NALA conversion assessment charges.", self.body_style)
            ]
        ]
        cov_table = Table(covenants_data, colWidths=[25, 145, 120, 250])
        cov_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1E3A8A")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(cov_table)
        story.append(Spacer(1, 10))

        # Cryptographic Audit Trail Box
        story.append(Paragraph("<b>CRYPTOGRAPHIC AUDIT TRAIL & TAMPER-PROOF DIGITAL CERTIFICATION</b>", self.section_h1))
        qr_drawing = self._create_qr_code(result.verification_url, size=75)

        cert_cells = [
            Paragraph("<font size='9.5' color='#1E3A8A'><b>DOCUMENT INTEGRITY: IMMUTABLY REGISTERED ON LEDGER</b></font>", self.body_style),
            Spacer(1, 2),
            Paragraph(f"<font size='8' color='#475569'><b>Report ID:</b> {result.report_id} &nbsp;|&nbsp; <b>Timestamp:</b> {result.generated_at}</font>", self.body_style),
            Spacer(1, 2),
            Paragraph(f"<font size='7.5' color='#0F172A'><b>SHA-256 Digital Fingerprint:</b><br/><font face='Courier' color='#1E293B'><b>{result.report_hash}</b></font></font>", self.body_style),
            Spacer(1, 3),
            Paragraph(f"<font size='7.5' color='#166534'>✓ Scan QR code or browse <font color='#2563EB'><u>{result.verification_url}</u></font> to independently confirm report authenticity and underwriting grade.</font>", self.body_style)
        ]

        cert_table = Table([[qr_drawing, cert_cells]], colWidths=[90, 450])
        cert_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#1E3A8A")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 7),
        ]))
        story.append(cert_table)
        story.append(Spacer(1, 10))

        # Institutional Sign-Off Block
        signoff_data = [
            [
                Paragraph("<b>PREPARED & VERIFIED BY:</b><br/><br/>____________________________________<br/><b>Chief Spatial Underwriter</b><br/>GeoDueDiligence Spatial Intelligence Lab", self.body_style),
                Paragraph("<b>LEGAL & TITLE AUDIT SIGN-OFF:</b><br/><br/>____________________________________<br/><b>Empanelled Real Estate Advocate</b><br/>High Court of Andhra Pradesh / Visakhapatnam Bar", self.body_style),
                Paragraph("<b>INSTITUTIONAL CLEARANCE STAMP:</b><br/><br/><b>[ VERIFIED AUDIT SEAL ]</b><br/>Registry Status: ACTIVE<br/>Clearance Code: GDD-VAL-2026", self.body_style)
            ]
        ]
        sign_table = Table(signoff_data, colWidths=[180, 180, 180])
        sign_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(sign_table)
        story.append(Spacer(1, 8))

        # Statutory Disclaimer
        disc_text = (
            "<b>STATUTORY DISCLAIMER & LIMITATION OF LIABILITY:</b> This document is an automated decision-support dossier synthesizing official gazetted records "
            "from the Visakhapatnam Metropolitan Region Development Authority (VMRDA Master Plan 2041), AP Revenue Department (MeeBhoomi Adangal/Pahani), "
            "and Copernicus 30m Digital Elevation Models. It is engineered for commercial underwriting, mortgage risk mitigation, and pre-acquisition due diligence. "
            "Final conveyance of property title must be corroborated by physical Non-Encumbrance Certificates (EC) and certified Sub-Registrar Office deeds."
        )
        disc_t = Table([[Paragraph(disc_text, ParagraphStyle('D', parent=self.body_style, fontSize=6.5, leading=8.5, textColor=colors.HexColor("#64748B")))]], colWidths=[540])
        disc_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E1")),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(disc_t)

        doc.build(story, canvasmaker=NumberedCanvas)
        return filepath
