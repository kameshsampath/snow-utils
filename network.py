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
Snowflake Network Manager - Core module and CLI.

Provides:
- Core functions for creating/managing network rules and policies
- CLI commands for network operations
- IPv4 preset support (GitHub Actions, Google, local IP)
"""

import click

from network_presets import (
    NetworkRuleMode,
    NetworkRuleType,
    collect_ipv4_cidrs,
    get_valid_types_for_mode,
    validate_mode_type,
)
from snow_common import (
    run_snow_sql,
    run_snow_sql_stdin,
    set_snow_cli_options,
)


def get_network_rule_sql(
    name: str,
    db: str,
    schema: str,
    values: list[str],
    mode: NetworkRuleMode = NetworkRuleMode.INGRESS,
    rule_type: NetworkRuleType = NetworkRuleType.IPV4,
    comment: str = "",
    force: bool = False,
) -> str:
    """
    Generate SQL for creating a network rule.

    Args:
        name: Network rule name
        db: Database name
        schema: Schema name
        values: List of values (CIDRs, hosts, VPC IDs depending on type)
        mode: Rule mode (INGRESS, EGRESS, etc.)
        rule_type: Value type (IPV4, HOST_PORT, etc.)
        comment: Optional comment

    Returns:
        CREATE OR REPLACE NETWORK RULE SQL statement
    """
    value_list = ", ".join(f"'{v}'" for v in values)
    comment_text = comment or "Created by snow-utils"
    create_stmt = "CREATE OR REPLACE" if force else "CREATE IF NOT EXISTS"
    return f"""{create_stmt} NETWORK RULE {db}.{schema}.{name}
    MODE = {mode.value}
    TYPE = {rule_type.value}
    VALUE_LIST = ({value_list})
    COMMENT = '{comment_text}';"""


def get_network_policy_sql(
    policy_name: str,
    rule_refs: list[str],
    comment: str = "",
    force: bool = False,
) -> str:
    """
    Generate SQL for creating a network policy from rules.

    Args:
        policy_name: Network policy name
        rule_refs: List of fully qualified network rule names
        comment: Optional comment

    Returns:
        CREATE OR REPLACE NETWORK POLICY SQL statement
    """
    rule_list = ", ".join(rule_refs)
    comment_text = comment or "Created by snow-utils"
    create_stmt = "CREATE OR REPLACE" if force else "CREATE IF NOT EXISTS"
    return f"""{create_stmt} NETWORK POLICY {policy_name}
    ALLOWED_NETWORK_RULE_LIST = ({rule_list})
    COMMENT = '{comment_text}';"""


def get_alter_network_policy_sql(
    policy_name: str,
    rule_refs: list[str],
) -> str:
    """
    Generate SQL for adding rules to an existing network policy.

    Args:
        policy_name: Network policy name
        rule_refs: List of fully qualified network rule names to add

    Returns:
        ALTER NETWORK POLICY SQL statement
    """
    rule_list = ", ".join(rule_refs)
    return f"""ALTER NETWORK POLICY {policy_name}
    ADD ALLOWED_NETWORK_RULE_LIST = ({rule_list});"""


def create_network_rule(
    name: str,
    db: str,
    schema: str,
    values: list[str],
    mode: NetworkRuleMode = NetworkRuleMode.INGRESS,
    rule_type: NetworkRuleType = NetworkRuleType.IPV4,
    comment: str = "",
    dry_run: bool = False,
    force: bool = False,
) -> str:
    """
    Create a network rule in Snowflake.

    Args:
        name: Network rule name
        db: Database name
        schema: Schema name
        values: List of values (CIDRs, hosts, VPC IDs)
        mode: Rule mode
        rule_type: Value type
        comment: Optional comment
        dry_run: If True, only print SQL without executing

    Returns:
        Fully qualified network rule name (db.schema.name)

    Raises:
        click.ClickException: If mode/type combination is invalid
    """
    if not validate_mode_type(mode, rule_type):
        valid = get_valid_types_for_mode(mode)
        raise click.ClickException(
            f"Invalid type '{rule_type.value}' for mode '{mode.value}'. "
            f"Valid types: {valid}"
        )

    sql = get_network_rule_sql(name, db, schema, values, mode, rule_type, comment, force)

    if dry_run:
        click.echo(sql)
    else:
        setup_sql = (
            f"CREATE DATABASE IF NOT EXISTS {db};\n"
            f"CREATE SCHEMA IF NOT EXISTS {db}.{schema};\n"
        )
        run_snow_sql_stdin(setup_sql + sql)

    return f"{db}.{schema}.{name}"


def create_network_policy(
    policy_name: str,
    rule_refs: list[str],
    comment: str = "",
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """
    Create a network policy referencing given rules.

    Args:
        policy_name: Network policy name
        rule_refs: List of fully qualified network rule names
        comment: Optional comment
        dry_run: If True, only print SQL without executing
    """
    sql = get_network_policy_sql(policy_name, rule_refs, comment, force)

    if dry_run:
        click.echo(sql)
    else:
        run_snow_sql_stdin(sql)


def alter_network_policy(
    policy_name: str,
    rule_refs: list[str],
    dry_run: bool = False,
) -> None:
    """
    Add rules to an existing network policy.

    Args:
        policy_name: Network policy name
        rule_refs: List of fully qualified network rule names to add
        dry_run: If True, only print SQL without executing
    """
    sql = get_alter_network_policy_sql(policy_name, rule_refs)

    if dry_run:
        click.echo(sql)
    else:
        run_snow_sql_stdin(sql)


def delete_network_rule(name: str, db: str, schema: str) -> None:
    """Delete a network rule (idempotent)."""
    run_snow_sql(f"DROP NETWORK RULE IF EXISTS {db}.{schema}.{name}")


def delete_network_policy(policy_name: str) -> None:
    """Delete a network policy (idempotent)."""
    run_snow_sql(f"DROP NETWORK POLICY IF EXISTS {policy_name}")


def list_network_rules(db: str, schema: str) -> list[dict]:
    """List network rules in a schema."""
    return run_snow_sql(f"SHOW NETWORK RULES IN SCHEMA {db}.{schema}") or []


def list_network_policies() -> list[dict]:
    """List all network policies."""
    return run_snow_sql("SHOW NETWORK POLICIES") or []


def network_policy_exists(policy_name: str) -> bool:
    """Check if a network policy exists."""
    policies = list_network_policies()
    return any(p.get("name", "").upper() == policy_name.upper() for p in policies)


def setup_network_for_user(
    user: str,
    db: str,
    cidrs: list[str],
    schema: str = "NETWORKS",
    dry_run: bool = False,
    force: bool = False,
) -> tuple[str, str]:
    """
    Create network rule and policy for a user (idempotent).

    This is a convenience function for PAT and other user setup workflows.
    Uses CREATE OR REPLACE for idempotency.

    Args:
        user: Username (used for naming rule/policy)
        db: Database for network rule
        cidrs: List of IPv4 CIDRs
        schema: Schema for network rule (default: NETWORKS)
        dry_run: If True, only print SQL

    Returns:
        Tuple of (rule_fqn, policy_name)
    """
    rule_name = f"{user}_NETWORK_RULE".upper()
    policy_name = f"{user}_NETWORK_POLICY".upper()

    rule_fqn = create_network_rule(
        name=rule_name,
        db=db,
        schema=schema,
        values=cidrs,
        mode=NetworkRuleMode.INGRESS,
        rule_type=NetworkRuleType.IPV4,
        comment=f"Network rule for {user} access",
        dry_run=dry_run,
        force=force,
    )

    create_network_policy(
        policy_name=policy_name,
        rule_refs=[rule_fqn],
        comment=f"Network policy for {user} access",
        dry_run=dry_run,
        force=force,
    )

    return rule_fqn, policy_name


def cleanup_network_for_user(
    user: str,
    db: str,
    schema: str = "NETWORKS",
    unset_from_user: bool = True,
) -> None:
    """
    Remove network rule and policy for a user (idempotent).

    Args:
        user: Username
        db: Database containing network rule
        schema: Schema containing network rule
        unset_from_user: If True, also unset network policy from user
    """
    rule_name = f"{user}_NETWORK_RULE".upper()
    policy_name = f"{user}_NETWORK_POLICY".upper()

    if unset_from_user:
        run_snow_sql_stdin(
            f"ALTER USER IF EXISTS {user} UNSET NETWORK_POLICY;",
            check=False,
        )

    delete_network_policy(policy_name)
    delete_network_rule(rule_name, db.upper(), schema.upper())


def assign_network_policy_to_user(user: str, policy_name: str) -> None:
    """Assign a network policy to a user."""
    run_snow_sql_stdin(f"ALTER USER {user} SET NETWORK_POLICY = '{policy_name}';")


def unassign_network_policy_from_user(user: str) -> None:
    """Remove network policy from a user (idempotent)."""
    run_snow_sql_stdin(f"ALTER USER IF EXISTS {user} UNSET NETWORK_POLICY;", check=False)


MODE_CHOICES = ["ingress", "internal_stage", "egress", "postgres_ingress", "postgres_egress"]
TYPE_CHOICES = ["ipv4", "host_port", "private_host_port", "awsvpceid"]


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--debug", "-d", is_flag=True, help="Enable debug output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, debug: bool) -> None:
    """
    Snowflake Network Rule Manager.

    Create and manage network rules with IPv4 presets for GitHub Actions,
    Google services, and local IP detection.
    """
    set_snow_cli_options(verbose=verbose, debug=debug)
    ctx.ensure_object(dict)


@cli.command()
@click.option("--name", "-n", required=True, envvar="NW_RULE_NAME", help="Network rule name")
@click.option("--db", required=True, envvar="NW_RULE_DB", help="Database for rule")
@click.option(
    "--schema", "-s",
    default="NETWORKS",
    envvar="NW_RULE_SCHEMA",
    help="Schema (default: NETWORKS)",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(MODE_CHOICES, case_sensitive=False),
    default="ingress",
    help="Rule mode (default: ingress)",
)
@click.option(
    "--type", "-t", "rule_type",
    type=click.Choice(TYPE_CHOICES, case_sensitive=False),
    default="ipv4",
    help="Value type (default: ipv4)",
)
@click.option("--values", help="Comma-separated values (CIDRs, hosts, VPC IDs)")
@click.option(
    "--with-local/--no-local",
    default=True,
    help="Include local IP (IPV4 only, default: ON)",
)
@click.option("--with-gh", "-G", is_flag=True, help="Include GitHub Actions IPs (IPV4 only)")
@click.option("--with-google", "-g", is_flag=True, help="Include Google IPs (IPV4 only)")
@click.option("--dry-run", is_flag=True, help="Preview SQL without executing")
@click.option(
    "--force", "-f",
    is_flag=True,
    help="Overwrite existing rule/policy (CREATE OR REPLACE)",
)
@click.option(
    "--policy", "-p",
    "policy_name",
    help="Also create/update network policy with this name",
)
@click.option(
    "--policy-mode",
    type=click.Choice(["create", "alter"], case_sensitive=False),
    default="create",
    help="Policy mode: 'create' (replace) or 'alter' (add to existing)",
)
def create(
    name: str,
    db: str,
    schema: str,
    mode: str,
    rule_type: str,
    values: str | None,
    with_local: bool,
    with_gh: bool,
    with_google: bool,
    dry_run: bool,
    force: bool,
    policy_name: str | None,
    policy_mode: str,
) -> None:
    """
    Create a network rule with presets and/or custom values.

    \b
    Examples:
        # Local IP only (default)
        nwrule.py create --name dev_rule --db my_db

        # GitHub Actions + local IP
        nwrule.py create --name ci_rule --db my_db --with-gh

        # GitHub Actions + local IP + create policy
        network.py create --name ci_rule --db my_db --with-gh --policy ci_policy

        # Add rule to existing policy
        network.py create --name extra_rule --db my_db --policy my_policy --policy-mode alter

        # Egress rule for external APIs
        network.py create --name api_egress --db my_db \\
            --mode egress --type host_port \\
            --values "api.openai.com:443,api.anthropic.com:443"

        # Postgres wire protocol for BI tools
        nwrule.py create --name bi_access --db my_db --mode postgres_ingress
    """
    mode_enum = NetworkRuleMode(mode.upper())
    type_enum = NetworkRuleType(rule_type.upper())

    has_presets = with_local or with_gh or with_google
    if has_presets and type_enum != NetworkRuleType.IPV4:
        raise click.ClickException(
            f"IPv4 presets (--with-local, --with-gh, --with-google) "
            f"only valid for --type ipv4, not {rule_type}"
        )

    if type_enum == NetworkRuleType.IPV4:
        extra = [v.strip() for v in values.split(",")] if values else None
        all_values = collect_ipv4_cidrs(with_local, with_gh, with_google, extra)
    else:
        if not values:
            raise click.ClickException(f"--values required for type {rule_type}")
        all_values = [v.strip() for v in values.split(",")]

    if not all_values:
        raise click.ClickException("No values specified.")

    click.echo(
        f"Creating {mode.upper()} network rule ({rule_type.upper()}) "
        f"with {len(all_values)} value(s)..."
    )

    fqn = create_network_rule(
        name.upper(),
        db.upper(),
        schema.upper(),
        all_values,
        mode_enum,
        type_enum,
        dry_run=dry_run,
        force=force,
    )

    if not dry_run:
        click.echo(f"✓ Created rule: {fqn}")

    if policy_name:
        policy_upper = policy_name.upper()
        if policy_mode.lower() == "alter":
            click.echo(f"Adding rule to policy: {policy_upper}")
            alter_network_policy(policy_upper, [fqn], dry_run=dry_run)
            if not dry_run:
                click.echo(f"✓ Updated policy: {policy_upper}")
        else:
            click.echo(f"Creating policy: {policy_upper}")
            create_network_policy(policy_upper, [fqn], dry_run=dry_run, force=force)
            if not dry_run:
                click.echo(f"✓ Created policy: {policy_upper}")


@cli.command()
@click.option("--name", "-n", required=True, envvar="NW_RULE_NAME", help="Network rule name")
@click.option("--db", required=True, envvar="NW_RULE_DB", help="Database name")
@click.option("--schema", "-s", default="NETWORKS", envvar="NW_RULE_SCHEMA", help="Schema name")
@click.option("--with-local", is_flag=True, default=False, help="Also include local IP")
@click.option("--policy", "-p", "policy_name", help="Also create/update network policy")
@click.option("--policy-mode", type=click.Choice(["create", "alter"]), default="create")
@click.option("--dry-run", is_flag=True, help="Preview SQL without executing")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing rule/policy")
@click.pass_context
def github(
    ctx: click.Context,
    name: str,
    db: str,
    schema: str,
    with_local: bool,
    policy_name: str | None,
    policy_mode: str,
    dry_run: bool,
    force: bool,
) -> None:
    """Create INGRESS IPV4 rule for GitHub Actions IPs."""
    ctx.invoke(
        create,
        name=name,
        db=db,
        schema=schema,
        mode="ingress",
        rule_type="ipv4",
        values=None,
        with_local=with_local,
        with_gh=True,
        with_google=False,
        dry_run=dry_run,
        force=force,
        policy_name=policy_name,
        policy_mode=policy_mode,
    )


@cli.command()
@click.option("--name", "-n", required=True, envvar="NW_RULE_NAME", help="Network rule name")
@click.option("--db", required=True, envvar="NW_RULE_DB", help="Database name")
@click.option("--schema", "-s", default="NETWORKS", envvar="NW_RULE_SCHEMA", help="Schema name")
@click.option("--with-local", is_flag=True, default=False, help="Also include local IP")
@click.option("--policy", "-p", "policy_name", help="Also create/update network policy")
@click.option("--policy-mode", type=click.Choice(["create", "alter"]), default="create")
@click.option("--dry-run", is_flag=True, help="Preview SQL without executing")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing rule/policy")
@click.pass_context
def google(
    ctx: click.Context,
    name: str,
    db: str,
    schema: str,
    with_local: bool,
    policy_name: str | None,
    policy_mode: str,
    dry_run: bool,
    force: bool,
) -> None:
    """Create INGRESS IPV4 rule for Google IPs."""
    ctx.invoke(
        create,
        name=name,
        db=db,
        schema=schema,
        mode="ingress",
        rule_type="ipv4",
        values=None,
        with_local=with_local,
        with_gh=False,
        with_google=True,
        dry_run=dry_run,
        force=force,
        policy_name=policy_name,
        policy_mode=policy_mode,
    )


@cli.command(name="local")
@click.option("--name", "-n", required=True, envvar="NW_RULE_NAME", help="Network rule name")
@click.option("--db", required=True, envvar="NW_RULE_DB", help="Database name")
@click.option("--schema", "-s", default="NETWORKS", envvar="NW_RULE_SCHEMA", help="Schema name")
@click.option("--policy", "-p", "policy_name", help="Also create/update network policy")
@click.option("--policy-mode", type=click.Choice(["create", "alter"]), default="create")
@click.option("--dry-run", is_flag=True, help="Preview SQL without executing")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing rule/policy")
@click.pass_context
def local_cmd(
    ctx: click.Context,
    name: str,
    db: str,
    schema: str,
    policy_name: str | None,
    policy_mode: str,
    dry_run: bool,
    force: bool,
) -> None:
    """Create INGRESS IPV4 rule for current IP only."""
    ctx.invoke(
        create,
        name=name,
        db=db,
        schema=schema,
        mode="ingress",
        rule_type="ipv4",
        values=None,
        with_local=True,
        with_gh=False,
        with_google=False,
        dry_run=dry_run,
        force=force,
        policy_name=policy_name,
        policy_mode=policy_mode,
    )


@cli.command(name="delete-rule")
@click.option("--name", "-n", required=True, envvar="NW_RULE_NAME", help="Network rule name")
@click.option("--db", required=True, envvar="NW_RULE_DB", help="Database name")
@click.option("--schema", "-s", default="NETWORKS", envvar="NW_RULE_SCHEMA", help="Schema name")
@click.confirmation_option(prompt="Delete this network rule?")
def delete_rule_cmd(name: str, db: str, schema: str) -> None:
    """Delete a network rule."""
    fqn = f"{db}.{schema}.{name}".upper()
    click.echo(f"Deleting network rule: {fqn}")
    delete_network_rule(name.upper(), db.upper(), schema.upper())
    click.echo(f"✓ Deleted: {fqn}")


@cli.command(name="delete-policy")
@click.option("--name", "-n", required=True, help="Network policy name")
@click.option("--user", "-u", help="Also unset from this user first")
@click.confirmation_option(prompt="Delete this network policy?")
def delete_policy_cmd(name: str, user: str | None) -> None:
    """Delete a network policy."""
    policy_name = name.upper()
    if user:
        click.echo(f"Unsetting policy from user: {user}")
        unassign_network_policy_from_user(user)
    click.echo(f"Deleting network policy: {policy_name}")
    delete_network_policy(policy_name)
    click.echo(f"✓ Deleted: {policy_name}")


@cli.command(name="list-rules")
@click.option("--db", required=True, envvar="NW_RULE_DB", help="Database name")
@click.option("--schema", "-s", default="NETWORKS", envvar="NW_RULE_SCHEMA", help="Schema name")
def list_rules_cmd(db: str, schema: str) -> None:
    """List network rules in schema."""
    click.echo(f"Network rules in {db}.{schema}:".upper())
    rules = list_network_rules(db.upper(), schema.upper())

    if not rules:
        click.echo("  (none)")
        return

    for r in rules:
        rule_name = r.get("name", "N/A")
        rule_type = r.get("type", "N/A")
        mode = r.get("mode", "N/A")
        click.echo(f"  {rule_name} ({mode}, {rule_type})")


@cli.command(name="list-policies")
def list_policies_cmd() -> None:
    """List all network policies."""
    click.echo("Network policies:")
    policies = list_network_policies()

    if not policies:
        click.echo("  (none)")
        return

    for p in policies:
        name = p.get("name", "N/A")
        click.echo(f"  {name}")


@cli.command()
@click.option("--name", "-n", required=True, help="Network policy name")
@click.option(
    "--rules", "-r",
    required=True,
    help="Comma-separated fully qualified rule names (db.schema.rule)",
)
@click.option(
    "--alter", "-a",
    is_flag=True,
    help="Add rules to existing policy instead of creating new",
)
@click.option("--dry-run", is_flag=True, help="Preview SQL without executing")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing policy (CREATE OR REPLACE)")
def policy(name: str, rules: str, alter: bool, dry_run: bool, force: bool) -> None:
    """
    Create or alter a network policy with specified rules.

    \b
    Examples:
        # Create new policy with rules
        nwrule.py policy --name my_policy --rules "db.networks.rule1,db.networks.rule2"

        # Add rules to existing policy
        nwrule.py policy --name my_policy --rules "db.networks.rule3" --alter
    """
    rule_refs = [r.strip().upper() for r in rules.split(",")]
    policy_name = name.upper()

    if alter:
        click.echo(f"Adding {len(rule_refs)} rule(s) to policy: {policy_name}")
        alter_network_policy(policy_name, rule_refs, dry_run=dry_run)
        if not dry_run:
            click.echo(f"✓ Updated: {policy_name}")
    else:
        click.echo(f"Creating policy {policy_name} with {len(rule_refs)} rule(s)...")
        create_network_policy(policy_name, rule_refs, dry_run=dry_run, force=force)
        if not dry_run:
            click.echo(f"✓ Created: {policy_name}")


if __name__ == "__main__":
    cli()
