# Veeam Presence — Infra Team Repo Setup Plan

This document tells the infra team what to configure so the CI/CD pipeline works.
The setup is two phases:

1. **Phase 1 (manual, before first merge):** Provide basic inputs, set up OIDC, create GitHub environments with seed variables
2. **Phase 2 (automated, bootstrap workflow):** The `bootstrap-foundation` workflow provisions all Azure resources (ACR, ACA environment, Key Vault, OpenAI, networking) and outputs resource names — those get back-filled into GitHub environment variables

Only **Databricks** is pre-existing. Everything else is created by the bootstrap or deploy workflows.

---

## Phase 1: Pre-Requisites (Manual)

### 1.1 Basic Inputs Required From Team

These are the only values needed before anything can run:

```
AZURE_TENANT_ID=<your-entra-tenant-id>
AZURE_SUBSCRIPTION_ID=<your-azure-subscription-id>
AZURE_RESOURCE_GROUP=rg-presence-int          # choose a name
AZURE_LOCATION=eastus2
INFRA_NAME_PREFIX=presence                    # used by Bicep to derive all resource names
DATABRICKS_HOST=<existing Databricks workspace URL, e.g. adb-xxxxx.azuredatabricks.net>
DATABRICKS_AZURE_RESOURCE_ID=<Azure resource ID of the Databricks workspace>
DATABRICKS_WAREHOUSE_ID=<existing SQL warehouse ID>
```

**Databricks authentication uses Entra ID (MSI) — no PAT or service principal token needed.**
The Presence agent's system-assigned managed identity authenticates to Databricks via
`DefaultAzureCredential`. The agent Container App's identity must be granted access to the
Databricks workspace (see Phase 2.3).

### 1.2 Branch Model

Create and protect three long-lived branches:

| Branch | Purpose | PR required? | Status checks |
|--------|---------|-------------|---------------|
| `dev` | Engineering integration | Yes | `CI` workflow must pass |
| `integration` | Non-prod Azure deployment | Yes (from `dev`) | `CI` workflow must pass |
| `main` | Production | Yes (from `integration`) | `CI` workflow must pass |

Feature branches (`feature/*`, `features/*`) are developer working branches — no
protection needed.

#### Branch protection rules (Settings > Branches > Add rule)

**`dev`**
- Require a pull request before merging (1 reviewer)
- Require status checks: `CI / Python Tests`, `CI / Docker Build Smoke`
- Do not allow bypassing the above settings

**`integration`**
- Require a pull request before merging (1 reviewer)
- Require status checks: `CI / Python Tests`, `CI / Docker Build Smoke`
- Restrict who can push: infra team only
- Do not allow bypassing the above settings

**`main`**
- Require a pull request before merging (1 reviewer from infra team)
- Require status checks: `CI / Python Tests`, `CI / Docker Build Smoke`
- Prevent self-review
- Restrict who can push: infra team only
- Do not allow bypassing the above settings

### 1.3 GitHub Environments (Create Empty Shells)

Create four environments in Settings > Environments. You'll populate variables
after OIDC setup (1.4) and after bootstrap (Phase 2).

| Environment | Branch policy | Reviewer gate |
|-------------|--------------|---------------|
| `integration` | `integration` branch only | Optional |
| `production` | `main` branch only | Required (infra team, prevent self-review) |
| `teams-catalog-admin` | Manual only | Required (M365 admin) |
| `bootstrap-foundation` | Manual only | Required (infra team) |

### 1.4 OIDC Authentication (Azure to GitHub Actions)

#### How It Works

Traditional CI/CD stores long-lived Azure credentials (client secret or certificate)
as GitHub secrets. OIDC eliminates this — no Azure secrets are stored in GitHub at all.

The flow for every workflow run:

```
GitHub Actions runner                    Entra ID (Azure AD)
       |                                        |
  1.   |-- requests OIDC token from GitHub ----->|
       |   (contains: repo, branch, env name)   |
       |                                        |
  2.   |<--- GitHub issues signed JWT ----------|
       |   (signed by GitHub's OIDC provider)   |
       |                                        |
  3.   |-- presents JWT to Entra ID ----------->|
       |   "I am repo:Veeam.../Veeam_Presence  |
       |    running in environment:integration" |
       |                                        |
  4.   |   Entra ID validates:                  |
       |   - JWT signature (GitHub's public key)|
       |   - issuer = token.actions.github...   |
       |   - subject matches federated cred     |
       |   - audience = api://AzureADToken...   |
       |                                        |
  5.   |<--- returns Azure access token --------|
       |   (scoped to the service principal's   |
       |    RBAC assignments)                   |
       |                                        |
  6.   |-- uses Azure token for az CLI, ------->|  Azure Resources
       |   ACR push, ACA deploy, etc.           |
```

**Key security properties:**
- **No stored secrets** — nothing to rotate, nothing to leak
- **Environment-scoped** — the `integration` identity can ONLY be used by workflows
  running in the `integration` GitHub environment (which is branch-locked to the
  `integration` branch). A feature branch cannot impersonate integration.
- **Short-lived** — tokens expire in minutes, not months
- **Auditable** — every token exchange appears in Entra ID sign-in logs

#### In the Workflows

Every deploy workflow uses `azure/login@v3` with OIDC. The workflow must declare
`permissions: id-token: write` to request the GitHub OIDC token:

```yaml
permissions:
  contents: read
  id-token: write      # required for OIDC

steps:
  - uses: azure/login@v3
    with:
      client-id: ${{ vars.AZURE_CLIENT_ID }}       # from GitHub environment variable
      tenant-id: ${{ vars.AZURE_TENANT_ID }}        # from GitHub environment variable
      subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}  # from GitHub environment variable
      # No client-secret — OIDC handles authentication
```

After this step, all subsequent `az` CLI commands and Azure SDK calls in the workflow
are authenticated as the service principal.

#### Identity-to-Environment Mapping

Each GitHub environment maps to a dedicated Entra app registration. This is the
trust boundary — the federated credential's `subject` filter locks the identity
to a specific repo + environment combination.

| GitHub Environment | Entra App Display Name | Subject Filter | RBAC |
|---|---|---|---|
| `integration` | `gh-presence-integration` | `repo:Veeam-CT-RevenueIntelligence/Veeam_Presence:environment:integration` | Contributor + AcrPush + KV Secrets User |
| `production` | `gh-presence-production` | `repo:Veeam-CT-RevenueIntelligence/Veeam_Presence:environment:production` | Contributor + KV Secrets User (no AcrPush) |
| `bootstrap-foundation` | `gh-presence-bootstrap-foundation` (optional) | `repo:Veeam-CT-RevenueIntelligence/Veeam_Presence:environment:bootstrap-foundation` | Contributor |

Production intentionally has **no `AcrPush`** — it pulls images that were already
built and tested in integration. This prevents production workflows from
modifying container images.

#### Prerequisites

The person running the OIDC setup commands needs:
- **Entra ID role:** `Application Administrator` or `Cloud Application Administrator`
- **Azure RBAC:** `User Access Administrator` or `Owner` on the target resource group
  (to assign roles to the new service principals)

#### Creating the Identities

##### Integration Identity

```bash
# Create app registration
az ad app create --display-name "gh-presence-integration"
# Note the appId output — this becomes AZURE_CLIENT_ID for the integration environment

# Create service principal
az ad sp create --id <app-id>

# Add federated credential
az ad app federated-credential create --id <app-object-id> --parameters '{
  "name": "github-integration",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:Veeam-CT-RevenueIntelligence/Veeam_Presence:environment:integration",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "GitHub Actions OIDC for integration environment"
}'

# RBAC — Contributor on the resource group
az role assignment create --assignee <app-id> --role "Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>"
```

> **Note:** `AcrPush` and `Key Vault Secrets User` roles are granted AFTER bootstrap
> creates those resources (see Phase 2 post-bootstrap steps).

##### Production Identity

```bash
az ad app create --display-name "gh-presence-production"
az ad sp create --id <app-id>

az ad app federated-credential create --id <app-object-id> --parameters '{
  "name": "github-production",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:Veeam-CT-RevenueIntelligence/Veeam_Presence:environment:production",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "GitHub Actions OIDC for production environment"
}'

# Contributor only — production does NOT push images
az role assignment create --assignee <app-id> --role "Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg-prod>"
```

##### Bootstrap Identity (Optional)

Can reuse the integration identity for initial setup, or create a dedicated one:

```bash
az ad app create --display-name "gh-presence-bootstrap-foundation"
az ad sp create --id <app-id>

az ad app federated-credential create --id <app-object-id> --parameters '{
  "name": "github-bootstrap",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:Veeam-CT-RevenueIntelligence/Veeam_Presence:environment:bootstrap-foundation",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "GitHub Actions OIDC for bootstrap-foundation environment"
}'
```

### 1.5 Seed GitHub Environment Variables (Phase 1 values only)

After OIDC setup, populate environments with the values you know now.

#### `bootstrap-foundation` environment:

| Variable | Value |
|----------|-------|
| `AZURE_CLIENT_ID` | *(from bootstrap or integration app registration)* |
| `AZURE_TENANT_ID` | *(from 1.1)* |
| `AZURE_SUBSCRIPTION_ID` | *(from 1.1)* |
| `AZURE_RESOURCE_GROUP` | `rg-presence-int` |
| `AZURE_LOCATION` | `eastus2` |
| `INFRA_NAME_PREFIX` | `presence` |

#### `integration` environment (seed — more variables added after bootstrap):

| Variable | Value |
|----------|-------|
| `AZURE_CLIENT_ID` | *(from integration app registration)* |
| `AZURE_TENANT_ID` | *(from 1.1)* |
| `AZURE_SUBSCRIPTION_ID` | *(from 1.1)* |
| `AZURE_RESOURCE_GROUP` | `rg-presence-int` |
| `AZURE_LOCATION` | `eastus2` |
| `DATABRICKS_HOST` | *(existing — from 1.1)* |
| `DATABRICKS_AZURE_RESOURCE_ID` | *(existing — from 1.1)* |
| `DATABRICKS_WAREHOUSE_ID` | *(existing — from 1.1)* |

> **No Databricks secrets needed.** Authentication uses the agent Container App's
> system-assigned managed identity via `DefaultAzureCredential` → Entra ID token.

#### `production` environment:

Same seed shape — fill with production values when ready. Production setup
happens after integration is validated.

---

## Phase 2: Bootstrap (Automated)

### 2.1 Run the Bootstrap Foundation Workflow

Trigger the `bootstrap-foundation.yml` workflow manually from GitHub Actions.
This runs `infra/scripts/deploy-foundation.sh` which deploys `infra/bicep/foundation.bicep`
and additional CLI resources:

| Resource | Naming convention | Created by |
|----------|------------------|------------|
| Log Analytics Workspace | `{prefix}-logs-{env}` | Bicep |
| Azure Key Vault | `{prefix}-kv-{env}-{unique}` | Bicep |
| Azure Container Registry | `{prefix}acr{env}{unique}` | Bicep |
| VNet + subnets | `{prefix}-vnet` | Bicep (secure mode) |
| Private DNS Zones | standard Azure names | Bicep (secure mode) |
| ACA Environment | `{prefix}-env` | CLI (`deploy-foundation.sh`) |
| Azure OpenAI resource | `{prefix}openai` | CLI (`deploy-foundation.sh`) |
| Azure OpenAI deployment | `gpt-5.3-chat` | CLI (`deploy-foundation.sh`) |
| Private Endpoints (OpenAI, KV) | `pe-{resource}` | CLI (secure mode) |

**Not created by bootstrap** (created later by deploy workflows):

| Resource | Created by | Script |
|----------|-----------|--------|
| Agent Container App | `deploy-integration.yml` | `deploy-agent.sh` |
| Wrapper Container App | `deploy-integration.yml` | `deploy-wrapper.sh` |
| Azure Bot Service | Manual one-time setup | `create-azure-bot-resource.sh` |

### 2.2 Back-Fill GitHub Environment Variables (Post-Bootstrap)

The bootstrap outputs the created resource names via `.env.outputs`. Add them to the
`integration` environment:

| Variable | Source |
|----------|--------|
| `ACR_NAME` | `.env.outputs`: `ACR_NAME` |
| `ACA_ENV_NAME` | `.env.outputs`: `ACA_ENV_NAME` |
| `AGENT_ACA_APP_NAME` | `presence-agent-{env}` (set by `deploy-agent.sh`) |
| `WRAPPER_ACA_APP_NAME` | `presence-wrapper-{env}` (set by `deploy-wrapper.sh`) |
| `AZURE_OPENAI_ENDPOINT` | `.env.outputs`: `AZURE_OPENAI_ENDPOINT` |
| `AZURE_OPENAI_ACCOUNT_NAME` | `.env.outputs`: `AZURE_OPENAI_ACCOUNT_NAME` |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | `gpt-5.3-chat` |
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` |
| `BOT_APP_ID` | From bot app registration (see 2.6) |
| `KEYVAULT_NAME` | `.env.outputs`: `KEY_VAULT_NAME` |
| `KEYVAULT_BOT_APP_PASSWORD_NAME` | `BOT-APP-PASSWORD` |
| `ENV_SUFFIX` | `int` (integration) or `prod` (production) |
| `WRAPPER_BASE_URL` | `.env.outputs`: `WRAPPER_BASE_URL` |

### 2.3 Post-Bootstrap RBAC Grants

Now that the resources exist, add fine-grained roles:

```bash
# Integration identity — AcrPush (for CI image builds)
az role assignment create --assignee <integration-app-id> --role "AcrPush" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.ContainerRegistry/registries/<acr-name>"

# Integration identity — Key Vault Secrets User (for deploy scripts)
az role assignment create --assignee <integration-app-id> --role "Key Vault Secrets User" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<kv-name>"

# Production identity — Key Vault Secrets User only (NO AcrPush)
az role assignment create --assignee <production-app-id> --role "Key Vault Secrets User" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg-prod>/providers/Microsoft.KeyVault/vaults/<kv-name>"

# Agent Container App managed identity — Cognitive Services OpenAI User
az role assignment create \
  --assignee <agent-app-managed-identity-principal-id> \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<aoai-name>"

# Agent Container App managed identity — Databricks workspace access
# Grant the agent's MSI access to query the Databricks SQL warehouse.
# Option A: Add the MSI as a Databricks user with workspace access via SCIM:
#   az databricks workspace update ... (or via Databricks Admin Console > Users)
# Option B: Assign "Contributor" role on the Databricks Azure resource:
az role assignment create \
  --assignee <agent-app-managed-identity-principal-id> \
  --role "Contributor" \
  --scope "<DATABRICKS_AZURE_RESOURCE_ID>"
# Then grant SQL warehouse USE permission in Databricks to the MSI's service principal.
```

### 2.4 Populate Key Vault Secrets

Store runtime secrets that the Container Apps read via managed identity:

```bash
az keyvault secret set --vault-name <kv-name> --name "BOT-APP-ID" --value "<value>"
az keyvault secret set --vault-name <kv-name> --name "BOT-APP-PASSWORD" --value "<value>"
```

> **Note:** Key Vault uses hyphens, not underscores, in secret names.
>
> Databricks credentials are NOT stored in Key Vault — authentication uses the
> agent Container App's system-assigned managed identity via Entra ID.

### 2.5 Databricks Environment Variables

Databricks connection details are passed as **plain environment variables** on the
agent Container App (not secrets, since they contain no credentials):

| Env var | Value | Purpose |
|---------|-------|---------|
| `DATABRICKS_HOST` | e.g. `adb-xxxxx.azuredatabricks.net` | Workspace URL |
| `DATABRICKS_AZURE_RESOURCE_ID` | e.g. `/subscriptions/.../Microsoft.Databricks/workspaces/...` | Used by `DefaultAzureCredential` to scope the Entra ID token |
| `DATABRICKS_WAREHOUSE_ID` | e.g. `abc123def456` | SQL warehouse to execute queries against |

These are set via the deploy scripts or passed as GitHub environment variables to
the deploy workflow, which wires them into the Container App configuration.

### 2.6 Add Bot Secret to GitHub

After the Bot app registration is created (via `create-azure-bot-resource.sh`):

| Secret | Environment |
|--------|-------------|
| `BOT_APP_PASSWORD` | `integration` |
| `BOT_APP_PASSWORD` | `production` |

The deploy workflow also falls back to Key Vault if the GitHub secret is not set.

### 2.7 Configure Bot Messaging Endpoint

In Azure Portal > Bot Service > Configuration:
```
Messaging endpoint: https://<wrapper-aca-app>.azurecontainerapps.io/api/messages
```
Enable the **Microsoft Teams** channel.

---

## Checklist

### Phase 1 (before first merge)
```
[ ] Basic inputs collected (tenant, subscription, location, Databricks host/resource ID/warehouse ID)
[ ] Branches created: dev, integration, main
[ ] Branch protection rules configured
[ ] GitHub environments created: integration, production, teams-catalog-admin, bootstrap-foundation
[ ] OIDC: gh-presence-integration app + federated credential + Contributor RBAC
[ ] OIDC: gh-presence-production app + federated credential + Contributor RBAC
[ ] Seed variables set in bootstrap-foundation environment
[ ] Seed variables set in integration environment (including Databricks — no secrets needed)
```

### Phase 2 (after bootstrap runs)
```
[ ] Bootstrap foundation workflow run successfully
[ ] Generated resource names back-filled into integration environment variables
[ ] Post-bootstrap RBAC grants applied (AcrPush, Key Vault, OpenAI)
[ ] Agent MSI granted Databricks workspace access + SQL warehouse USE permission
[ ] Key Vault secrets populated (Bot only — no Databricks secrets)
[ ] Bot app registration created, messaging endpoint configured with Teams channel
[ ] BOT_APP_PASSWORD secret added to GitHub environments
[ ] Databricks env vars (HOST, AZURE_RESOURCE_ID, WAREHOUSE_ID) set in integration environment
[ ] Push to dev triggers CI workflow
[ ] Merge to integration triggers image build + deploy
[ ] Repeat Phase 2 for production environment when ready
```

---

## Quick Reference: What Exists vs What Gets Created

| Resource | Pre-existing? | Created by |
|----------|:------------:|------------|
| Databricks workspace | Yes | — (already exists) |
| Databricks SQL warehouse | Yes | — (already exists) |
| Entra tenant | Yes | — |
| Azure subscription | Yes | — |
| Resource group | **No** | Bootstrap (`deploy-foundation.sh`) |
| Log Analytics Workspace | **No** | Bootstrap (Bicep) |
| Key Vault | **No** | Bootstrap (Bicep) |
| Container Registry | **No** | Bootstrap (Bicep) |
| VNet + subnets | **No** | Bootstrap (Bicep, secure mode) |
| ACA Environment | **No** | Bootstrap (CLI) |
| Azure OpenAI + gpt-5.3-chat | **No** | Bootstrap (CLI) |
| Agent Container App | **No** | Deploy workflow (`deploy-agent.sh`) |
| Wrapper Container App | **No** | Deploy workflow (`deploy-wrapper.sh`) |
| Azure Bot Service | **No** | Manual (`create-azure-bot-resource.sh`) |
| OIDC app registrations | **No** | Manual (Phase 1.4) |
| GitHub environments | **No** | Manual (Phase 1.3) |

---

## Databricks Authentication: How It Works

The data pipeline queries Databricks SQL via the Statement Execution API. Instead of
a PAT or service principal secret, the agent Container App authenticates using its
**system-assigned managed identity** through Entra ID:

```
Agent Container App (MSI)
       |
  1.   |-- DefaultAzureCredential requests token -----> Entra ID
       |   scope: DATABRICKS_AZURE_RESOURCE_ID          |
       |                                                 |
  2.   |<--- returns Entra ID access token -------------|
       |                                                 |
  3.   |-- Bearer token in Authorization header -------> Databricks SQL API
       |   POST /api/2.0/sql/statements                   (DATABRICKS_HOST)
       |   warehouse_id: DATABRICKS_WAREHOUSE_ID
```

**Requirements:**
- Agent Container App must have a **system-assigned managed identity** enabled
- That identity must be registered as a user in the Databricks workspace
- That identity must have `CAN USE` permission on the SQL warehouse
- `DATABRICKS_HOST`, `DATABRICKS_AZURE_RESOURCE_ID`, and `DATABRICKS_WAREHOUSE_ID`
  must be set as environment variables on the Container App
