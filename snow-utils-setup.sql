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
-- Creates the SA role and database with required schemas and grants.
--
-- Environment Variables (from .env):
--   SA_ROLE - Name of the service account role to create
--   PAT_OBJECTS_DB - Name of the database to create
--
-- Prerequisites:
--   - Must be run by ACCOUNTADMIN or role with CREATE ROLE privilege
--   - After setup, grant the SA role to users who need to run snow-utils
--
-- Usage:
--   task snow-utils:setup
--   task snow-utils:setup SA_ROLE=MY_SA_ROLE PAT_OBJECTS_DB=MY_DB
--   snow sql -f snow-utils-setup.sql --templating=all --env SA_ROLE=X PAT_OBJECTS_DB=Y
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- =============================================================================
-- Step 1: Create SA Role
-- =============================================================================

CREATE ROLE IF NOT EXISTS <% ctx.env.SA_ROLE %>
    COMMENT = 'Role for snow-utils operations (scoped privileges, no grant delegation)';

-- =============================================================================
-- Step 2: Create Database and Schemas
-- =============================================================================

CREATE DATABASE IF NOT EXISTS <% ctx.env.SNOW_UTILS_DB %>
    COMMENT = 'Database for snow-utils objects (network rules, policies, etc.)';

CREATE SCHEMA IF NOT EXISTS <% ctx.env.SNOW_UTILS_DB %>.NETWORKS
    COMMENT = 'Schema for network rules';
CREATE SCHEMA IF NOT EXISTS <% ctx.env.SNOW_UTILS_DB %>.POLICIES
    COMMENT = 'Schema for authentication policies';

-- =============================================================================
-- Step 3: Grant Database and Schema Ownership to SA Role
-- =============================================================================

GRANT OWNERSHIP ON DATABASE <% ctx.env.SNOW_UTILS_DB %> TO ROLE <% ctx.env.SA_ROLE %> COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %> COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.POLICIES TO ROLE <% ctx.env.SA_ROLE %> COPY CURRENT GRANTS;

-- =============================================================================
-- Step 4: Account-Level Privileges for External Volume Management
-- =============================================================================

GRANT CREATE EXTERNAL VOLUME ON ACCOUNT TO ROLE <% ctx.env.SA_ROLE %>;

-- =============================================================================
-- Step 5: Account-Level Privileges for User and Policy Management
-- =============================================================================
-- Note: CREATE USER cannot be restricted to TYPE=SERVICE only per Snowflake docs.
-- This is a known limitation - the SA role can create any user type.

GRANT CREATE USER ON ACCOUNT TO ROLE <% ctx.env.SA_ROLE %>;
GRANT CREATE NETWORK POLICY ON ACCOUNT TO ROLE <% ctx.env.SA_ROLE %>;

-- =============================================================================
-- Step 6: Schema-Level Privileges for Network Rules
-- =============================================================================

GRANT CREATE NETWORK RULE ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %>;
GRANT USAGE ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %>;

-- =============================================================================
-- Step 7: Schema-Level Privileges for Authentication Policies
-- =============================================================================

GRANT CREATE AUTHENTICATION POLICY ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.POLICIES TO ROLE <% ctx.env.SA_ROLE %>;
GRANT USAGE ON SCHEMA <% ctx.env.SNOW_UTILS_DB %>.POLICIES TO ROLE <% ctx.env.SA_ROLE %>;

-- =============================================================================
-- Step 8: Grant SA Role to SYSADMIN (Role Hierarchy)
-- =============================================================================

GRANT ROLE <% ctx.env.SA_ROLE %> TO ROLE SYSADMIN;

-- =============================================================================
-- Step 9: Future Grants for New Objects
-- =============================================================================

GRANT ALL PRIVILEGES ON FUTURE NETWORK RULES IN SCHEMA <% ctx.env.SNOW_UTILS_DB %>.NETWORKS TO ROLE <% ctx.env.SA_ROLE %>;

-- =============================================================================
-- Verification
-- =============================================================================
-- SHOW GRANTS TO ROLE <% ctx.env.SA_ROLE %>;
-- SHOW GRANTS ON DATABASE <% ctx.env.SNOW_UTILS_DB %>;

SELECT 'Snow-utils setup complete. Role <% ctx.env.SA_ROLE %> with database <% ctx.env.SNOW_UTILS_DB %> created.' AS status;
