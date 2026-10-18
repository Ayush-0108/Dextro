-- =====================================================================================
-- DataMind — Snowflake setup (run once, top to bottom, in a Snowsight SQL worksheet)
-- Works on a free 30-day trial account (choose ENTERPRISE edition at sign-up: masking
-- policies and Time Travel used in the demo need it). Takes ~2 minutes on an X-Small.
-- Idempotent: safe to re-run.
-- =====================================================================================
USE ROLE ACCOUNTADMIN;

-- -------------------------------------------------------------------------------------
-- 1. Compute with cost guardrails
--    X-Small = 1 credit/hour, billed per second while running; suspends after 60 s idle.
--    The resource monitor hard-stops the warehouse if the daily budget is exceeded.
-- -------------------------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS DATAMIND_WH
  WITH WAREHOUSE_SIZE = 'XSMALL'
       AUTO_SUSPEND = 60
       AUTO_RESUME = TRUE
       INITIALLY_SUSPENDED = TRUE
       STATEMENT_TIMEOUT_IN_SECONDS = 120
       COMMENT = 'DataMind agent warehouse';

CREATE RESOURCE MONITOR IF NOT EXISTS DATAMIND_RM
  WITH CREDIT_QUOTA = 4
       FREQUENCY = DAILY
       START_TIMESTAMP = IMMEDIATELY
       TRIGGERS ON 75 PERCENT DO NOTIFY
                ON 100 PERCENT DO SUSPEND
                ON 110 PERCENT DO SUSPEND_IMMEDIATE;

ALTER WAREHOUSE DATAMIND_WH SET RESOURCE_MONITOR = DATAMIND_RM;

-- -------------------------------------------------------------------------------------
-- 2. Least-privilege roles
--    DATAMIND_ADMIN      owns the data, runs setup and the data-change demo
--    DATAMIND_AGENT      what the app uses: SELECT only, nothing else
--    DATAMIND_RESTRICTED like AGENT, but customer phone/balance are masked (governance demo)
-- -------------------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS DATAMIND_ADMIN;
CREATE ROLE IF NOT EXISTS DATAMIND_AGENT;
CREATE ROLE IF NOT EXISTS DATAMIND_RESTRICTED;
GRANT ROLE DATAMIND_ADMIN TO ROLE SYSADMIN;

SET me = CURRENT_USER();
GRANT ROLE DATAMIND_ADMIN TO USER IDENTIFIER($me);
GRANT ROLE DATAMIND_AGENT TO USER IDENTIFIER($me);
GRANT ROLE DATAMIND_RESTRICTED TO USER IDENTIFIER($me);

GRANT USAGE, OPERATE ON WAREHOUSE DATAMIND_WH TO ROLE DATAMIND_ADMIN;
GRANT USAGE ON WAREHOUSE DATAMIND_WH TO ROLE DATAMIND_AGENT;
GRANT USAGE ON WAREHOUSE DATAMIND_WH TO ROLE DATAMIND_RESTRICTED;

-- -------------------------------------------------------------------------------------
-- 3. Database and data
--    Copy TPC-H SF1 from Snowflake's shared sample database into our own schema. A copy is
--    needed because shared data is read-only: we attach masking policies and run the
--    "answer changes when data changes" demo against it. The data never leaves Snowflake
--    and is not committed to the repository.
-- -------------------------------------------------------------------------------------
-- If SNOWFLAKE_SAMPLE_DATA is missing from your account, recreate it from Snowflake's share first:
--   CREATE DATABASE SNOWFLAKE_SAMPLE_DATA FROM SHARE SFC_SAMPLES.SAMPLE_DATA;
CREATE DATABASE IF NOT EXISTS DATAMIND_DB COMMENT = 'DataMind demo data';
CREATE SCHEMA IF NOT EXISTS DATAMIND_DB.TPCH COMMENT = 'TPC-H SF1 copied from SNOWFLAKE_SAMPLE_DATA';
GRANT OWNERSHIP ON DATABASE DATAMIND_DB TO ROLE DATAMIND_ADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA DATAMIND_DB.TPCH TO ROLE DATAMIND_ADMIN COPY CURRENT GRANTS;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE_SAMPLE_DATA TO ROLE DATAMIND_ADMIN;
GRANT APPLY MASKING POLICY ON ACCOUNT TO ROLE DATAMIND_ADMIN;

USE ROLE DATAMIND_ADMIN;
USE WAREHOUSE DATAMIND_WH;
USE SCHEMA DATAMIND_DB.TPCH;

CREATE TABLE IF NOT EXISTS REGION   AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.REGION;
CREATE TABLE IF NOT EXISTS NATION   AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.NATION;
CREATE TABLE IF NOT EXISTS CUSTOMER AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER;
CREATE TABLE IF NOT EXISTS SUPPLIER AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.SUPPLIER;
CREATE TABLE IF NOT EXISTS PART     AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.PART;
CREATE TABLE IF NOT EXISTS PARTSUPP AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.PARTSUPP;
CREATE TABLE IF NOT EXISTS ORDERS   AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS;
CREATE TABLE IF NOT EXISTS LINEITEM AS SELECT * FROM SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.LINEITEM;

-- Keep 7 days of history so Time Travel can show "what the answer was before the data changed"
ALTER SCHEMA DATAMIND_DB.TPCH SET DATA_RETENTION_TIME_IN_DAYS = 7;

-- Documentation lives with the data (also visible to anyone browsing the schema)
COMMENT ON TABLE LINEITEM IS 'One row per order line (part bought from one supplier within an order)';
COMMENT ON TABLE ORDERS   IS 'One row per customer order';
COMMENT ON TABLE CUSTOMER IS 'One row per customer';
COMMENT ON TABLE SUPPLIER IS 'One row per supplier';
COMMENT ON TABLE PART     IS 'One row per part (product)';
COMMENT ON TABLE PARTSUPP IS 'One row per (part, supplier) offer: supply cost and stock';
COMMENT ON TABLE NATION   IS '25 nations, used for both customer and supplier location';
COMMENT ON TABLE REGION   IS '5 regions';

-- -------------------------------------------------------------------------------------
-- 4. Governance: dynamic data masking for the restricted role (Enterprise edition)
-- -------------------------------------------------------------------------------------
CREATE MASKING POLICY IF NOT EXISTS MASK_PHONE AS (val STRING) RETURNS STRING ->
  CASE WHEN CURRENT_ROLE() = 'DATAMIND_RESTRICTED' THEN '***-***-****' ELSE val END;

CREATE MASKING POLICY IF NOT EXISTS MASK_BALANCE AS (val NUMBER(12,2)) RETURNS NUMBER(12,2) ->
  CASE WHEN CURRENT_ROLE() = 'DATAMIND_RESTRICTED' THEN NULL ELSE val END;

ALTER TABLE CUSTOMER MODIFY COLUMN C_PHONE   SET MASKING POLICY MASK_PHONE FORCE;
ALTER TABLE CUSTOMER MODIFY COLUMN C_ACCTBAL SET MASKING POLICY MASK_BALANCE FORCE;
ALTER TABLE SUPPLIER MODIFY COLUMN S_PHONE   SET MASKING POLICY MASK_PHONE FORCE;

-- -------------------------------------------------------------------------------------
-- 5. Read-only grants for the agent roles (SELECT only; no INSERT/UPDATE/DELETE/CREATE)
-- -------------------------------------------------------------------------------------
GRANT USAGE ON DATABASE DATAMIND_DB TO ROLE DATAMIND_AGENT;
GRANT USAGE ON SCHEMA DATAMIND_DB.TPCH TO ROLE DATAMIND_AGENT;
GRANT SELECT ON ALL TABLES IN SCHEMA DATAMIND_DB.TPCH TO ROLE DATAMIND_AGENT;
GRANT USAGE ON DATABASE DATAMIND_DB TO ROLE DATAMIND_RESTRICTED;
GRANT USAGE ON SCHEMA DATAMIND_DB.TPCH TO ROLE DATAMIND_RESTRICTED;
GRANT SELECT ON ALL TABLES IN SCHEMA DATAMIND_DB.TPCH TO ROLE DATAMIND_RESTRICTED;

USE ROLE ACCOUNTADMIN;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DATAMIND_DB.TPCH TO ROLE DATAMIND_AGENT;
GRANT SELECT ON FUTURE TABLES IN SCHEMA DATAMIND_DB.TPCH TO ROLE DATAMIND_RESTRICTED;

-- -------------------------------------------------------------------------------------
-- 6. Verify (expected: 6001215 / 1500000 / 150000 rows; agent cannot write)
-- -------------------------------------------------------------------------------------
USE ROLE DATAMIND_AGENT;
USE WAREHOUSE DATAMIND_WH;
SELECT (SELECT COUNT(*) FROM DATAMIND_DB.TPCH.LINEITEM) AS lineitem_rows,
       (SELECT COUNT(*) FROM DATAMIND_DB.TPCH.ORDERS)   AS orders_rows,
       (SELECT COUNT(*) FROM DATAMIND_DB.TPCH.CUSTOMER) AS customer_rows;
SHOW GRANTS TO ROLE DATAMIND_AGENT;

-- Optional: prove the agent role is read-only (this must FAIL with "Insufficient privileges")
-- DELETE FROM DATAMIND_DB.TPCH.REGION;

-- Optional: prove masking works
-- USE ROLE DATAMIND_RESTRICTED; SELECT C_NAME, C_PHONE, C_ACCTBAL FROM DATAMIND_DB.TPCH.CUSTOMER LIMIT 3;

-- -------------------------------------------------------------------------------------
-- 7. Recommended: a dedicated app user that holds ONLY the agent roles.
--    Uncomment, choose a strong password, and put it in .env (never commit it).
--    Trial accounts allow password sign-in for this user; on paid accounts use key-pair auth
--    (TYPE = SERVICE, RSA_PUBLIC_KEY = '...') and SNOWFLAKE_PRIVATE_KEY_FILE in .env.
-- -------------------------------------------------------------------------------------
-- USE ROLE ACCOUNTADMIN;
-- CREATE USER IF NOT EXISTS DATAMIND_APP
--   PASSWORD = '<choose-a-strong-password>'
--   DEFAULT_ROLE = DATAMIND_AGENT
--   DEFAULT_WAREHOUSE = DATAMIND_WH
--   MUST_CHANGE_PASSWORD = FALSE
--   COMMENT = 'DataMind application user (read-only roles only)';
-- GRANT ROLE DATAMIND_AGENT TO USER DATAMIND_APP;
-- GRANT ROLE DATAMIND_RESTRICTED TO USER DATAMIND_APP;
