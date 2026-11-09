-- Snowflake setup for this project. Run it ONCE in a Snowflake worksheet, as ACCOUNTADMIN (or a role that can
-- create roles, users and warehouses). The flow itself never runs any of this: it only reads.
--
-- 1. Change the password below. The other names work as they are; if you change one, use the same name in .env.
-- 2. Run the whole script.
-- 3. When python setup.py (or python flow.py init) asks for your settings, enter these values:
--      warehouse BI_WH, database BI_DEMO, schema BI, role BI_READER, user BI_AGENT, and your password.

USE ROLE ACCOUNTADMIN;

CREATE WAREHOUSE IF NOT EXISTS BI_WH WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE;
CREATE DATABASE  IF NOT EXISTS BI_DEMO;
CREATE SCHEMA    IF NOT EXISTS BI_DEMO.BI;

CREATE ROLE IF NOT EXISTS BI_READER;
GRANT USAGE ON WAREHOUSE BI_WH TO ROLE BI_READER;
GRANT USAGE ON DATABASE  BI_DEMO TO ROLE BI_READER;
GRANT USAGE ON SCHEMA    BI_DEMO.BI TO ROLE BI_READER;

-- Read access to everything in the schema now and later, including the views the model step asks you to create.
GRANT SELECT ON ALL TABLES    IN SCHEMA BI_DEMO.BI TO ROLE BI_READER;
GRANT SELECT ON ALL VIEWS     IN SCHEMA BI_DEMO.BI TO ROLE BI_READER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA BI_DEMO.BI TO ROLE BI_READER;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA BI_DEMO.BI TO ROLE BI_READER;

CREATE USER IF NOT EXISTS BI_AGENT PASSWORD = 'CHANGE_ME_TO_A_LONG_PASSWORD'
  DEFAULT_ROLE = BI_READER DEFAULT_WAREHOUSE = BI_WH MUST_CHANGE_PASSWORD = FALSE;
GRANT ROLE BI_READER TO USER BI_AGENT;

-- Optional: for the sample-data quick start (QUICKSTART.md). Snowflake's free TPC-H sample data. If the first line
-- says the share already exists, ignore it. If your account has no such share, skip this block and use your own data.
CREATE DATABASE IF NOT EXISTS SNOWFLAKE_SAMPLE_DATA FROM SHARE SFC_SAMPLES.SAMPLE_DATA;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE_SAMPLE_DATA TO ROLE BI_READER;

-- Your own data lives in another database or schema? Grant the same way, for example:
--   GRANT USAGE ON DATABASE MY_DB TO ROLE BI_READER;
--   GRANT USAGE ON SCHEMA MY_DB.MY_SCHEMA TO ROLE BI_READER;
--   GRANT SELECT ON ALL TABLES IN SCHEMA MY_DB.MY_SCHEMA TO ROLE BI_READER;
