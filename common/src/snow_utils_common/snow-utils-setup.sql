-- Copyright 2026 Kamesh Sampath
-- Generated with Cortex Code
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

--!jinja

-- =============================================================================
-- Snow-Utils Setup Script
-- =============================================================================
-- Creates the SA role and database with SCOPED privileges (secure-first).
--
-- Environment Variables (from .env):
--   SA_ROLE        - Name of the service account role to create
--   SNOW_UTILS_DB  - Name of the database to create
--   SNOWFLAKE_USER - Current user (will be granted SA_ROLE)
--   SA_ADMIN_ROLE  - Admin role to run setup (e.g., ACCOUNTADMIN)
--
-- Security Model:
--   SA_ROLE gets ONLY database-scoped privileges:
--     - CREATE NETWORK RULE (in SNOW_UTILS_DB.NETWORKS)
--     - Database/schema ownership
--
--   Account-level operations use SA_ADMIN_ROLE:
--     - CREATE USER (service accounts)
--     - CREATE NETWORK POLICY
--     - CREATE AUTHENTICATION POLICY
--     - CREATE EXTERNAL VOLUME
--     - ALTER USER (policy assignments)
--
-- Prerequisites:
--   - Must be run by SA_ADMIN_ROLE (default: ACCOUNTADMIN)
--
-- Usage:
--   snow sql -f snow-utils-setup.sql --enable-templating ALL --role <SA_ADMIN_ROLE>
-- =============================================================================

USE ROLE <% ctx.env.SA_ADMIN_ROLE %>;

-- =============================================================================
-- Step 1: Create SA Role (scoped privileges only)
-- =============================================================================

CREATE ROLE IF NOT EXISTS <% ctx.env.SA_ROLE %>
    COMMENT = 'Role for snow-utils DB operations (scoped privileges only)';

-- =============================================================================
-- Step 2: Create Database and Schemas
-- =============================================================================

CREATE DATABASE IF NOT EXISTS <% ctx.env.SNOW_UTILS_DB %>
    COMMENT = 'Database for snow-utils objects (network rules, etc.)';

CREATE SCHEMA IF NOT EXISTS <% ctx.env.SNOW_UTILS_DB %>.NETWORKS
    COMMENT = 'Schema for network rules';
CREATE SCHEMA IF NOT EXISTS <% ctx.env.SNOW_UTILS_DB %>.POLICIES
    COMMENT = 'Schema for authentication policies (created by SA_ADMIN_ROLE)';

-- =============================================================================
-- Step 3: Grant Database and Schema Ownership to SA Role
-- =============================================================================

GRANT OWNERSHIP ON DATABASE <% ctx.env.SNOW_UTILS_DB %> TO ROLE <% ctx.env.SA_ROLE %> COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %> COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.POLICIES TO ROLE <% ctx.env.SA_ROLE %> COPY CURRENT GRANTS;

-- =============================================================================
-- Step 4: Schema-Level Privileges for Network Rules
-- =============================================================================
-- Network RULES are database objects (scoped to SA_ROLE).
-- Network POLICIES are account objects (remain with ACCOUNTADMIN).

GRANT CREATE NETWORK RULE ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %>;
GRANT USAGE ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %>;

-- =============================================================================
-- Step 5: Future Grants for New Objects
-- =============================================================================

GRANT ALL PRIVILEGES ON FUTURE NETWORK RULES IN SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %>;

-- =============================================================================
-- Step 6: Grant SA Role to Current User and SYSADMIN
-- =============================================================================

GRANT ROLE <% ctx.env.SA_ROLE %> TO USER <% ctx.env.SNOWFLAKE_USER %>;
GRANT ROLE <% ctx.env.SA_ROLE %> TO ROLE SYSADMIN;

-- =============================================================================
-- Verification
-- =============================================================================
-- SHOW GRANTS TO ROLE <% ctx.env.SA_ROLE %>;
-- SHOW GRANTS ON DATABASE <% ctx.env.SNOW_UTILS_DB %>;

SELECT 'Snow-utils setup complete. Role <% ctx.env.SA_ROLE %> granted to <% ctx.env.SNOWFLAKE_USER %>.' AS status;
