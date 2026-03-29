# Veeam Presence — Deployment Runbook

## Who This Is For

Platform / DevOps team deploying Presence to production.

## What You're Deploying

Three containers behind Azure Bot Service:

1. **Presence Agent Service** — Python FastAPI app that handles the AI logic. Receives questions, calls Claude (Anthropic API) with tools, returns answers. Port 8000. Internal only (not public).
2. **M365 Gateway** — Thin wrapper that connects Microsoft Teams and Copilot to the agent service. Handles authentication, typing indicators, and Adaptive Card rendering. Port 3978. Public (receives webhooks from Microsoft).
3. **Pipeline Job** — Scheduled nightly job that pulls attendance data from Databricks, computes baselines and analytics, writes output files. The agent service reads these files. No AI calls needed.

## Prerequisites

- Azure subscription with permissions to create: Container Apps, Key Vault, Bot Service, Azure Files
- Azure Container Registry (or any container registry)
- Microsoft 365 admin access (for uploading custom Teams apps)

## Credentials to Create

**Do NOT use personal tokens for production.** Create dedicated service accounts:

| Secret | What to create | Who creates it |
|--------|---------------|----------------|
| `ANTHROPIC_API_KEY` | Org-level API key at console.anthropic.com. Set spend limit (~$150/month is plenty). | Presence dev team or API admin |
| `DATABRICKS_HOST` | Workspace hostname: `adb-1715711735713564.4.azuredatabricks.net` | Already known |
| `DATABRICKS_TOKEN` | **Service principal PAT** — create a Databricks service principal with READ access to `dev_catalog.jf_salesforce_bronze.office_occupancy_o_365_verkada` and `dev_catalog.revenue_intelligence.workday_enhanced`. Do not use a personal token. | Databricks admin |
| `DATABRICKS_HTTP_PATH` | SQL warehouse path: `/sql/1.0/warehouses/be160f1edb836d88` | Already known |
| `BOT_APP_ID` | Microsoft Entra app registration (see Step 2) | DevOps |
| `BOT_APP_PASSWORD` | Client secret from the Entra registration | DevOps |

## Step 1: Create Azure Key Vault

```bash
az group create --name rg-presence --location eastus

az keyvault create --name kv-presence --resource-group rg-presence --location eastus

az keyvault secret set --vault-name kv-presence --name ANTHROPIC-API-KEY --value '<key>'
az keyvault secret set --vault-name kv-presence --name DATABRICKS-HOST --value '<host>'
az keyvault secret set --vault-name kv-presence --name DATABRICKS-TOKEN --value '<token>'
az keyvault secret set --vault-name kv-presence --name DATABRICKS-HTTP-PATH --value '<path>'
az keyvault secret set --vault-name kv-presence --name BOT-APP-ID --value '<app-id>'
az keyvault secret set --vault-name kv-presence --name BOT-APP-PASSWORD --value '<app-password>'
```

## Step 2: Create Microsoft Entra App Registrations

**Agent Service App:**
1. Azure Portal → Entra ID → App registrations → New
2. Name: `Presence Agent Service`
3. Single tenant
4. Note the Application (client) ID

**Gateway/Bot App:**
1. New registration → `Presence Gateway`
2. Single tenant
3. Generate client secret → save as BOT_APP_PASSWORD
4. Note Application ID → save as BOT_APP_ID

## Step 3: Build and Push Container Images

```bash
# Agent service
docker build -t presence-agent:latest -f Dockerfile .
docker tag presence-agent:latest <your-acr>.azurecr.io/presence-agent:latest
docker push <your-acr>.azurecr.io/presence-agent:latest

# Gateway
docker build -t presence-gateway:latest -f gateway/Dockerfile ./gateway
docker tag presence-gateway:latest <your-acr>.azurecr.io/presence-gateway:latest
docker push <your-acr>.azurecr.io/presence-gateway:latest

# Pipeline job
docker build -t presence-pipeline:latest -f Dockerfile.pipeline .
docker tag presence-pipeline:latest <your-acr>.azurecr.io/presence-pipeline:latest
docker push <your-acr>.azurecr.io/presence-pipeline:latest
```

## Step 4: Deploy to Azure Container Apps

```bash
# Create environment
az containerapp env create \
  --name presence-env \
  --resource-group rg-presence \
  --location eastus

# Deploy agent service (internal, not public)
az containerapp create \
  --name presence-agent \
  --resource-group rg-presence \
  --environment presence-env \
  --image <your-acr>.azurecr.io/presence-agent:latest \
  --target-port 8000 \
  --ingress internal \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 1 --memory 2Gi \
  --secrets \
    anthropic-key=keyvaultref:kv-presence/ANTHROPIC-API-KEY,identityref:<managed-identity> \
    dbx-host=keyvaultref:kv-presence/DATABRICKS-HOST,identityref:<managed-identity> \
    dbx-token=keyvaultref:kv-presence/DATABRICKS-TOKEN,identityref:<managed-identity> \
    dbx-path=keyvaultref:kv-presence/DATABRICKS-HTTP-PATH,identityref:<managed-identity> \
  --env-vars \
    ANTHROPIC_API_KEY=secretref:anthropic-key \
    DATABRICKS_HOST=secretref:dbx-host \
    DATABRICKS_TOKEN=secretref:dbx-token \
    DATABRICKS_HTTP_PATH=secretref:dbx-path

# Deploy gateway (public, receives webhooks)
az containerapp create \
  --name presence-gateway \
  --resource-group rg-presence \
  --environment presence-env \
  --image <your-acr>.azurecr.io/presence-gateway:latest \
  --target-port 3978 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 0.5 --memory 1Gi \
  --secrets \
    bot-id=keyvaultref:kv-presence/BOT-APP-ID,identityref:<managed-identity> \
    bot-pwd=keyvaultref:kv-presence/BOT-APP-PASSWORD,identityref:<managed-identity> \
  --env-vars \
    BOT_APP_ID=secretref:bot-id \
    BOT_APP_PASSWORD=secretref:bot-pwd \
    AGENT_SERVICE_URL=https://presence-agent.internal.<env-domain>
```

Note the gateway's public URL for bot registration.

## Step 5: Nightly Pipeline Job (Option A — Recommended)

The pipeline refreshes attendance data daily. Deploy as a scheduled Container App Job:

```bash
az containerapp job create \
  --name presence-pipeline \
  --resource-group rg-presence \
  --environment presence-env \
  --image <your-acr>.azurecr.io/presence-pipeline:latest \
  --trigger-type Schedule \
  --cron-expression "0 2 * * *" \
  --cpu 1 --memory 2Gi \
  --replica-timeout 600 \
  --secrets \
    dbx-host=keyvaultref:kv-presence/DATABRICKS-HOST,identityref:<managed-identity> \
    dbx-token=keyvaultref:kv-presence/DATABRICKS-TOKEN,identityref:<managed-identity> \
    dbx-path=keyvaultref:kv-presence/DATABRICKS-HTTP-PATH,identityref:<managed-identity> \
  --env-vars \
    DATABRICKS_HOST=secretref:dbx-host \
    DATABRICKS_TOKEN=secretref:dbx-token \
    DATABRICKS_HTTP_PATH=secretref:dbx-path
```

**Important:** The pipeline job and agent service must share a storage volume for the pickle files. Use Azure Files or Blob Storage mounted to both:

```bash
az containerapp env storage set \
  --name presence-env \
  --resource-group rg-presence \
  --storage-name presence-data \
  --azure-file-account-name <storage-account> \
  --azure-file-share-name presence-data \
  --azure-file-account-key <key> \
  --access-mode ReadWrite
```

Then add `--volume presence-data=presence-data:/app/data` to both the agent and pipeline job create commands.

### Option B: Manual Refresh (Pilot Only)

For pilot testing, the dev team runs the pipeline locally and copies pickle files to the agent container:

```bash
# On dev machine (Windows, has Databricks access)
powershell -ExecutionPolicy Bypass -File run_pipeline.ps1

# Copy data to container (or mount as volume)
az containerapp exec --name presence-agent --resource-group rg-presence -- mkdir -p /app/data
# Upload pickle files via Azure Files mount
```

## Step 6: Register Azure Bot Service

1. Azure Portal → Create resource → Azure Bot
2. Bot handle: `VeeamPresence`
3. App type: Single Tenant
4. App ID: use the Gateway app registration ID
5. Messaging endpoint: `https://<gateway-public-url>/api/messages`
6. Enable channels: Microsoft Teams + Microsoft 365 (Copilot)

## Step 7: Create and Upload App Package

1. Edit `appPackage/manifest.json`:
   - Set `id` to a new GUID
   - Set `botId` to the Gateway app registration ID
2. Convert `appPackage/icon-color.svg` to `icon-color.png` (192x192)
3. Convert `appPackage/icon-outline.svg` to `icon-outline.png` (32x32)
4. Zip the appPackage directory (manifest.json + both PNGs)
5. Teams Admin Center → Manage Apps → Upload custom app
6. Create App Setup Policy → pin for `SG-Presence-Users` security group

## Step 8: Verify

1. Health: `curl https://<gateway-public-url>/health`
2. Open Teams → find "Veeam Presence" → start chat
3. Verify welcome card appears
4. Click "Daily briefing" → verify office list
5. Ask "Who's showing up the most in Prague?" → verify leaderboard
6. Ask "Who is traveling between offices?" → verify visitor data

## Step 9: Distribute to Pilot Users

**For pilot (3-5 people):** Sideload the app directly to test users. No AD group needed.

1. Teams Admin Center → Manage Apps → Upload custom app → upload the zip
2. Assign the app to specific pilot users via App Setup Policy
3. Pilot users find "Veeam Presence" in their Teams apps

**For broader rollout (later):** Create an Azure AD security group (`SG-Presence-Users`), add members, and target the App Setup Policy to that group. This scales without touching individual users.

## Monitoring

- **Container logs:** Container Apps → presence-agent → Log stream
- **Pipeline logs:** Container Apps → Jobs → presence-pipeline → Execution history
- **Cost:** Monitor Anthropic API at console.anthropic.com

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Bot doesn't respond | Gateway logs — is webhook receiving? |
| "Something went wrong" | Agent logs — Claude API error? Databricks down? |
| Stale data | Pipeline job — did it run? Check execution history |
| Cards don't render | Paste card JSON into adaptivecards.io/designer |
| "Access denied" | Is user in SG-Presence-Users? |
| Slow responses | Agent logs — tool latency. Databricks cold-starting? |

## Monthly Cost Estimate

| Resource | Cost |
|----------|------|
| Container App (agent, 1 vCPU/2GB, always on) | ~$30-50 |
| Container App (gateway, 0.5 vCPU/1GB, always on) | ~$15-25 |
| Container App Job (pipeline, 1 vCPU/2GB, 1 min/day) | ~$1 |
| Azure Bot Service | Free tier |
| Azure Files (shared storage) | ~$1 |
| Anthropic API (~20 queries/day) | ~$15-30 |
| **Total** | **~$62-107/month** |
