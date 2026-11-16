from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from ..core.database import Base

class CadastralParcelModel(Base):
    __tablename__ = "cadastral_parcels"

    id = Column(Integer, primary_key=True, index=True)
    district = Column(String(100), nullable=False)
    mandal = Column(String(100), nullable=False)
    village_name = Column(String(150), nullable=False, index=True)
    survey_no = Column(String(50), nullable=False, index=True)
    latitude = Column(Numeric(10, 6), nullable=False)
    longitude = Column(Numeric(10, 6), nullable=False)
    pdf_x = Column(Numeric(10, 2), nullable=True)
    pdf_y = Column(Numeric(10, 2), nullable=True)
    dist_to_village_pt = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class VMRDAZoningModel(Base):
    __tablename__ = "vmrda_zoning_2041"

    id = Column(Integer, primary_key=True, index=True)
    zone_code = Column(String(50), nullable=False, index=True)
    zone_name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    road_widening_setback = Column(String(255), nullable=True)
    master_plan_ref = Column(String(255), default="VMRDA Master Plan 2041")
    permitted_uses = Column(JSON, nullable=True)
    restricted_uses = Column(JSON, nullable=True)
    base_risk_score = Column(Numeric(5, 2), default=15.0)

class MeeBhoomiRecordModel(Base):
    __tablename__ = "meebhoomi_records"

    id = Column(Integer, primary_key=True, index=True)
    district = Column(String(100), nullable=False)
    mandal = Column(String(100), nullable=False)
    village_name = Column(String(150), nullable=False, index=True)
    survey_no = Column(String(50), nullable=False, index=True)
    pattadar_name = Column(String(255), nullable=False)
    anubhavadar_name = Column(String(255), nullable=False)
    khata_number = Column(String(100), nullable=False)
    extent_acres = Column(Numeric(8, 2), nullable=False)
    land_nature = Column(String(255), nullable=False)
    section_22a_prohibited = Column(Boolean, default=False, index=True)
    title_dispute_flag = Column(Boolean, default=False)
    source_portal = Column(String(150), default="AP MeeBhoomi / Webland")
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())

class VMRDALayoutModel(Base):
    __tablename__ = "vmrda_layouts_registry"

    id = Column(Integer, primary_key=True, index=True)
    district = Column(String(100), nullable=False)
    mandal = Column(String(100), nullable=False)
    village_name = Column(String(150), nullable=False, index=True)
    survey_no = Column(String(50), nullable=False, index=True)
    lp_number = Column(String(100), nullable=True)
    approval_year = Column(Integer, nullable=True)
    layout_status = Column(String(150), nullable=False)
    is_unauthorized = Column(Boolean, default=False, index=True)
    lrs_eligible = Column(Boolean, default=False)
    civic_utility_clearance = Column(Text, nullable=True)
    notification_ref = Column(String(255), nullable=True)

class AuditReportModel(Base):
    __tablename__ = "audit_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String(50), unique=True, nullable=False, index=True)
    report_hash = Column(String(64), unique=True, nullable=False, index=True)
    district = Column(String(100), nullable=False)
    mandal = Column(String(100), nullable=False)
    village_name = Column(String(150), nullable=False, index=True)
    survey_no = Column(String(50), nullable=False, index=True)
    overall_risk_score = Column(Numeric(5, 2), nullable=False)
    overall_risk_grade = Column(String(5), nullable=False)
    risk_status = Column(String(100), nullable=False)
    pattadar_name = Column(String(255), nullable=True)
    section_22a_prohibited = Column(Boolean, default=False)
    zone_code = Column(String(50), nullable=True)
    audit_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
