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


def do_run_setup(sa_role: str, db_name: str, script_dir: Path) -> bool:
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
        "snow",
        "sql",
        "-f",
        str(setup_sql),
        "--enable-templating",
        "ALL",
        "--role",
        "ACCOUNTADMIN",
    ]

    result = subprocess.run(cmd, env=env, capture_output=False)

    if result.returncode == 0:
        click.echo(click.style("\n✓ Setup complete!", fg="green"))
        return True
    else:
        click.echo(click.style("\n✗ Setup failed", fg="red"))
        return False


@click.command()
@click.option("--role", "-r", help="SA Role name (or set SA_ROLE env var)")
@click.option("--database", "-d", help="Database name (or set SNOW_UTILS_DB env var)")
@click.option("--run-setup", is_flag=True, help="Run setup if infrastructure missing")
@click.option("--suggest", is_flag=True, help="Output suggested defaults as JSON")
def check(role: str | None, database: str | None, run_setup: bool, suggest: bool):
    """Check if snow-utils infrastructure is set up.

    Non-interactive - all values via CLI args or env vars.
    Designed to be called by Cortex Code skills.

    Exit codes:
      0 - Infrastructure ready
      1 - Infrastructure missing (setup not requested or failed)
      2 - Error during check
    """
    script_dir = Path(__file__).parent

    user = os.environ.get("SNOWFLAKE_USER", "").upper()
    if user:
        default_role = f"{user}_SNOW_UTILS_SA"
        default_db = f"{user}_SNOW_UTILS"
    else:
        default_role = DEFAULT_ROLE
        default_db = DEFAULT_DB

    if suggest:
        role_to_check = role or os.environ.get("SA_ROLE") or default_role
        db_to_check = database or os.environ.get("SNOW_UTILS_DB") or default_db
        role_exists = check_role_exists(role_to_check)
        db_exists = check_database_exists(db_to_check)
        click.echo(
            json.dumps(
                {
                    "user": user or None,
                    "suggested_role": default_role,
                    "suggested_database": default_db,
                    "role_exists": role_exists,
                    "database_exists": db_exists,
                    "ready": role_exists and db_exists,
                }
            )
        )
        sys.exit(0)

    sa_role = role or os.environ.get("SA_ROLE") or default_role
    db_name = database or os.environ.get("SNOW_UTILS_DB") or default_db

    click.echo("Snow-utils infrastructure check\n")
    if user:
        click.echo(f"Detected user: {user}")
    click.echo(f"  SA_ROLE: {sa_role}")
    click.echo(f"  SNOW_UTILS_DB: {db_name}\n")

    db_exists = check_database_exists(db_name)
    role_exists = check_role_exists(sa_role)

    if db_exists and role_exists:
        click.echo(click.style("✓ Infrastructure ready", fg="green"))
        click.echo(f"  Database: {db_name}")
        click.echo(f"  Role: {sa_role}")

        if not check_user_has_role(sa_role):
            click.echo(
                click.style(
                    f"\n⚠ Note: You don't have {sa_role} granted to your user.",
                    fg="yellow",
                )
            )
            click.echo(f'  Run: snow sql -q "GRANT ROLE {sa_role} TO USER <your_username>"')

        sys.exit(0)

    click.echo(click.style("⚠ Infrastructure not ready", fg="yellow"))
    if not db_exists:
        click.echo(f"  ✗ Database {db_name} does not exist")
    else:
        click.echo(f"  ✓ Database {db_name} exists")

    if not role_exists:
        click.echo(f"  ✗ Role {sa_role} does not exist")
    else:
        click.echo(f"  ✓ Role {sa_role} exists")

    if not run_setup:
        click.echo(f"\nTo create infrastructure, re-run with --run-setup")
        sys.exit(1)

    click.echo(f"\nRunning setup...")
    click.echo(f"  - Role: {sa_role} (with scoped privileges)")
    click.echo(f"  - Database: {db_name}")
    click.echo(f"  - Schemas: {db_name}.NETWORKS, {db_name}.POLICIES")

    success = do_run_setup(sa_role, db_name, script_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    check()
