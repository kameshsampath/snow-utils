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

create role if not exists kamesh_demos;
alter user kameshs set DEFAULT_ROLE='kamesh_demos';
grant create database on account to role kamesh_demos;
grant create integration on account to role kamesh_demos;
grant role kamesh_demos to user kameshs;

use role kamesh_demos;
grant CREATE AUTHENTICATION POLICY ON SCHEMA openflow_demos.policies TO ROLE ACCOUNTADMIN;
