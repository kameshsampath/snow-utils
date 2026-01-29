#!/usr/bin/env python3
"""
Snowflake PAT (Programmatic Access Token) Manager

Sets up a service user with network policies, authentication policies,
and creates/rotates PATs for programmatic access.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import click
import requests

from snow_common import (
    get_snow_cli_options,
    run_snow_sql,
    run_snow_sql_stdin,
    set_snow_cli_options,
)


def get_local_ip() -> str:
    """Get the local public IP address with /32 CIDR suffix."""
    try:
        # Use a reliable IP echo service
        response = requests.get("https://api.ipify.org", timeout=10)
        response.raise_for_status()
        return f"{response.text.strip()}/32"
    except requests.RequestException as e:
        raise click.ClickException(f"Failed to get local IP: {e}")


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


def setup_service_user(user: str, pat_role: str) -> None:
    """Create service user and grant the PAT role."""
    click.echo(f"Setting up service user: {user}")

    sql = f"""
        USE ROLE accountadmin;
        CREATE USER IF NOT EXISTS {user}
            TYPE = SERVICE
            COMMENT = 'Service user for PAT access';
        GRANT ROLE {pat_role} TO USER {user};
    """
    run_snow_sql_stdin(sql)
    click.echo(f"✓ Service user {user} configured with role {pat_role}")


def setup_network_policy(user: str, admin_role: str, db: str, local_ip: str) -> None:
    """Create network rule and policy for the service user using admin_role."""

    # Derive policy names from user
    network_rule_name = f"{user}_network_rule".upper()
    network_policy_name = f"{user}_network_policy".upper()
    click.echo(f"Setting up network policy for user {user}")
    click.echo(f"Using admin role: {admin_role}")
    click.echo(f"Network rule: {db}.networks.{network_rule_name}")
    click.echo(f"Network policy: {network_policy_name}")

    # First, unset and drop any existing network policy (ignore errors)
    run_snow_sql_stdin(
        f"""
USE ROLE accountadmin;
ALTER USER {user} UNSET network_policy;
DROP NETWORK POLICY IF EXISTS {network_policy_name};
""",
        check=False,
    )

    cidr_list = f"'{local_ip}'"

    sql = f"""
        USE ROLE {admin_role};
        GRANT CREATE NETWORK RULE ON SCHEMA {db}.networks TO ROLE accountadmin;
        GRANT CREATE AUTHENTICATION POLICY ON SCHEMA {db}.policies TO ROLE accountadmin;

        CREATE DATABASE IF NOT EXISTS {db};
        USE DATABASE {db};

        CREATE SCHEMA IF NOT EXISTS networks;
        CREATE SCHEMA IF NOT EXISTS policies;
        CREATE SCHEMA IF NOT EXISTS data;

        CREATE OR REPLACE NETWORK RULE {db}.networks.{network_rule_name}
            MODE = ingress
            TYPE = ipv4
            VALUE_LIST = ({cidr_list})
            COMMENT = 'Network rule for {user} PAT access';

        USE ROLE accountadmin;

        CREATE OR REPLACE NETWORK POLICY {network_policy_name}
            ALLOWED_NETWORK_RULE_LIST = ({db}.networks.{network_rule_name})
            COMMENT = 'Network policy for {user} PAT access';

        ALTER USER {user} SET NETWORK_POLICY = '{network_policy_name}';
    """
    run_snow_sql_stdin(sql)
    click.echo("✓ Network policy configured")


def setup_auth_policy(user: str, db: str, default_expiry_days: int, max_expiry_days: int) -> None:
    """Create authentication policy for PAT access."""
    click.echo("Setting up authentication policy...")

    # Derive auth policy name from user
    auth_policy_name = f"{user}_auth_policy".upper()

    # First, unset any existing auth policy (ignore errors)
    run_snow_sql(
        f"USE ROLE accountadmin; ALTER USER {user} UNSET AUTHENTICATION POLICY;",
        check=False,
    )

    sql = f"""
        CREATE OR ALTER AUTHENTICATION POLICY {db}.policies.{auth_policy_name}
            AUTHENTICATION_METHODS = ('PROGRAMMATIC_ACCESS_TOKEN')
            PAT_POLICY = (
                default_expiry_in_days = {default_expiry_days},
                max_expiry_in_days = {max_expiry_days},
                network_policy_evaluation = ENFORCED_REQUIRED
            );

        ALTER USER {user} SET AUTHENTICATION POLICY {db}.policies.{auth_policy_name};
    """
    run_snow_sql_stdin(sql)
    click.echo("✓ Authentication policy configured")


def get_existing_pat(user: str, pat_name: str) -> str | None:
    """Check if a PAT with the given name exists for the user."""
    result = run_snow_sql(f"SHOW USER PATS FOR USER {user}")

    if not result:
        return None

    for pat in result:
        if pat.get("name", "").lower() == pat_name.lower():
            return pat.get("name")

    return None


def create_or_rotate_pat(user: str, pat_role: str, pat_name: str, rotate: bool = False) -> str:
    """Create a new PAT or rotate an existing one with pat_role as the role restriction."""
    existing = get_existing_pat(user, pat_name)

    if existing and not rotate:
        # Remove existing PAT and recreate (allows changing role restriction)
        click.echo(f"PAT '{pat_name}' exists. Removing and recreating (--no-rotate)...")
        remove_query = f"ALTER USER IF EXISTS {user} REMOVE PAT {pat_name}"
        run_snow_sql(remove_query)
        click.echo(f"✓ Removed existing PAT '{pat_name}'")
        existing = None  # Mark as removed so we create a new one

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
    """Remove a PAT from a user."""
    click.echo(f"Removing PAT '{pat_name}' from user {user}...")

    existing = get_existing_pat(user, pat_name)
    if not existing:
        click.echo(f"⚠ PAT '{pat_name}' not found for user {user}")
        return

    sql = f"ALTER USER IF EXISTS {user} REMOVE PAT {pat_name}"
    run_snow_sql(sql)
    click.echo(f"✓ Removed PAT '{pat_name}'")


def remove_network_policy(user: str, db: str) -> None:
    """Remove network rule and policy for a user."""
    network_rule_name = f"{user}_network_rule".upper()
    network_policy_name = f"{user}_network_policy".upper()

    click.echo(f"Removing network policy: {network_policy_name}")
    click.echo(f"Removing network rule: {db}.networks.{network_rule_name}")

    sql = f"""
        USE ROLE accountadmin;
        ALTER USER IF EXISTS {user} UNSET NETWORK_POLICY;
        DROP NETWORK POLICY IF EXISTS {network_policy_name};
        DROP NETWORK RULE IF EXISTS {db}.networks.{network_rule_name};
    """
    run_snow_sql_stdin(sql, check=False)
    click.echo("✓ Network policy and rule removed")


def remove_auth_policy(user: str, db: str) -> None:
    """Remove authentication policy for a user."""
    auth_policy_name = f"{user}_auth_policy".upper()

    click.echo(f"Removing authentication policy: {db}.policies.{auth_policy_name}")

    sql = f"""
        USE ROLE accountadmin;
        ALTER USER IF EXISTS {user} UNSET AUTHENTICATION POLICY;
        DROP AUTHENTICATION POLICY IF EXISTS {db}.policies.{auth_policy_name};
    """
    run_snow_sql_stdin(sql, check=False)
    click.echo("✓ Authentication policy removed")


def remove_service_user(user: str) -> None:
    """Drop the service user."""
    click.echo(f"Dropping service user: {user}")

    sql = f"""
        USE ROLE accountadmin;
        DROP USER IF EXISTS {user};
    """
    run_snow_sql_stdin(sql)
    click.echo(f"✓ Service user {user} dropped")


def _escape_env_value(value: str) -> str:
    """
    Escape a value for safe storage in .env file.

    Uses double quotes and escapes internal double quotes and backslashes.
    This is compatible with python-dotenv and most .env parsers.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def update_env(env_path: Path, user: str, password: str, pat_role: str) -> None:
    """Update .env file with the new SNOWFLAKE_PASSWORD and SA_ROLE (PAT role restriction)."""
    if not env_path.exists():
        click.echo(f"⚠ {env_path} not found, skipping update")
        return

    content = env_path.read_text()

    # Create backup
    backup_path = env_path.with_suffix(".env.bak")
    shutil.copy(env_path, backup_path)

    # Replace or add SNOWFLAKE_PASSWORD (properly escaped)
    password_pattern = r"^SNOWFLAKE_PASSWORD=.*$"
    password_replacement = f"SNOWFLAKE_PASSWORD={_escape_env_value(password)}"

    if re.search(password_pattern, content, re.MULTILINE):
        new_content = re.sub(password_pattern, password_replacement, content, flags=re.MULTILINE)
    else:
        new_content = content.rstrip() + f"\n{password_replacement}\n"

    # Replace or add SA_USER (properly escaped)
    user_pattern = r"^SA_USER=.*$"
    user_replacement = f"SA_USER={_escape_env_value(user)}"

    if re.search(user_pattern, new_content, re.MULTILINE):
        new_content = re.sub(user_pattern, user_replacement, new_content, flags=re.MULTILINE)
    else:
        new_content = new_content.rstrip() + f"\n{user_replacement}\n"

    # Replace or add SA_ROLE (properly escaped)
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

    # Create backup
    backup_path = env_path.with_suffix(".env.bak")
    shutil.copy(env_path, backup_path)
    click.echo(f"✓ Created backup: {backup_path}")

    # Set SNOWFLAKE_PASSWORD to empty string
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
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output (info level logging for snow CLI)",
)
@click.option(
    "--debug",
    "-d",
    is_flag=True,
    help="Enable debug output (debug level logging for snow CLI, shows SQL)",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, debug: bool) -> None:
    """
    Snowflake PAT Manager - Manage service users with programmatic access tokens.

    \b
    Commands:
        create  - Create/rotate PAT for service user (default)
        remove  - Remove PAT and associated objects

    \b
    Debug options:
        --verbose  Show info level output from snow CLI
        --debug    Show debug output including SQL statements
    """
    # Set global snow CLI options
    set_snow_cli_options(verbose=verbose, debug=debug)

    # If no subcommand is provided, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command(name="create")
@click.option(
    "--user",
    "-u",
    envvar="SA_USER",
    required=True,
    help="Service account user name (or set SA_USER env var)",
)
@click.option(
    "--role",
    "-r",
    envvar="SA_ROLE",
    required=True,
    help="Role restriction for the PAT (or set SA_ROLE env var)",
)
@click.option(
    "--admin-role",
    "-a",
    envvar="SA_ADMIN_ROLE",
    default=None,
    help="Admin role for creating network rules/policies (default: --role)",
)
@click.option(
    "--db",
    "-d",
    envvar="PAT_OBJECTS_DB",
    required=True,
    help="Database for PAT objects (or set PAT_OBJECTS_DB env var)",
)
@click.option(
    "--pat-name",
    default=None,
    envvar="PAT_NAME",
    help="Name for the PAT token (default: {user}_pat)",
)
@click.option(
    "--rotate/--no-rotate",
    default=True,
    help="Rotate existing PAT if it exists (default: True)",
)
@click.option(
    "--env-path",
    type=click.Path(path_type=Path),
    default=Path(".env"),
    envvar="DOT_ENV_FILE",
    help="Path to .env file to update",
)
@click.option(
    "--skip-verify",
    is_flag=True,
    help="Skip connection verification after PAT creation",
)
@click.option(
    "--local-ip",
    help="Override local IP detection (format: x.x.x.x/32)",
)
@click.option(
    "--default-expiry-days",
    default=45,
    type=int,
    help="Default PAT expiry in days (default: 45)",
)
@click.option(
    "--max-expiry-days",
    default=90,
    type=int,
    help="Maximum PAT expiry in days (default: 90)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview what would be created without making changes",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format (default: text)",
)
def create_command(
    user: str,
    role: str,
    admin_role: str | None,
    db: str,
    pat_name: str | None,
    rotate: bool,
    env_path: Path,
    skip_verify: bool,
    local_ip: str | None,
    default_expiry_days: int,
    max_expiry_days: int,
    dry_run: bool,
    output: str,
) -> None:
    """
    Create or rotate a PAT for a service user.

    This command:

    \b
    1. Creates/configures a Snowflake service user
    2. Sets up network rules and policies for secure access
    3. Configures authentication policy for PAT
    4. Creates or rotates a PAT for the service user
    5. Updates .env with the new credentials
    6. Verifies the connection works

    \b
    Two roles can be specified:
    - --admin-role: Role with privileges to create network rules, policies, database objects
    - --role: Role restriction for the PAT (the role the service account will actually use)

    Example:

    \b
        # Using environment variables
        export SA_USER=my_service_user
        export SA_ROLE=demo_role           # PAT role restriction
        export SA_ADMIN_ROLE=sysadmin      # Role for creating policies
        export PAT_OBJECTS_DB=my_db
        python pat.py create

        # Using CLI arguments (admin-role defaults to role if not specified)
        python pat.py create --user my_user --role demo_role --admin-role sysadmin --db my_db

        # Preview without creating
        python pat.py create --user my_user --role demo_role --db my_db --dry-run

        # Output results as JSON for automation
        python pat.py create --user my_user --role demo_role --db my_db --output json
    """
    # Set default admin_role to role if not provided
    if not admin_role:
        admin_role = role

    # Set default pat_name based on user if not provided
    if not pat_name:
        pat_name = f"{user}_pat".upper()

    # Helper to build result dict for JSON output
    def build_result(status: str, token: str | None = None) -> dict:
        result = {
            "status": status,
            "user": user,
            "pat_name": pat_name,
            "pat_role": role,
            "admin_role": admin_role,
            "database": db,
            "resources": {
                "network_rule": f"{db}.NETWORKS.{user}_NETWORK_RULE".upper(),
                "network_policy": f"{user}_NETWORK_POLICY".upper(),
                "auth_policy": f"{db}.POLICIES.{user}_AUTH_POLICY".upper(),
            },
        }
        if token:
            result["token"] = token
        return result

    # Get local IP if not provided (needed for both text and JSON output)
    if not local_ip:
        if output == "text":
            click.echo("Detecting local IP...")
        local_ip = get_local_ip()
        if output == "text":
            click.echo(f"✓ Local IP: {local_ip}")

    # JSON output for dry-run
    if output == "json" and dry_run:
        result = build_result("dry_run")
        result["local_ip"] = local_ip
        click.echo(json.dumps(result, indent=2))
        return

    # Text output header
    if output == "text":
        click.echo("=" * 50)
        click.echo("Snowflake PAT Manager")
        if dry_run:
            click.echo("  [DRY RUN - No changes will be made]")
        click.echo("=" * 50)
        click.echo()
        click.echo(f"User:       {user}")
        click.echo(f"PAT Role:   {role} (role restriction for PAT)")
        click.echo(f"Admin Role: {admin_role} (for creating policies)")
        click.echo(f"Database:   {db}")
        click.echo(f"PAT Name:   {pat_name}")
        click.echo(f"Local IP:   {local_ip}")
        click.echo()

    if dry_run:
        click.echo("─" * 40)
        click.echo("Resources that would be created:")
        click.echo(f"  Service User:     {user}")
        click.echo(f"  Network Rule:     {db}.NETWORKS.{user}_NETWORK_RULE".upper())
        click.echo(f"  Network Policy:   {user}_NETWORK_POLICY".upper())
        click.echo(f"  Auth Policy:      {db}.POLICIES.{user}_AUTH_POLICY".upper())
        click.echo(f"  PAT:              {pat_name}")
        click.echo("─" * 40)
        click.echo()
        click.echo("Dry run complete. No resources were created.")
        click.echo("To create these resources, run without --dry-run")
        return

    # Step 1: Setup service user (grants the PAT role to user)
    setup_service_user(user=user, pat_role=role)

    # Step 2: Setup network policy (uses admin_role for creating resources)
    setup_network_policy(user=user, admin_role=admin_role, db=db, local_ip=local_ip)

    # Step 3: Setup authentication policy (uses admin_role)
    setup_auth_policy(
        user=user, db=db, default_expiry_days=default_expiry_days, max_expiry_days=max_expiry_days
    )

    # Step 4: Create or rotate PAT (uses role as the PAT role restriction)
    password = create_or_rotate_pat(user=user, pat_role=role, pat_name=pat_name, rotate=rotate)

    # Step 5: Update .env (stores the PAT role)
    if output == "text":
        update_env(env_path=env_path, user=user, password=password, pat_role=role)

    # Step 6: Verify connection
    if not skip_verify and output == "text":
        verify_connection(user=user, password=password, pat_role=role)

    # JSON output for successful creation
    if output == "json":
        result = build_result("success", password)
        result["local_ip"] = local_ip
        result["env_file"] = str(env_path)
        click.echo(json.dumps(result, indent=2))
        return

    click.echo()
    click.echo("=" * 50)
    click.echo("✓ PAT setup completed successfully!")
    click.echo("=" * 50)


@cli.command(name="remove")
@click.option(
    "--user",
    "-u",
    envvar="SA_USER",
    required=True,
    help="Service account user name (or set SA_USER env var)",
)
@click.option(
    "--db",
    "-d",
    envvar="PAT_OBJECTS_DB",
    required=True,
    help="Database where PAT objects are stored (or set PAT_OBJECTS_DB env var)",
)
@click.option(
    "--pat-name",
    default=None,
    envvar="PAT_NAME",
    help="Name of the PAT to remove (default: {user}_pat)",
)
@click.option(
    "--drop-user",
    is_flag=True,
    help="Also drop the service user (default: keep user)",
)
@click.option(
    "--pat-only",
    is_flag=True,
    help="Only remove the PAT, keep network and auth policies",
)
@click.option(
    "--env-path",
    type=click.Path(path_type=Path),
    default=Path(".env"),
    envvar="DOT_ENV_FILE",
    help="Path to .env file to clear credentials from",
)
@click.confirmation_option(prompt="Are you sure you want to remove the PAT and associated objects?")
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

    This command removes:

    \b
    1. The PAT (programmatic access token)
    2. Network policy and network rule (unless --pat-only)
    3. Authentication policy (unless --pat-only)
    4. Optionally the service user (with --drop-user)
    5. Clears SNOWFLAKE_PASSWORD from .env file

    \b
    Based on Snowflake documentation:
    https://docs.snowflake.com/en/sql-reference/sql/alter-user-remove-programmatic-access-token

    Example:

    \b
        # Remove PAT and policies (keep user)
        python pat.py remove --user my_service_user --db my_db

        # Remove only the PAT
        python pat.py remove --user my_service_user --db my_db --pat-only

        # Remove everything including the user
        python pat.py remove --user my_service_user --db my_db --drop-user
    """
    click.echo("=" * 50)
    click.echo("Snowflake PAT Manager - Remove")
    click.echo("=" * 50)
    click.echo()

    # Set default pat_name based on user if not provided
    if not pat_name:
        pat_name = f"{user}_pat".upper()

    click.echo(f"User:     {user}")
    click.echo(f"Database: {db}")
    click.echo(f"PAT Name: {pat_name}")
    click.echo()

    # Step 1: Remove PAT
    click.echo("─" * 40)
    click.echo("Step 1: Remove PAT")
    click.echo("─" * 40)
    remove_pat(user=user, pat_name=pat_name)
    click.echo()

    if not pat_only:
        # Step 2: Remove network policy
        click.echo("─" * 40)
        click.echo("Step 2: Remove Network Policy")
        click.echo("─" * 40)
        remove_network_policy(user=user, db=db)
        click.echo()

        # Step 3: Remove authentication policy
        click.echo("─" * 40)
        click.echo("Step 3: Remove Authentication Policy")
        click.echo("─" * 40)
        remove_auth_policy(user=user, db=db)
        click.echo()

    if drop_user:
        # Step 4: Drop user
        click.echo("─" * 40)
        click.echo("Step 4: Drop Service User")
        click.echo("─" * 40)
        remove_service_user(user=user)
        click.echo()

    # Step 5: Clear credentials from .env
    click.echo("─" * 40)
    click.echo("Step 5: Clear Credentials from .env")
    click.echo("─" * 40)
    clear_env(env_path=env_path)
    click.echo()

    click.echo("=" * 50)
    click.echo("✓ PAT removal completed successfully!")
    click.echo("=" * 50)


if __name__ == "__main__":
    cli()
