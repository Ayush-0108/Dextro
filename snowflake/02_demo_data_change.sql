-- =====================================================================================
-- DataMind demo: the answer changes when the data changes (+ Time Travel before/after)
-- Run step by step in a Snowsight worksheet while the app is open.
-- =====================================================================================
USE ROLE DATAMIND_ADMIN;
USE WAREHOUSE DATAMIND_WH;
USE SCHEMA DATAMIND_DB.TPCH;

-- STEP 0 — in the app, ask:
--   "Which customer generated the most revenue from orders placed in July 1998?"
--   Note the answer and its Snowflake query id.

-- STEP 1 — remember the moment before the change
SET before_change = CURRENT_TIMESTAMP();

-- STEP 2 — one very large new order for Customer#000000001
INSERT INTO ORDERS (O_ORDERKEY, O_CUSTKEY, O_ORDERSTATUS, O_TOTALPRICE, O_ORDERDATE, O_ORDERPRIORITY,
                    O_CLERK, O_SHIPPRIORITY, O_COMMENT)
VALUES (9000001, 1, 'O', 5400000.00, '1998-07-15', '1-URGENT', 'Clerk#000000001', 0, 'DataMind demo order');

INSERT INTO LINEITEM (L_ORDERKEY, L_PARTKEY, L_SUPPKEY, L_LINENUMBER, L_QUANTITY, L_EXTENDEDPRICE, L_DISCOUNT,
                      L_TAX, L_RETURNFLAG, L_LINESTATUS, L_SHIPDATE, L_COMMITDATE, L_RECEIPTDATE,
                      L_SHIPINSTRUCT, L_SHIPMODE, L_COMMENT)
VALUES (9000001, 1, 2, 1, 50, 5000000.00, 0.00, 0.08, 'N', 'O', '1998-07-20', '1998-07-25', '1998-07-28',
        'DELIVER IN PERSON', 'AIR', 'DataMind demo line');

-- STEP 3 — ask the same question in the app again: Customer#000000001 now leads, with a NEW query id.

-- STEP 4 — Time Travel: the same calculation as of before the change vs now
SELECT 'before' AS version, c.C_NAME, SUM(l.L_EXTENDEDPRICE * (1 - l.L_DISCOUNT)) AS revenue
FROM LINEITEM AT(TIMESTAMP => $before_change) AS l
JOIN ORDERS AT(TIMESTAMP => $before_change) AS o ON l.L_ORDERKEY = o.O_ORDERKEY
JOIN CUSTOMER AS c ON o.O_CUSTKEY = c.C_CUSTKEY
WHERE o.O_ORDERDATE BETWEEN '1998-07-01' AND '1998-07-31'
GROUP BY c.C_NAME
QUALIFY ROW_NUMBER() OVER (ORDER BY revenue DESC) = 1
UNION ALL
SELECT 'after', c.C_NAME, SUM(l.L_EXTENDEDPRICE * (1 - l.L_DISCOUNT))
FROM LINEITEM AS l
JOIN ORDERS AS o ON l.L_ORDERKEY = o.O_ORDERKEY
JOIN CUSTOMER AS c ON o.O_CUSTKEY = c.C_CUSTKEY
WHERE o.O_ORDERDATE BETWEEN '1998-07-01' AND '1998-07-31'
GROUP BY c.C_NAME
QUALIFY ROW_NUMBER() OVER (ORDER BY SUM(l.L_EXTENDEDPRICE * (1 - l.L_DISCOUNT)) DESC) = 1;

-- STEP 5 — revert so the evaluation set and other demos see the original data
DELETE FROM LINEITEM WHERE L_ORDERKEY = 9000001;
DELETE FROM ORDERS WHERE O_ORDERKEY = 9000001;
