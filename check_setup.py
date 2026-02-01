#!/usr/bin/env python3
# Copyright 2026 Kamesh Sampath
# Generated with Cortex Code
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Pre-flight check for snow-utils infrastructure.

Checks if SNOW_UTILS_DB and SA_ROLE exist, and offers to create them if missing.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import click

DEFAULT_ROLE = "SNOW_UTILS_SA"
DEFAULT_DB = "SNOW_UTILS"


def run_sql(query: str) -> list | None:
    """Execute SQL and return parsed JSON result. Uses active connection from env."""
    cmd = ["snow", "sql", "--query", query, "--format", "json"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
    return None


def check_database_exists(db_name: str) -> bool:
    """Check if a database exists."""
    try:
        result = run_sql(f"SHOW DATABASES LIKE '{db_name}'")
        return result is not None and len(result) > 0
    except Exception:
        return False


def check_role_exists(role_name: str) -> bool:
    """Check if a role exists."""
    try:
        result = run_sql(f"SHOW ROLES LIKE '{role_name}'")
        return result is not None and len(result) > 0
    except Exception:
        return False


def check_user_has_role(role_name: str) -> bool:
    """Check if current user has the specified role granted."""
    try:
        result = run_sql("SELECT CURRENT_AVAILABLE_ROLES() AS roles")
        if result and len(result) > 0:
            roles_str = result[0].get("ROLES", "[]")
            roles = json.loads(roles_str) if isinstance(roles_str, str) else roles_str
            return role_name.upper() in [r.upper() for r in roles]
    except Exception:
        pass
    return False


def run_setup(sa_role: str, db_name: str, script_dir: Path) -> bool:
    """Run the setup script with ACCOUNTADMIN."""
    setup_sql = script_dir / "snow-utils-setup.sql"
    if not setup_sql.exists():
        click.echo(click.style(f"Setup script not found: {setup_sql}", fg="red"))
        return False

    click.echo(f"\nRunning setup with ACCOUNTADMIN...")
    click.echo(f"  SA_ROLE: {sa_role}")
    click.echo(f"  SNOW_UTILS_DB: {db_name}")
    click.echo()

    env = os.environ.copy()
    env["SA_ROLE"] = sa_role
    env["SNOW_UTILS_DB"] = db_name

    cmd = [
        "snow", "sql",
        "-f", str(setup_sql),
        "--templating", "all",
        "--role", "ACCOUNTADMIN"
    ]

    result = subprocess.run(cmd, env=env, capture_output=False)

    if result.returncode == 0:
        click.echo(click.style("\n✓ Setup complete!", fg="green"))
        return True
    else:
        click.echo(click.style("\n✗ Setup failed", fg="red"))
        return False


@click.command()
@click.option("--quiet", "-q", is_flag=True, help="Suppress output, exit 0 if ready, 1 if not")
def check(quiet: bool):
    """Check if snow-utils infrastructure is set up.
    
    Prompts interactively for SA_ROLE and SNOW_UTILS_DB values.
    Uses the active Snowflake connection (set via SNOWFLAKE_DEFAULT_CONNECTION_NAME).
    
    Exit codes:
      0 - Infrastructure ready
      1 - Infrastructure missing (and setup declined or failed)
      2 - Error during check
    """
    script_dir = Path(__file__).parent

    if quiet:
        # Quiet mode - use defaults, no prompts
        role = os.environ.get("SA_ROLE") or DEFAULT_ROLE
        db = os.environ.get("SNOW_UTILS_DB") or DEFAULT_DB
        db_exists = check_database_exists(db)
        role_exists = check_role_exists(role)
        sys.exit(0 if (db_exists and role_exists) else 1)

    # Interactive mode - always prompt
    click.echo("Snow-utils infrastructure check\n")
    role = click.prompt("SA Role name", default=DEFAULT_ROLE)
    db = click.prompt("Database name", default=DEFAULT_DB)

    click.echo(f"\nChecking infrastructure...")
    click.echo(f"  SA_ROLE: {role}")
    click.echo(f"  SNOW_UTILS_DB: {db}\n")

    db_exists = check_database_exists(db)
    role_exists = check_role_exists(role)

    if db_exists and role_exists:
        click.echo(click.style("✓ Infrastructure ready", fg="green"))
        click.echo(f"  Database: {db}")
        click.echo(f"  Role: {role}")

        if not check_user_has_role(role):
            click.echo(click.style(f"\n⚠ Note: You don't have {role} granted to your user.", fg="yellow"))
            click.echo(f"  Run: snow sql -q \"GRANT ROLE {role} TO USER <your_username>\"")

        sys.exit(0)

    click.echo(click.style("⚠ Infrastructure not ready", fg="yellow"))
    if not db_exists:
        click.echo(f"  ✗ Database {db} does not exist")
    else:
        click.echo(f"  ✓ Database {db} exists")

    if not role_exists:
        click.echo(f"  ✗ Role {role} does not exist")
    else:
        click.echo(f"  ✓ Role {role} exists")

    click.echo(f"\nSetup will create:")
    click.echo(f"  - Role: {role} (with scoped privileges)")
    click.echo(f"  - Database: {db}")
    click.echo(f"  - Schemas: {db}.NETWORKS, {db}.POLICIES")
    click.echo(f"\nRequires: ACCOUNTADMIN role")

    should_setup = click.confirm("\nRun setup now?", default=True)

    if should_setup:
        success = run_setup(role, db, script_dir)
        sys.exit(0 if success else 1)
    else:
        click.echo("\nTo run setup manually:")
        click.echo(f"  snow sql -f snow-utils-setup.sql --templating all --role ACCOUNTADMIN")
        sys.exit(1)


if __name__ == "__main__":
    check()
