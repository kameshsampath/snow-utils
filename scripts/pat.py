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
Snowflake PAT (Programmatic Access Token) Manager

Sets up a service user with authentication policies and creates/rotates PATs.
Network setup is handled separately via network.py.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import click
from network import (
    assign_network_policy_to_user,
    cleanup_network_for_user,
    get_setup_network_for_user_sql,
    setup_network_for_user,
)
from snow_utils_common import (
    collect_ipv4_cidrs,
    get_snow_cli_options,
    run_snow_sql,
    run_snow_sql_stdin,
    set_masking,
    set_snow_cli_options,
)


def get_snowflake_account() -> str:
    """Get the current Snowflake account from connection test."""
    result = subprocess.run(
        ["snow", "connection", "test", "--format", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise click.ClickException(f"Failed to test connection: {result.stderr}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise click.ClickException(
            f"Invalid JSON from connection test: {e}\nOutput: {result.stdout[:500]}"
        )

    account = data.get("Account")
    if not account:
        raise click.ClickException(
            f"Account not found in connection test response: {list(data.keys())}"
        )
    return account


def get_service_user_sql(user: str, pat_role: str) -> str:
    """Generate SQL for creating service user (idempotent)."""
    return f"""USE ROLE accountadmin;
CREATE USER IF NOT EXISTS {user}
    TYPE = SERVICE
    COMMENT = 'Service user for PAT access';
GRANT ROLE {pat_role} TO USER {user};"""


def setup_service_user(user: str, pat_role: str) -> None:
    """Create service user and grant the PAT role (idempotent)."""
    click.echo(f"Setting up service user: {user}")
    sql = get_service_user_sql(user, pat_role)
    run_snow_sql_stdin(sql)
    click.echo(f"✓ Service user {user} configured with role {pat_role}")


def get_auth_policy_sql(user: str, db: str, default_expiry_days: int, max_expiry_days: int) -> str:
    """Generate SQL for creating authentication policy (idempotent)."""
    auth_policy_name = f"{user}_auth_policy".upper()

    return f"""CREATE SCHEMA IF NOT EXISTS {db}.POLICIES;
CREATE OR ALTER AUTHENTICATION POLICY {db}.POLICIES.{auth_policy_name}
    AUTHENTICATION_METHODS = ('PROGRAMMATIC_ACCESS_TOKEN')
    PAT_POLICY = (
        default_expiry_in_days = {default_expiry_days},
        max_expiry_in_days = {max_expiry_days},
        network_policy_evaluation = ENFORCED_REQUIRED
    );

ALTER USER {user} SET AUTHENTICATION POLICY {db}.POLICIES.{auth_policy_name};"""


def setup_auth_policy(user: str, db: str, default_expiry_days: int, max_expiry_days: int) -> None:
    """Create authentication policy for PAT access (idempotent)."""
    click.echo("Setting up authentication policy...")
    sql = get_auth_policy_sql(user, db, default_expiry_days, max_expiry_days)
    run_snow_sql_stdin(sql)
    click.echo("✓ Authentication policy configured")


def remove_auth_policy(user: str, db: str) -> None:
    """Remove authentication policy for a user (idempotent)."""
    auth_policy_name = f"{user}_auth_policy".upper()

    click.echo(f"Removing authentication policy: {db}.POLICIES.{auth_policy_name}")

    sql = f"""
        USE ROLE accountadmin;
        ALTER USER IF EXISTS {user} UNSET AUTHENTICATION POLICY;
        DROP AUTHENTICATION POLICY IF EXISTS {db}.POLICIES.{auth_policy_name};
    """
    run_snow_sql_stdin(sql, check=False)
    click.echo("✓ Authentication policy removed")


def get_existing_pat(user: str, pat_name: str) -> str | None:
    """Check if a PAT with the given name exists for the user."""
    result = run_snow_sql(f"SHOW USER PATS FOR USER {user}")

    if not result:
        return None

    for pat in result:
        if pat.get("name", "").lower() == pat_name.lower():
            return pat.get("name")

    return None


def get_pat_sql(user: str, pat_role: str, pat_name: str) -> str:
    """Generate SQL for creating PAT."""
    return f"ALTER USER IF EXISTS {user} ADD PAT {pat_name} ROLE_RESTRICTION = {pat_role};"


def create_or_rotate_pat(user: str, pat_role: str, pat_name: str, rotate: bool = False) -> str:
    """Create a new PAT or rotate an existing one (idempotent for rotate=True)."""
    existing = get_existing_pat(user, pat_name)

    if existing and not rotate:
        click.echo(f"PAT '{pat_name}' exists. Removing and recreating (--no-rotate)...")
        remove_query = f"ALTER USER IF EXISTS {user} REMOVE PAT {pat_name}"
        run_snow_sql(remove_query)
        click.echo(f"✓ Removed existing PAT '{pat_name}'")
        existing = None

    if existing:
        click.echo(f"Rotating PAT for service user {user}...")
        query = f"ALTER USER IF EXISTS {user} ROTATE PAT {pat_name}"
    else:
        click.echo(f"Creating new PAT for service user {user} with role restriction {pat_role}...")
        query = f"ALTER USER IF EXISTS {user} ADD PAT {pat_name} ROLE_RESTRICTION = {pat_role}"

    result = run_snow_sql(query)

    if not result or not result[0].get("token_secret"):
        raise click.ClickException("Failed to get PAT token from response")

    token = result[0]["token_secret"]
    click.echo("✓ PAT created/rotated successfully")
    return token


def remove_pat(user: str, pat_name: str) -> None:
    """Remove a PAT from a user (idempotent)."""
    click.echo(f"Removing PAT '{pat_name}' from user {user}...")

    existing = get_existing_pat(user, pat_name)
    if not existing:
        click.echo(f"⚠ PAT '{pat_name}' not found for user {user}")
        return

    sql = f"ALTER USER IF EXISTS {user} REMOVE PAT {pat_name}"
    run_snow_sql(sql)
    click.echo(f"✓ Removed PAT '{pat_name}'")


def remove_service_user(user: str) -> None:
    """Drop the service user (idempotent)."""
    click.echo(f"Dropping service user: {user}")

    sql = f"""
        USE ROLE accountadmin;
        DROP USER IF EXISTS {user};
    """
    run_snow_sql_stdin(sql)
    click.echo(f"✓ Service user {user} dropped")


def _escape_env_value(value: str) -> str:
    """Escape a value for safe storage in .env file."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def update_env(env_path: Path, user: str, password: str, pat_role: str) -> None:
    """Update .env file with the new SNOWFLAKE_PASSWORD and SA_ROLE."""
    if not env_path.exists():
        click.echo(f"⚠ {env_path} not found, skipping update")
        return

    content = env_path.read_text()

    backup_path = env_path.with_suffix(".env.bak")
    shutil.copy(env_path, backup_path)

    password_pattern = r"^SNOWFLAKE_PASSWORD=.*$"
    password_replacement = f"SNOWFLAKE_PASSWORD={_escape_env_value(password)}"

    if re.search(password_pattern, content, re.MULTILINE):
        new_content = re.sub(password_pattern, password_replacement, content, flags=re.MULTILINE)
    else:
        new_content = content.rstrip() + f"\n{password_replacement}\n"

    user_pattern = r"^SA_USER=.*$"
    user_replacement = f"SA_USER={_escape_env_value(user)}"

    if re.search(user_pattern, new_content, re.MULTILINE):
        new_content = re.sub(user_pattern, user_replacement, new_content, flags=re.MULTILINE)
    else:
        new_content = new_content.rstrip() + f"\n{user_replacement}\n"

    role_pattern = r"^SA_ROLE=.*$"
    role_replacement = f"SA_ROLE={_escape_env_value(pat_role)}"

    if re.search(role_pattern, new_content, re.MULTILINE):
        new_content = re.sub(role_pattern, role_replacement, new_content, flags=re.MULTILINE)
    else:
        new_content = new_content.rstrip() + f"\n{role_replacement}\n"

    env_path.write_text(new_content)
    click.echo(f"✓ Updated {env_path} with new SNOWFLAKE_PASSWORD, SA_USER, and SA_ROLE")


def clear_env(env_path: Path) -> None:
    """Clear PAT credentials from .env file."""
    if not env_path.exists():
        click.echo(f"⚠ {env_path} not found, skipping")
        return

    content = env_path.read_text()

    backup_path = env_path.with_suffix(".env.bak")
    shutil.copy(env_path, backup_path)
    click.echo(f"✓ Created backup: {backup_path}")

    password_pattern = r"^SNOWFLAKE_PASSWORD=.*$"
    new_content = re.sub(password_pattern, 'SNOWFLAKE_PASSWORD=""', content, flags=re.MULTILINE)

    env_path.write_text(new_content)
    click.echo(f"✓ Cleared SNOWFLAKE_PASSWORD in {env_path}")


def verify_connection(user: str, password: str, pat_role: str) -> None:
    """Verify the PAT connection works."""
    click.echo("Verifying connection with PAT...")

    account = get_snowflake_account()

    cmd = [
        "snow",
        "sql",
        *get_snow_cli_options().get_flags(),
        "-x",
        "--user",
        user,
        "--account",
        account,
        "--role",
        pat_role,
        "-q",
        "SELECT current_timestamp()",
    ]

    if get_snow_cli_options().debug:
        click.echo(f"[DEBUG] Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        env={**os.environ, "SNOWFLAKE_PASSWORD": password},
        capture_output=True,
        text=True,
    )

    if get_snow_cli_options().debug and result.stderr:
        click.echo(f"[DEBUG] stderr: {result.stderr}")

    if result.returncode != 0:
        raise click.ClickException(f"Connection verification failed: {result.stderr}")

    click.echo("✓ Connection verified successfully")


@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, debug: bool) -> None:
    """
    Snowflake PAT Manager - Manage service users with programmatic access tokens.

    \b
    Commands:
        create  - Create/rotate PAT for service user
        rotate  - Rotate existing PAT (keep policies)
        verify  - Test PAT connection
        remove  - Remove PAT and associated objects
    """
    set_snow_cli_options(verbose=verbose, debug=debug)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command(name="create")
@click.option("--user", "-u", envvar="SA_USER", required=True, help="Service account user name")
@click.option("--role", "-r", envvar="SA_ROLE", required=True, help="Role restriction for the PAT")
@click.option("--db", "-d", envvar="SNOW_UTILS_DB", required=True, help="Database for PAT objects")
@click.option("--pat-name", default=None, envvar="PAT_NAME", help="Name for the PAT token")
@click.option("--rotate/--no-rotate", default=True, help="Rotate existing PAT (default: True)")
@click.option(
    "--env-path",
    type=click.Path(path_type=Path),
    default=Path(".env"),
    help=".env file path",
)
@click.option("--skip-verify", is_flag=True, help="Skip connection verification")
@click.option(
    "--allow-local/--no-local",
    "allow_local",
    default=True,
    help="Include local IP (default: True)",
)
@click.option("--allow-gh", is_flag=True, default=False, help="Include GitHub Actions IPs")
@click.option("--allow-google", is_flag=True, default=False, help="Include Google IPs")
@click.option("--extra-cidrs", multiple=True, help="Additional CIDRs (can be repeated)")
@click.option("--default-expiry-days", default=45, type=int, help="Default PAT expiry days")
@click.option("--max-expiry-days", default=90, type=int, help="Maximum PAT expiry days")
@click.option("--dry-run", is_flag=True, help="Preview without making changes")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing network rule/policy (CREATE OR REPLACE)",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def create_command(
    user: str,
    role: str,
    db: str,
    pat_name: str | None,
    rotate: bool,
    env_path: Path,
    skip_verify: bool,
    allow_local: bool,
    allow_gh: bool,
    allow_google: bool,
    extra_cidrs: tuple[str, ...],
    default_expiry_days: int,
    max_expiry_days: int,
    dry_run: bool,
    force: bool,
    output: str,
) -> None:
    """
    Create or rotate a PAT for a service user.

    Network policy is REQUIRED for PAT security (Snowflake best practice).
    By default, includes local IP. Use --allow-gh/--allow-google for CI/CD access.

    \b
    Steps:
    1. Create service user (if not exists)
    2. Create network rule and policy (REQUIRED)
    3. Create authentication policy
    4. Create or rotate PAT
    5. Update .env file
    6. Verify connection

    \b
    Examples:
        # Basic usage - local IP only (most secure)
        pat.py create --user my_sa --role demo_role --db my_db

        # Include GitHub Actions IPs for CI/CD
        pat.py create --user ci_sa --role ci_role --db my_db --allow-gh

        # Multiple IP sources
        pat.py create --user my_sa --role demo_role --db my_db --allow-gh --allow-google
    """
    if not pat_name:
        pat_name = f"{user}_pat".upper()

    cidrs = collect_ipv4_cidrs(
        with_local=allow_local,
        with_gh=allow_gh,
        with_google=allow_google,
        extra_cidrs=list(extra_cidrs) if extra_cidrs else None,
    )
    if not cidrs:
        raise click.ClickException(
            "Network policy required for PAT security. "
            "Use --allow-local (default), --allow-gh, --allow-google, or --extra-cidrs"
        )

    def build_result(status: str, token: str | None = None) -> dict:
        result = {
            "status": status,
            "user": user,
            "pat_name": pat_name,
            "pat_role": role,
            "database": db,
            "resources": {
                "auth_policy": f"{db}.POLICIES.{user}_AUTH_POLICY".upper(),
                "network_rule": f"{db}.NETWORKS.{user}_NETWORK_RULE".upper(),
                "network_policy": f"{user}_NETWORK_POLICY".upper(),
            },
            "cidrs_count": len(cidrs),
        }
        if token:
            result["token"] = token
        return result

    if output == "json" and dry_run:
        result = build_result("dry_run")
        result["cidrs"] = cidrs
        click.echo(json.dumps(result, indent=2))
        return

    if output == "text":
        click.echo("=" * 50)
        click.echo("Snowflake PAT Manager")
        if dry_run:
            click.echo("  [DRY RUN]")
        click.echo("=" * 50)
        click.echo(f"User:     {user}")
        click.echo(f"Role:     {role}")
        click.echo(f"Database: {db}")
        click.echo(f"PAT Name: {pat_name}")
        click.echo(f"CIDRs:    {len(cidrs)} entries")
        click.echo()

    if dry_run:
        set_masking(False)
        click.echo("SQL that would be executed:")
        click.echo("─" * 60)
        click.echo("-- Step 1: Create service user")
        click.echo(get_service_user_sql(user, role))
        click.echo()
        click.echo("-- Step 2: Create network rule and policy")
        click.echo(get_setup_network_for_user_sql(user=user, db=db, cidrs=cidrs, force=force))
        click.echo()
        click.echo("-- Step 3: Create authentication policy")
        click.echo(get_auth_policy_sql(user, db, default_expiry_days, max_expiry_days))
        click.echo()
        click.echo("-- Step 4: Create PAT")
        click.echo(get_pat_sql(user, role, pat_name))
        click.echo("─" * 60)
        return

    setup_service_user(user=user, pat_role=role)

    click.echo(f"Setting up network rule and policy ({len(cidrs)} CIDRs)...")
    rule_fqn, policy_name = setup_network_for_user(user=user, db=db, cidrs=cidrs, force=force)
    click.echo(f"✓ Network rule: {rule_fqn}")
    click.echo(f"✓ Network policy: {policy_name}")
    assign_network_policy_to_user(user, policy_name)
    click.echo(f"✓ Assigned network policy to user {user}")

    setup_auth_policy(
        user=user,
        db=db,
        default_expiry_days=default_expiry_days,
        max_expiry_days=max_expiry_days,
    )

    password = create_or_rotate_pat(user=user, pat_role=role, pat_name=pat_name, rotate=rotate)

    if output == "text":
        update_env(env_path=env_path, user=user, password=password, pat_role=role)

    if not skip_verify and output == "text":
        verify_connection(user=user, password=password, pat_role=role)

    if output == "json":
        result = build_result("success", password)
        result["cidrs"] = cidrs
        result["env_file"] = str(env_path)
        click.echo(json.dumps(result, indent=2))
        return

    click.echo()
    click.echo("=" * 50)
    click.echo("✓ PAT setup completed successfully!")
    click.echo("=" * 50)


@cli.command(name="remove")
@click.option("--user", "-u", envvar="SA_USER", required=True, help="Service account user name")
@click.option("--db", "-d", envvar="SNOW_UTILS_DB", required=True, help="Database for PAT objects")
@click.option("--pat-name", default=None, envvar="PAT_NAME", help="Name of the PAT to remove")
@click.option("--drop-user", is_flag=True, help="Also drop the service user")
@click.option("--pat-only", is_flag=True, help="Only remove PAT, keep policies")
@click.option(
    "--env-path",
    type=click.Path(path_type=Path),
    default=Path(".env"),
    help=".env file path",
)
@click.confirmation_option(prompt="Remove PAT and associated objects?")
def remove_command(
    user: str,
    db: str,
    pat_name: str | None,
    drop_user: bool,
    pat_only: bool,
    env_path: Path,
) -> None:
    """
    Remove PAT and associated objects for a service user.

    \b
    Steps:
    1. Remove PAT
    2. Remove network policy and rule (unless --pat-only)
    3. Remove authentication policy (unless --pat-only)
    4. Drop service user (if --drop-user)
    5. Clear .env credentials
    """
    click.echo("=" * 50)
    click.echo("Snowflake PAT Manager - Remove")
    click.echo("=" * 50)
    click.echo()

    if not pat_name:
        pat_name = f"{user}_pat".upper()

    click.echo(f"User:     {user}")
    click.echo(f"Database: {db}")
    click.echo(f"PAT Name: {pat_name}")
    click.echo()

    click.echo("─" * 40)
    click.echo("Step 1: Remove PAT")
    click.echo("─" * 40)
    remove_pat(user=user, pat_name=pat_name)
    click.echo()

    if not pat_only:
        click.echo("─" * 40)
        click.echo("Step 2: Remove Network Policy")
        click.echo("─" * 40)
        cleanup_network_for_user(user=user, db=db)
        click.echo("✓ Network policy and rule removed")
        click.echo()

        click.echo("─" * 40)
        click.echo("Step 3: Remove Authentication Policy")
        click.echo("─" * 40)
        remove_auth_policy(user=user, db=db)
        click.echo()

    if drop_user:
        click.echo("─" * 40)
        click.echo("Step 4: Drop Service User")
        click.echo("─" * 40)
        remove_service_user(user=user)
        click.echo()

    click.echo("─" * 40)
    click.echo("Step 5: Clear .env Credentials")
    click.echo("─" * 40)
    clear_env(env_path=env_path)
    click.echo()

    click.echo("=" * 50)
    click.echo("✓ PAT removal completed!")
    click.echo("=" * 50)


@cli.command(name="rotate")
@click.option("--user", "-u", required=True, envvar="SA_USER", help="Service account user name")
@click.option("--role", "-r", required=True, envvar="SA_ROLE", help="Role restriction for the PAT")
@click.option("--pat-name", envvar="SA_PAT", help="Name for the PAT token")
@click.option(
    "--env-path", type=click.Path(path_type=Path), default=Path(".env"), help=".env file path"
)
@click.option("--skip-verify", is_flag=True, help="Skip connection verification")
@click.option(
    "-o", "--output", type=click.Choice(["text", "json"]), default="text", help="Output format"
)
def rotate_command(
    user: str,
    role: str,
    pat_name: str | None,
    env_path: Path,
    skip_verify: bool,
    output: str,
) -> None:
    """
    Rotate an existing PAT for a service user.

    This regenerates the PAT token while keeping all policies intact.
    The new token will be saved to the .env file.

    \b
    Examples:
        # Rotate PAT with defaults
        pat.py rotate --user my_sa --role demo_role

        # Rotate and skip verification
        pat.py rotate --user my_sa --role demo_role --skip-verify
    """
    if not pat_name:
        pat_name = f"{user}_pat".upper()

    click.echo("=" * 50)
    click.echo("Snowflake PAT Manager - Rotate")
    click.echo("=" * 50)
    click.echo(f"User:     {user}")
    click.echo(f"Role:     {role}")
    click.echo(f"PAT Name: {pat_name}")
    click.echo()

    existing = get_existing_pat(user, pat_name)
    if not existing:
        raise click.ClickException(
            f"PAT '{pat_name}' not found for user {user}. Use 'create' command first."
        )

    password = create_or_rotate_pat(user=user, pat_role=role, pat_name=pat_name, rotate=True)

    if output == "text":
        update_env(env_path=env_path, user=user, password=password, pat_role=role)

    if not skip_verify:
        verify_connection(user=user, password=password, pat_role=role)

    if output == "json":
        result = {
            "status": "rotated",
            "user": user,
            "pat_name": pat_name,
            "pat_role": role,
            "token": password,
        }
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo()
        click.echo("=" * 50)
        click.echo("✓ PAT rotated successfully!")
        click.echo("=" * 50)


@cli.command(name="verify")
@click.option("--user", "-u", required=True, envvar="SA_USER", help="Service account user name")
@click.option("--role", "-r", required=True, envvar="SA_ROLE", help="Role for the PAT")
@click.option("--password", "-p", envvar="SA_PAT", help="PAT token (or use SA_PAT env var)")
@click.option(
    "--env-path",
    type=click.Path(path_type=Path),
    default=Path(".env"),
    help=".env file to read token from",
)
def verify_command(
    user: str,
    role: str,
    password: str | None,
    env_path: Path,
) -> None:
    """
    Verify PAT connection works correctly.

    Tests the PAT by connecting to Snowflake and running a simple query.
    The token can be provided via --password, SA_PAT env var, or read from .env file.

    \b
    Examples:
        # Verify using SA_PAT env var
        pat.py verify --user my_sa --role demo_role

        # Verify with explicit token
        pat.py verify --user my_sa --role demo_role --password "token..."

        # Verify reading from .env
        pat.py verify --user my_sa --role demo_role --env-path .env
    """
    if not password:
        if env_path.exists():
            content = env_path.read_text()
            import re

            match = re.search(
                r'^SNOWFLAKE_PASSWORD\s*=\s*["\']?([^"\'#\n]+)["\']?', content, re.MULTILINE
            )
            if match:
                password = match.group(1).strip()
                click.echo(f"Using token from {env_path}")

    if not password:
        raise click.ClickException(
            "No PAT token provided. Use --password, SA_PAT env var, or ensure .env contains SNOWFLAKE_PASSWORD"
        )

    click.echo("=" * 50)
    click.echo("Snowflake PAT Manager - Verify")
    click.echo("=" * 50)
    click.echo(f"User: {user}")
    click.echo(f"Role: {role}")
    click.echo()

    verify_connection(user=user, password=password, pat_role=role)

    click.echo()
    click.echo("=" * 50)
    click.echo("✓ PAT verification successful!")
    click.echo("=" * 50)


if __name__ == "__main__":
    cli()
