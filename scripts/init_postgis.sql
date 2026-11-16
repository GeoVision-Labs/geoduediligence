-- ============================================================================
-- GeoDueDiligence — PostGIS Spatial Database Schema
-- Target Jurisdiction: Visakhapatnam Metropolitan Region (VMRDA Master Plan 2041)
-- Database: PostgreSQL 16 + PostGIS 3.4
-- ============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Cadastral Survey Parcels Table (Spatial Partitioned by District)
CREATE TABLE IF NOT EXISTS cadastral_parcels (
    id SERIAL PRIMARY KEY,
    district VARCHAR(100) NOT NULL,
    mandal VARCHAR(100) NOT NULL,
    village_name VARCHAR(150) NOT NULL,
    survey_no VARCHAR(50) NOT NULL,
    pdf_x NUMERIC(10, 2),
    pdf_y NUMERIC(10, 2),
    dist_to_village_pt NUMERIC(10, 2),
    -- Spatial Geometry (Point / Polygon representation in WGS84)
    geom GEOMETRY(Point, 4326) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Spatial GIST Index for Sub-Second Nearest Neighbor & Intersection Queries
CREATE INDEX IF NOT EXISTS idx_parcels_geom ON cadastral_parcels USING GIST (geom);
-- B-Tree Compound Index for Rapid Tabular Lookups
CREATE INDEX IF NOT EXISTS idx_parcels_lookup ON cadastral_parcels (LOWER(village_name), LOWER(survey_no));
CREATE INDEX IF NOT EXISTS idx_parcels_mandal ON cadastral_parcels (district, mandal);

-- 3. VMRDA Master Plan 2041 Statutory Land Use Zoning Table
CREATE TABLE IF NOT EXISTS vmrda_zoning_2041 (
    id SERIAL PRIMARY KEY,
    zone_code VARCHAR(50) NOT NULL,
    zone_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    road_widening_setback VARCHAR(255),
    master_plan_ref VARCHAR(255) DEFAULT 'VMRDA Master Plan 2041 (Full 7,328 km²)',
    permitted_uses TEXT[],
    restricted_uses TEXT[],
    base_risk_score NUMERIC(5, 2) DEFAULT 15.0,
    -- Spatial MultiPolygon in WGS84
    geom GEOMETRY(MultiPolygon, 4326)
);

CREATE INDEX IF NOT EXISTS idx_zoning_geom ON vmrda_zoning_2041 USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_zoning_code ON vmrda_zoning_2041 (zone_code);

-- 4. MeeBhoomi Land Revenue & Title Encumbrance Table
CREATE TABLE IF NOT EXISTS meebhoomi_records (
    id SERIAL PRIMARY KEY,
    district VARCHAR(100) NOT NULL,
    mandal VARCHAR(100) NOT NULL,
    village_name VARCHAR(150) NOT NULL,
    survey_no VARCHAR(50) NOT NULL,
    pattadar_name VARCHAR(255) NOT NULL,
    anubhavadar_name VARCHAR(255) NOT NULL,
    khata_number VARCHAR(100) NOT NULL,
    extent_acres NUMERIC(8, 2) NOT NULL,
    land_nature VARCHAR(255) NOT NULL,
    section_22a_prohibited BOOLEAN DEFAULT FALSE,
    title_dispute_flag BOOLEAN DEFAULT FALSE,
    source_portal VARCHAR(150) DEFAULT 'AP MeeBhoomi / Webland',
    last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meebhoomi_lookup ON meebhoomi_records (LOWER(village_name), LOWER(survey_no));
CREATE INDEX IF NOT EXISTS idx_meebhoomi_22a ON meebhoomi_records (section_22a_prohibited) WHERE section_22a_prohibited = TRUE;

-- 5. VMRDA Layout Approvals & Unauthorized Blacklist Registry
CREATE TABLE IF NOT EXISTS vmrda_layouts_registry (
    id SERIAL PRIMARY KEY,
    district VARCHAR(100) NOT NULL,
    mandal VARCHAR(100) NOT NULL,
    village_name VARCHAR(150) NOT NULL,
    survey_no VARCHAR(50) NOT NULL,
    lp_number VARCHAR(100),
    approval_year INT,
    layout_status VARCHAR(150) NOT NULL,
    is_unauthorized BOOLEAN DEFAULT FALSE,
    lrs_eligible BOOLEAN DEFAULT FALSE,
    civic_utility_clearance TEXT,
    notification_ref VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_layouts_lookup ON vmrda_layouts_registry (LOWER(village_name), LOWER(survey_no));
CREATE INDEX IF NOT EXISTS idx_layouts_unauth ON vmrda_layouts_registry (is_unauthorized) WHERE is_unauthorized = TRUE;

-- 6. Digital Audit Reports & Cryptographic Verification Registry
CREATE TABLE IF NOT EXISTS audit_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id VARCHAR(50) UNIQUE NOT NULL,
    report_hash VARCHAR(64) UNIQUE NOT NULL,
    district VARCHAR(100) NOT NULL,
    mandal VARCHAR(100) NOT NULL,
    village_name VARCHAR(150) NOT NULL,
    survey_no VARCHAR(50) NOT NULL,
    overall_risk_score NUMERIC(5, 2) NOT NULL,
    overall_risk_grade VARCHAR(5) NOT NULL,
    risk_status VARCHAR(100) NOT NULL,
    pattadar_name VARCHAR(255),
    section_22a_prohibited BOOLEAN DEFAULT FALSE,
    zone_code VARCHAR(50),
    audit_payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_hash ON audit_reports (report_hash);
CREATE INDEX IF NOT EXISTS idx_reports_report_id ON audit_reports (report_id);
CREATE INDEX IF NOT EXISTS idx_reports_lookup ON audit_reports (LOWER(village_name), LOWER(survey_no));
