-- =====================================================================================
-- DataMind — Chinook dataset setup (run once, top to bottom, in Snowsight as ACCOUNTADMIN)
-- Schema: DATAMIND_DB.CHINOOK
-- Owned by DATAMIND_ADMIN. Read access granted to DATAMIND_AGENT and DATAMIND_RESTRICTED.
-- Idempotent: safe to re-run.
-- =====================================================================================
USE ROLE ACCOUNTADMIN;

-- -------------------------------------------------------------------------------------
-- 1. Database, schema and ownership
-- -------------------------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS DATAMIND_DB COMMENT = 'DataMind demo data';
CREATE SCHEMA IF NOT EXISTS DATAMIND_DB.CHINOOK COMMENT = 'Chinook digital media store dataset';

GRANT USAGE ON DATABASE DATAMIND_DB TO ROLE DATAMIND_ADMIN;
GRANT USAGE ON SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_ADMIN;
GRANT OWNERSHIP ON SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_ADMIN COPY CURRENT GRANTS;

USE ROLE DATAMIND_ADMIN;
USE WAREHOUSE DATAMIND_WH;
USE SCHEMA DATAMIND_DB.CHINOOK;

-- -------------------------------------------------------------------------------------
-- 2. File format and stage for CSV data loading
-- -------------------------------------------------------------------------------------
-- OR REPLACE so a re-run updates it; AUTO because the exported dates are plain YYYY-MM-DD (no time part)
CREATE OR REPLACE FILE FORMAT CHINOOK_CSV_FORMAT
  TYPE = 'CSV'
  FIELD_DELIMITER = ','
  RECORD_DELIMITER = '\n'
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('', 'NULL', 'null')
  DATE_FORMAT = 'AUTO'
  TIMESTAMP_FORMAT = 'AUTO';

CREATE STAGE IF NOT EXISTS CHINOOK_STAGE
  FILE_FORMAT = CHINOOK_CSV_FORMAT
  COMMENT = 'Internal stage for Chinook CSV data loading';

-- -------------------------------------------------------------------------------------
-- 3. Tables (11 tables with primary and foreign key definitions)
-- -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ARTIST (
  artist_id INTEGER PRIMARY KEY,
  name VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS ALBUM (
  album_id INTEGER PRIMARY KEY,
  title VARCHAR(160) NOT NULL,
  artist_id INTEGER NOT NULL REFERENCES ARTIST(artist_id)
);

CREATE TABLE IF NOT EXISTS EMPLOYEE (
  employee_id INTEGER PRIMARY KEY,
  last_name VARCHAR(20) NOT NULL,
  first_name VARCHAR(20) NOT NULL,
  title VARCHAR(30),
  reports_to INTEGER REFERENCES EMPLOYEE(employee_id),
  birth_date TIMESTAMP_NTZ,
  hire_date TIMESTAMP_NTZ,
  address VARCHAR(70),
  city VARCHAR(40),
  state VARCHAR(40),
  country VARCHAR(40),
  postal_code VARCHAR(10),
  phone VARCHAR(24),
  fax VARCHAR(24),
  email VARCHAR(60)
);

CREATE TABLE IF NOT EXISTS CUSTOMER (
  customer_id INTEGER PRIMARY KEY,
  first_name VARCHAR(40) NOT NULL,
  last_name VARCHAR(20) NOT NULL,
  company VARCHAR(80),
  address VARCHAR(70),
  city VARCHAR(40),
  state VARCHAR(40),
  country VARCHAR(40),
  postal_code VARCHAR(10),
  phone VARCHAR(24),
  fax VARCHAR(24),
  email VARCHAR(60) NOT NULL,
  support_rep_id INTEGER REFERENCES EMPLOYEE(employee_id)
);

CREATE TABLE IF NOT EXISTS GENRE (
  genre_id INTEGER PRIMARY KEY,
  name VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS MEDIA_TYPE (
  media_type_id INTEGER PRIMARY KEY,
  name VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS TRACK (
  track_id INTEGER PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  album_id INTEGER REFERENCES ALBUM(album_id),
  media_type_id INTEGER NOT NULL REFERENCES MEDIA_TYPE(media_type_id),
  genre_id INTEGER REFERENCES GENRE(genre_id),
  composer VARCHAR(220),
  milliseconds INTEGER NOT NULL,
  bytes INTEGER,
  unit_price NUMBER(10,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS INVOICE (
  invoice_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES CUSTOMER(customer_id),
  invoice_date TIMESTAMP_NTZ NOT NULL,
  billing_address VARCHAR(70),
  billing_city VARCHAR(40),
  billing_state VARCHAR(40),
  billing_country VARCHAR(40),
  billing_postal_code VARCHAR(10),
  total NUMBER(10,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS INVOICE_LINE (
  invoice_line_id INTEGER PRIMARY KEY,
  invoice_id INTEGER NOT NULL REFERENCES INVOICE(invoice_id),
  track_id INTEGER NOT NULL REFERENCES TRACK(track_id),
  unit_price NUMBER(10,2) NOT NULL,
  quantity INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS PLAYLIST (
  playlist_id INTEGER PRIMARY KEY,
  name VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS PLAYLIST_TRACK (
  playlist_id INTEGER NOT NULL REFERENCES PLAYLIST(playlist_id),
  track_id INTEGER NOT NULL REFERENCES TRACK(track_id),
  PRIMARY KEY (playlist_id, track_id)
);

-- Documentation
COMMENT ON TABLE ARTIST IS 'Music artists and bands';
COMMENT ON TABLE ALBUM IS 'Albums released by artists';
COMMENT ON TABLE EMPLOYEE IS 'Store staff including managers and support representatives';
COMMENT ON TABLE CUSTOMER IS 'Customers purchasing digital tracks';
COMMENT ON TABLE GENRE IS 'Music genres';
COMMENT ON TABLE MEDIA_TYPE IS 'Audio and video media formats';
COMMENT ON TABLE TRACK IS 'Individual audio/video tracks with duration, bytes, and unit price';
COMMENT ON TABLE INVOICE IS 'Customer purchase invoices with billing location and order total';
COMMENT ON TABLE INVOICE_LINE IS 'Line items for purchased tracks within each invoice';
COMMENT ON TABLE PLAYLIST IS 'Named playlists';
COMMENT ON TABLE PLAYLIST_TRACK IS 'Many-to-many relationship linking playlists to tracks';

-- -------------------------------------------------------------------------------------
-- 4. Governance: dynamic data masking for sensitive fields under DATAMIND_RESTRICTED
-- -------------------------------------------------------------------------------------
CREATE MASKING POLICY IF NOT EXISTS MASK_EMAIL AS (val STRING) RETURNS STRING ->
  CASE WHEN CURRENT_ROLE() = 'DATAMIND_RESTRICTED' THEN '***@***.***' ELSE val END;

-- Apply phone masking (MASK_PHONE was created in DATAMIND_DB.TPCH by 01_setup.sql, so name it fully) and
-- email masking to customer and employee personal info
ALTER TABLE CUSTOMER MODIFY COLUMN phone SET MASKING POLICY DATAMIND_DB.TPCH.MASK_PHONE FORCE;
ALTER TABLE CUSTOMER MODIFY COLUMN email SET MASKING POLICY MASK_EMAIL FORCE;
ALTER TABLE EMPLOYEE MODIFY COLUMN phone SET MASKING POLICY DATAMIND_DB.TPCH.MASK_PHONE FORCE;
ALTER TABLE EMPLOYEE MODIFY COLUMN email SET MASKING POLICY MASK_EMAIL FORCE;

-- -------------------------------------------------------------------------------------
-- 5. Read-only grants for the agent roles (SELECT only)
-- -------------------------------------------------------------------------------------
GRANT USAGE ON SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_AGENT;
GRANT SELECT ON ALL TABLES IN SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_AGENT;
GRANT USAGE ON SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_RESTRICTED;
GRANT SELECT ON ALL TABLES IN SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_RESTRICTED;

USE ROLE ACCOUNTADMIN;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_AGENT;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DATAMIND_DB.CHINOOK TO ROLE DATAMIND_RESTRICTED;
