# Snow Utils

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Stop clicking through AWS Console and Snowflake UI. Automate it.**

Snow Utils turns complex multi-step Snowflake infrastructure setup into single commands:

| Task | Manual | With Snow Utils |
|------|--------|-----------------|
| External Volume + S3 + IAM | 10+ steps, 3 consoles | `snow-utils extvolume:up` |
| PAT + Network Policy + Auth Policy | 8+ steps | `snow-utils pat:create` |
| Network Rule + Policy | 5+ steps | `snow-utils networks:create` |

## What It Does

| Tool | What It Creates |
|------|-----------------|
| **External Volumes (AWS)** | S3 bucket → IAM role/policy → Snowflake external volume → trust relationship. Ready for Iceberg. |
| **PAT Management** | Service user → network policy → auth policy → PAT. Ready for CI/CD. |
| **Network Management** | Network rules (IPv4, HOST_PORT, etc.) → Network policies. Control access by IP, hostname, or VPC. |

> [!NOTE]
> External volume management currently supports **AWS S3** only. Azure Blob and GCS support may be added in future releases.

## Quick Start

```bash
# 🚀 Setup external volume for Iceberg tables
snow-utils extvolume:up

# 🔑 Create PAT for a service account
snow-utils pat:create SA_USER=my_sa SA_ROLE=my_role PAT_OBJECTS_DB=my_db

# 🌐 Create network rule for GitHub Actions
snow-utils networks:github NW_RULE_NAME=gh_actions NW_RULE_DB=my_db

# 🗑️ Tear everything down
snow-utils extvolume:down
snow-utils pat:remove
```

## Features

| Feature | Description |
|---------|-------------|
| **External Volume Management** | Create, verify, and delete Snowflake external volumes with AWS S3 |
| **AWS Resource Automation** | Provisions S3 buckets, IAM roles, and policies automatically |
| **PAT Management** | Create, rotate, and remove Programmatic Access Tokens |
| **Network Management** | Create network rules (IPv4, HOST_PORT) with built-in presets for GitHub, Google |
| **Smart Naming** | Resources prefixed with your username to avoid conflicts |
| **Environment-Driven** | Configure once in `.env`, run commands without parameters |
| **Tab Completion** | Shell completions for Bash and Zsh |

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| [Task](https://taskfile.dev/) | Task runner | `brew install go-task` |
| [uv](https://docs.astral.sh/uv/) | Python package manager | `brew install uv` |
| [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index) | `snow` command | `pip install snowflake-cli-labs` |
| [AWS CLI](https://aws.amazon.com/cli/) | AWS operations | `brew install awscli` |
| Python 3.11+ | Runtime | - |

> [!IMPORTANT]
> **Windows Users:** This tool requires a Unix-like shell. Use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) or Git Bash.

**Required permissions:**

- **AWS:** S3 full access, IAM role/policy management
- **Snowflake:** `ACCOUNTADMIN` or role with external volume privileges

---

## Installation

### 1. Clone and Setup

```bash
git clone https://github.com/kameshsampath/snow-bin-utils
cd snow-bin-utils

# Setup Python environment and install global command
task setup

# Or if you already have the repo and just need to update dependencies
task install
```

This will:
- Create `.venv` and install Python dependencies
- Symlink `snow-utils` to `~/.local/bin/` (if not already present)

> [!TIP]
> Ensure `~/.local/bin` is in your `PATH`. Add to your shell profile if needed:
> ```bash
> export PATH="$HOME/.local/bin:$PATH"
> ```

> [!NOTE]
> After running `task setup`, `snow-utils` works from **any directory** — it automatically uses the Python environment from the install location via `uv run`. No need to activate a venv or set up Python in each project.

### 2. Enable Tab Completion (Optional)

**Zsh** (save to your completions directory):

```bash
snow-utils --completion zsh > ~/.config/zsh/completions/_snow-utils
# Or wherever your fpath completions are stored
```

> [!TIP]
> Ensure your `~/.zshrc` has the completions directory in `fpath` before `compinit`:
>
> ```zsh
> fpath+=/path/to/completions
> autoload -Uz compinit && compinit
> ```

**Bash** (append to `.bashrc`):

```bash
snow-utils --completion bash >> ~/.bashrc
source ~/.bashrc
```

### 3. Configure Environment

Create a `.env` file (or copy from `.env.example`):

```bash
# Snowflake connection
SNOWFLAKE_DEFAULT_CONNECTION_NAME=default
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_DATABASE=MY_DATABASE

# AWS (optional, defaults to us-west-2)
AWS_REGION=us-west-2

# External Volume (optional)
BUCKET=iceberg-demo

# PAT Management (optional)
SA_USER=my_service_user
SA_ROLE=demo_role
SA_ADMIN_ROLE=sysadmin
PAT_OBJECTS_DB=my_db
```

### 4. Verify Installation

```bash
# Check snow-utils is available
snow-utils --help

# Test Snowflake connection
snow-utils snow:test

# Test AWS credentials
snow-utils aws:whoami
```

---

## External Volume Management (AWS)

> [!NOTE]
> **Snowflake Docs:**
> - [CREATE EXTERNAL VOLUME](https://docs.snowflake.com/en/sql-reference/sql/create-external-volume)
> - [Configure External Volume](https://docs.snowflake.com/user-guide/tables-iceberg-configure-external-volume)
> - [External Volume for S3](https://docs.snowflake.com/user-guide/tables-iceberg-configure-external-volume-s3)

### Required Privileges

| Platform | Role/Permissions | Purpose |
|----------|------------------|--------|
| **Snowflake** | `ACCOUNTADMIN` or role with `CREATE EXTERNAL VOLUME` | Create/drop external volumes |
| **AWS** | `s3:CreateBucket`, `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` | S3 bucket operations |
| **AWS** | `iam:CreateRole`, `iam:CreatePolicy`, `iam:AttachRolePolicy`, `iam:UpdateAssumeRolePolicy` | IAM role/policy management |

> [!TIP]
> Use `ACCOUNTADMIN` for simplicity, or create a custom role with `GRANT CREATE EXTERNAL VOLUME ON ACCOUNT TO ROLE my_role`.

### What Gets Created

When you run `extvolume:create`, the following resources are provisioned:

```
┌─────────────────────────────────────────────────────────────┐
│                         AWS                                 │
├─────────────────────────────────────────────────────────────┤
│  S3 Bucket:     {username}-{bucket}                         │
│  IAM Policy:    {username}-{bucket}-snowflake-policy        │
│  IAM Role:      {username}-{bucket}-snowflake-role          │
│                 └── Trust policy → Snowflake IAM user       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      Snowflake                              │
├─────────────────────────────────────────────────────────────┤
│  External Volume: {USERNAME}_{BUCKET}_EXTERNAL_VOLUME       │
│                   └── References S3 bucket via IAM role     │
└─────────────────────────────────────────────────────────────┘
```

### Commands

| Command | Description |
|---------|-------------|
| `extvolume:up` | Quick start — create bucket and external volume with defaults |
| `extvolume:down` | Tear down — delete bucket and external volume |
| `extvolume:create` | Create S3 bucket, IAM role, and Snowflake external volume |
| `extvolume:delete` | Delete external volume and AWS resources |
| `extvolume:verify` | Verify external volume connectivity |
| `extvolume:describe` | Describe external volume properties |
| `extvolume:update-trust` | Update IAM trust policy from external volume |

### Examples

```bash
# Quick start with defaults (uses BUCKET from env or 'iceberg-demo')
snow-utils extvolume:up

# Create with custom bucket
snow-utils extvolume:create BUCKET=my-data

# Create without username prefix
snow-utils extvolume:create BUCKET=my-data -- --no-prefix

# Create with custom prefix
snow-utils extvolume:create BUCKET=my-data -- --prefix myproject

# Verify volume connectivity
snow-utils extvolume:verify VOLUME=MY_EXTERNAL_VOLUME

# Delete (keeps S3 bucket)
snow-utils extvolume:delete BUCKET=my-data

# Delete everything including S3 bucket
snow-utils extvolume:delete BUCKET=my-data -- --delete-bucket --force
```

> [!TIP]
> The `--` separates Task variables (`VAR=value`) from CLI flags (`--flag`).

---

## PAT Management

> [!NOTE]
> **Snowflake Docs:**
> - [Programmatic Access Tokens](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens)
> - [ALTER USER ADD PAT](https://docs.snowflake.com/en/sql-reference/sql/alter-user-add-programmatic-access-token)
> - [CREATE USER (TYPE=SERVICE)](https://docs.snowflake.com/en/sql-reference/sql/create-user)
> - [CREATE AUTHENTICATION POLICY](https://docs.snowflake.com/en/sql-reference/sql/create-authentication-policy)
> - [CREATE NETWORK RULE](https://docs.snowflake.com/en/sql-reference/sql/create-network-rule)
> - [CREATE NETWORK POLICY](https://docs.snowflake.com/en/sql-reference/sql/create-network-policy)

### Required Privileges

| Role | Privileges Needed | Used For |
|------|-------------------|----------|
| **SA_ADMIN_ROLE** | `CREATE USER` | Create the service user |
| **SA_ADMIN_ROLE** | `CREATE SCHEMA` on database | Create POLICIES and NETWORKS schemas |
| **SA_ADMIN_ROLE** | `CREATE AUTHENTICATION POLICY` | Create auth policy for PAT |
| **SA_ADMIN_ROLE** | `CREATE NETWORK RULE`, `CREATE NETWORK POLICY` | Create network restrictions |
| **SA_ADMIN_ROLE** | `GRANT ROLE` | Grant SA_ROLE to service user |
| **SA_ROLE** | (must exist) | Role the PAT will be restricted to |

> [!TIP]
> `ACCOUNTADMIN` or `SECURITYADMIN` have all required privileges. For least-privilege, create a custom admin role:
> ```sql
> GRANT CREATE USER ON ACCOUNT TO ROLE pat_admin;
> GRANT CREATE AUTHENTICATION POLICY ON ACCOUNT TO ROLE pat_admin;
> GRANT CREATE NETWORK POLICY ON ACCOUNT TO ROLE pat_admin;
> GRANT CREATE SCHEMA ON DATABASE my_db TO ROLE pat_admin;
> ```

### What Gets Created

When you run `pat`, the following resources are provisioned:

```
┌─────────────────────────────────────────────────────────────┐
│                      Snowflake                              │
├─────────────────────────────────────────────────────────────┤
│  Service User:       {SA_USER} (TYPE=SERVICE)               │
│                      └── Granted role: {SA_ROLE}            │
│                                                             │
│  Network Rule:       {SA_USER}_NETWORK_RULE                 │
│                      └── Allows your current IP             │
│                                                             │
│  Network Policy:     {SA_USER}_NETWORK_POLICY               │
│                      └── References network rule            │
│                                                             │
│  Auth Policy:        {SA_USER}_AUTH_POLICY                  │
│                      └── PAT-only authentication            │
│                                                             │
│  PAT:                {SA_USER}_PAT                          │
│                      └── Role restriction: {SA_ROLE}        │
└─────────────────────────────────────────────────────────────┘
```

### Commands

| Command | Description |
|---------|-------------|
| `pat:create` | Create/rotate PAT for service user |
| `pat:no-rotate` | Remove existing PAT and create new (allows changing role) |
| `pat:remove` | Remove PAT and associated objects |

### Two Roles Explained

| Role | Purpose | Example |
|------|---------|---------|
| `SA_ROLE` | Role restriction for the PAT — what the service account can do | `DEMO_ROLE` |
| `SA_ADMIN_ROLE` | Role for creating policies/rules — needs elevated privileges | `SYSADMIN` |

### Examples

```bash
# Create PAT with separate admin role
snow-utils pat:create SA_USER=my_sa SA_ROLE=demo_role SA_ADMIN_ROLE=sysadmin PAT_OBJECTS_DB=my_db

# Create PAT (admin-role defaults to SA_ROLE)
snow-utils pat:create SA_USER=my_sa SA_ROLE=my_role PAT_OBJECTS_DB=my_db

# Create using env vars from .env file
snow-utils pat:create

# Remove and recreate PAT (to change role restriction)
snow-utils pat:no-rotate

# Remove PAT and policies (keeps user)
snow-utils pat:remove SA_USER=my_sa PAT_OBJECTS_DB=my_db

# Remove only the PAT (keep network/auth policies)
snow-utils pat:remove -- --pat-only

# Remove everything including the service user
snow-utils pat:remove -- --drop-user
```

### Using the PAT

After creation, the PAT token is saved to your `.env` file as `SNOWFLAKE_PASSWORD`. Use it:

```bash
# In your application
export SNOWFLAKE_USER=$SA_USER
export SNOWFLAKE_PASSWORD='<pat_token>'
export SNOWFLAKE_ACCOUNT='<your_account>'

# Or with snow CLI
snow sql --user $SA_USER --account $ACCOUNT -q "SELECT 1"
```

---

## Network Management

> [!NOTE]
> **Snowflake Docs:**
> - [CREATE NETWORK RULE](https://docs.snowflake.com/en/sql-reference/sql/create-network-rule)
> - [CREATE NETWORK POLICY](https://docs.snowflake.com/en/sql-reference/sql/create-network-policy)
> - [ALTER NETWORK POLICY](https://docs.snowflake.com/en/sql-reference/sql/alter-network-policy)
> - [Network Rule Modes and Types](https://docs.snowflake.com/en/user-guide/network-rules)

### Required Privileges

| Privilege | Used For |
|-----------|----------|
| `CREATE SCHEMA` on database | Create NETWORKS schema (if missing) |
| `CREATE NETWORK RULE` on schema | Create network rules |
| `CREATE NETWORK POLICY` on account | Create network policies |
| `ALTER USER` | Assign network policy to user |

> [!TIP]
> `ACCOUNTADMIN` or `SECURITYADMIN` have all required privileges. Minimum custom role:
> ```sql
> GRANT CREATE NETWORK POLICY ON ACCOUNT TO ROLE network_admin;
> GRANT CREATE SCHEMA ON DATABASE my_db TO ROLE network_admin;
> GRANT USAGE ON DATABASE my_db TO ROLE network_admin;
> ```

### What Gets Created

When you run `networks:create`, the following resources are provisioned:

```
┌─────────────────────────────────────────────────────────────┐
│                      Snowflake                              │
├─────────────────────────────────────────────────────────────┤
│  Network Rule:     {DB}.{SCHEMA}.{NAME}                     │
│                    └── MODE: INGRESS/EGRESS/etc.            │
│                    └── TYPE: IPV4/HOST_PORT/etc.            │
│                    └── VALUE_LIST: IPs or hostnames         │
│                                                             │
│  Network Policy:   {POLICY_NAME} (optional)                 │
│                    └── ALLOWED_NETWORK_RULE_LIST            │
└─────────────────────────────────────────────────────────────┘
```

### Network Rule Modes & Types

| Mode | Type | Use Case |
|------|------|----------|
| `INGRESS` | `IPV4` | Allow client connections from specific IPs |
| `INGRESS` | `AWSVPCEID` | Allow connections from AWS VPC endpoints |
| `EGRESS` | `HOST_PORT` | Allow external network access (UDFs, procedures) |
| `EGRESS` | `PRIVATE_HOST_PORT` | Allow private endpoint access |
| `INTERNAL_STAGE` | `HOST_PORT` | Allow stage access to external endpoints |
| `POSTGRES_INGRESS` | `IPV4` | Allow PostgreSQL-protocol connections |
| `POSTGRES_EGRESS` | `HOST_PORT` | Allow outbound PostgreSQL connections |

### Built-in IPv4 Presets

| Preset | Description | Command |
|--------|-------------|---------|
| **Local IP** | Your current public IP | `--with-local` (default) |
| **GitHub Actions** | GitHub Actions runner IPs | `--with-gh` |
| **Google** | Google IP ranges | `--with-google` |

### Commands

| Command | Description |
|---------|-------------|
| `networks:create` | Create a network rule with optional policy |
| `networks:github` | Create rule for GitHub Actions IPs |
| `networks:google` | Create rule for Google IPs |
| `networks:local` | Create rule for current IP only |
| `networks:policy` | Create or alter a network policy |
| `networks:list-rules` | List network rules in a schema |
| `networks:list-policies` | List all network policies |
| `networks:delete-rule` | Delete a network rule |
| `networks:delete-policy` | Delete a network policy |

### Examples

```bash
# Create rule for local IP only (most restrictive)
snow-utils networks:local NW_RULE_NAME=dev_access NW_RULE_DB=my_db

# Create rule for GitHub Actions CI/CD
snow-utils networks:github NW_RULE_NAME=ci_access NW_RULE_DB=my_db

# Create rule combining local + GitHub IPs
snow-utils networks:create NW_RULE_NAME=dev_ci NW_RULE_DB=my_db -- --with-local --with-gh

# Create rule with custom CIDRs
snow-utils networks:create NW_RULE_NAME=office NW_RULE_DB=my_db -- --values "10.0.0.0/8,192.168.1.0/24"

# Create egress rule for API access
snow-utils networks:create NW_RULE_NAME=api_egress NW_RULE_DB=my_db -- \
  --mode egress --type host_port --values "api.example.com:443"

# Create rule AND policy together
snow-utils networks:create NW_RULE_NAME=dev_rule NW_RULE_DB=my_db -- --policy dev_policy

# Add rule to existing policy
snow-utils networks:create NW_RULE_NAME=new_rule NW_RULE_DB=my_db -- \
  --policy existing_policy --policy-mode alter

# Create/alter policy with specific rules
snow-utils networks:policy -- --name my_policy --rules "DB.NETWORKS.RULE1,DB.NETWORKS.RULE2"
snow-utils networks:policy -- --name my_policy --rules "DB.NETWORKS.RULE3" --alter

# List rules and policies
snow-utils networks:list-rules NW_RULE_DB=my_db
snow-utils networks:list-policies

# Delete rule
snow-utils networks:delete-rule NW_RULE_NAME=old_rule NW_RULE_DB=my_db

# Delete policy (optionally unset from user first)
snow-utils networks:delete-policy -- --name my_policy --user my_user
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NW_RULE_NAME` | Network rule name | - |
| `NW_RULE_DB` | Database for network rule | - |
| `NW_RULE_SCHEMA` | Schema for network rule | `NETWORKS` |

---

## Snowflake & AWS Shortcuts

### Snowflake Commands

| Command | Description |
|---------|-------------|
| `snow:test` | Test Snowflake connection |
| `snow:sql` | Run SQL query |
| `snow:volumes` | List all external volumes |
| `snow:pats` | List programmatic access tokens |

```bash
snow-utils snow:test
snow-utils snow:sql -- "SELECT CURRENT_TIMESTAMP()"
snow-utils snow:volumes
snow-utils snow:pats PAT_USER=my_service_user
```

### AWS Commands

| Command | Description |
|---------|-------------|
| `aws:whoami` | Show current AWS identity |
| `aws:buckets` | List S3 buckets (filtered by prefix, defaults to username) |
| `aws:roles` | List IAM roles (filtered by prefix, defaults to username) |

```bash
snow-utils aws:whoami
snow-utils aws:buckets                    # filter by your username
snow-utils aws:buckets PREFIX=myproject   # filter by custom prefix
snow-utils aws:roles PREFIX=myproject
```

---

## Naming Conventions

Resources are **prefixed with your username** by default to avoid conflicts in shared accounts.

### Example (BUCKET=iceberg-demo, user: ksampath)

| Type | Resource | Name |
|------|----------|------|
| AWS | S3 Bucket | `ksampath-iceberg-demo` |
| AWS | IAM Role | `ksampath-iceberg-demo-snowflake-role` |
| AWS | IAM Policy | `ksampath-iceberg-demo-snowflake-policy` |
| Snowflake | External Volume | `KSAMPATH_ICEBERG_DEMO_EXTERNAL_VOLUME` |

### Customizing Prefixes

```bash
# Default: username prefix
snow-utils extvolume:create BUCKET=data
# → ksampath-data

# No prefix
snow-utils extvolume:create BUCKET=data -- --no-prefix
# → data

# Custom prefix
snow-utils extvolume:create BUCKET=data -- --prefix myproject
# → myproject-data
```

---

## Environment Variables Reference

All variables can be set in `.env` or exported in your shell.

### Snowflake Connection

| Variable | Description | Default |
|----------|-------------|---------|
| `SNOWFLAKE_DEFAULT_CONNECTION_NAME` | Snowflake connection profile | - |
| `SNOWFLAKE_ROLE` | Snowflake role to use | - |
| `SNOWFLAKE_DATABASE` | Default database | - |

### AWS Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region for resources | `us-west-2` |

### External Volume

| Variable | Description | Default |
|----------|-------------|---------|
| `BUCKET` | S3 bucket base name | `iceberg-demo` |
| `EXTERNAL_VOLUME_NAME` | Snowflake external volume name | - |

### PAT Management

| Variable | Description | Default |
|----------|-------------|---------|
| `SA_USER` | Service account username | - |
| `SA_ROLE` | Role restriction for PAT | - |
| `SA_ADMIN_ROLE` | Admin role for creating policies | `SA_ROLE` |
| `PAT_OBJECTS_DB` | Database for PAT objects | - |
| `DOT_ENV_FILE` | Path to .env file for credentials | `.env` |

---

## Debugging

Both `pat.py`, `extvolume.py`, and `network.py` support verbose and debug modes for troubleshooting:

```bash
# Verbose mode - shows info level output from snow CLI
snow-utils --verbose extvolume:create BUCKET=my-data
snow-utils pat:create -v SA_USER=my_sa ...
snow-utils networks:create -v NW_RULE_NAME=my_rule ...

# Debug mode - shows SQL statements and full output
snow-utils --debug extvolume:create BUCKET=my-data
snow-utils pat:create -d SA_USER=my_sa ...
snow-utils networks:create -d NW_RULE_NAME=my_rule ...
```

| Flag | Short | Effect |
|------|-------|--------|
| `--verbose` | `-v` | Info level logging from snow CLI |
| `--debug` | `-d` | Debug output including SQL statements |

> [!IMPORTANT]
> Place the flag **before** the subcommand: `snow-utils --debug extvolume:create`

---

## Troubleshooting

### External Volume Issues

**"STORAGE_AWS_IAM_USER_ARN not found"**

```bash
# Re-sync the trust policy
snow-utils extvolume:update-trust BUCKET=my-data
```

**"External volume verification failed"**

```bash
# Check IAM trust policy is correct
aws iam get-role --role-name {username}-{bucket}-snowflake-role

# Verify external volume settings
snow-utils extvolume:describe VOLUME=MY_VOLUME
```

### PAT Issues

**"PAT authentication failed"**

- Ensure network policy allows your IP
- Check PAT hasn't expired: `snow-utils snow:pats`
- Verify role is granted to user

**"DOT_ENV_FILE not updating the right file"**

```bash
# Specify absolute path
snow-utils pat DOT_ENV_FILE=/absolute/path/to/project/.env
```

### Network Issues

**"Network policy blocking connections"**

```bash
# List rules to see what IPs are allowed
snow-utils networks:list-rules NW_RULE_DB=my_db

# Check your current IP
curl -s https://api.ipify.org

# Update rule with your current IP
snow-utils networks:local NW_RULE_NAME=dev_access NW_RULE_DB=my_db
```

**"GitHub Actions failing to connect"**

- GitHub periodically updates their IP ranges
- Re-run `networks:github` to fetch latest IPs
- Note: GitHub has many IPs; rules are cached for 1 hour

### General Issues

**"snow command not found"**

```bash
pip install snowflake-cli-labs
```

**"Task not found"**

```bash
brew install go-task
```

**"Permission denied" on AWS operations**

- Verify AWS credentials: `snow-utils aws:whoami`
- Check IAM permissions for S3 and IAM operations

---

## Getting Help

```bash
# List all tasks
snow-utils --help

# Get detailed help for a specific task
snow-utils <task-name> --summary

# Examples
snow-utils extvolume:create --summary
snow-utils pat:create --summary
snow-utils networks:create --summary
snow-utils help:naming
snow-utils help:networks
```

---

## Use Cases

### Iceberg Tables with Snowflake-Managed Catalog

Once your external volume is set up, create Iceberg tables backed by S3:

```sql
CREATE ICEBERG TABLE my_catalog.my_schema.events (
    event_id INT,
    event_type STRING,
    created_at TIMESTAMP
)
  CATALOG = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'MY_EXTERNAL_VOLUME'
  BASE_LOCATION = 'events/';
```

See [Snowflake Iceberg Tables Documentation](https://docs.snowflake.com/en/user-guide/tables-iceberg) for more.

### Service Account Automation

Use PATs for CI/CD pipelines, scheduled jobs, or any programmatic Snowflake access:

- **GitHub Actions** — Automate data pipelines with Snowflake CLI
- **Airflow/Dagster** — Connect orchestrators to Snowflake securely
- **dbt** — Run dbt jobs with service account credentials

---

## Development

```bash
# Setup environment
task setup              # or: uv venv && uv sync

# Install dependencies
task install            # or: uv sync

# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Lint and fix
uv run ruff check . --fix
```

---

## License

Apache License 2.0 — See [LICENSE](LICENSE) for details.

Copyright 2024 Kamesh Sampath
