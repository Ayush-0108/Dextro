-- =====================================================================================
-- DataMind evidence: trace any answer to Snowflake query history, and show credit use.
-- Every query DataMind runs carries QUERY_TAG = {"app":"datamind","answer_id":"...","candidate":"..."}
-- =====================================================================================
USE ROLE ACCOUNTADMIN;
USE WAREHOUSE DATAMIND_WH;

-- All DataMind queries, newest first
SELECT q.query_id,
       q.start_time,
       q.role_name,
       TRY_PARSE_JSON(q.query_tag):answer_id::STRING AS answer_id,
       TRY_PARSE_JSON(q.query_tag):candidate::STRING AS candidate,
       q.execution_status,
       q.total_elapsed_time AS elapsed_ms,
       q.rows_produced,
       q.query_text
FROM TABLE(DATAMIND_DB.INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE(
       WAREHOUSE_NAME => 'DATAMIND_WH', RESULT_LIMIT => 1000)) AS q
WHERE q.query_tag ILIKE '%datamind%'
  AND q.query_type = 'SELECT'
ORDER BY q.start_time DESC;

-- One specific answer (paste the answer id shown in the app's Evidence tab)
-- ... WHERE TRY_PARSE_JSON(q.query_tag):answer_id::STRING = '<answer id>'

-- Credits used by the DataMind warehouse in the last 7 days
SELECT start_time, end_time, credits_used
FROM TABLE(DATAMIND_DB.INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY(
       DATE_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP()),
       WAREHOUSE_NAME => 'DATAMIND_WH'))
ORDER BY start_time DESC;

SHOW RESOURCE MONITORS LIKE 'DATAMIND_RM';
SHOW WAREHOUSES LIKE 'DATAMIND_WH';
