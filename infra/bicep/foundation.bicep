// Veeam Presence — Foundation infrastructure
// Creates: Log Analytics, Key Vault, Azure Container Registry
// Optionally creates: VNet, Private DNS Zones (when secureDeployment=true)
// Azure OpenAI + model deployment handled by deploy-foundation.sh (CLI)

@description('Location for all resources')
param location string = resourceGroup().location

@description('Environment name suffix')
param envSuffix string = 'dev'

@description('Common resource name prefix')
param namePrefix string = 'presence'

@description('Enable VNet-secured deployment with private endpoints')
param secureDeployment bool = false

@description('VNet address space')
param vnetAddressSpace string = '10.42.0.0/16'

@description('ACA infrastructure subnet CIDR')
param acaSubnetPrefix string = '10.42.0.0/23'

@description('Private endpoints subnet CIDR')
param privateEndpointSubnetPrefix string = '10.42.4.0/24'

param vnetName string = '${namePrefix}-vnet'
param acaSubnetName string = 'aca-infra'
param privateEndpointSubnetName string = 'private-endpoints'

var uniqueSuffix = uniqueString(resourceGroup().id)
var logWorkspaceName = '${namePrefix}-logs-${envSuffix}'
var keyVaultName = '${namePrefix}-kv-${envSuffix}-${take(uniqueSuffix, 6)}'
var acrName = '${namePrefix}acr${envSuffix}${take(uniqueSuffix, 6)}'

// --- Log Analytics Workspace ---
resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// --- Key Vault ---
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: secureDeployment ? 'Disabled' : 'Enabled'
  }
}

// --- Azure Container Registry ---
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: secureDeployment ? 'Premium' : 'Basic'
  }
  properties: {
    adminUserEnabled: true
    // az acr build runs from Microsoft-managed infra and needs public reachability
    publicNetworkAccess: 'Enabled'
  }
}

// --- VNet (secure mode only) ---
resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = if (secureDeployment) {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressSpace
      ]
    }
    subnets: [
      {
        name: acaSubnetName
        properties: {
          addressPrefix: acaSubnetPrefix
          delegations: [
            {
              name: 'acaDelegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: privateEndpointSubnetName
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// --- Private DNS Zones (secure mode only) ---
resource openaiDns 'Microsoft.Network/privateDnsZones@2020-06-01' = if (secureDeployment) {
  name: 'privatelink.openai.azure.com'
  location: 'global'
}

resource vaultDns 'Microsoft.Network/privateDnsZones@2020-06-01' = if (secureDeployment) {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
}

// --- VNet links for DNS zones ---
resource openaiDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (secureDeployment) {
  name: '${openaiDns.name}/${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource vaultDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (secureDeployment) {
  name: '${vaultDns.name}/${vnetName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

// --- Outputs ---
output secureDeploymentMode bool = secureDeployment
output logWorkspaceId string = logWorkspace.id
output logWorkspaceName string = logWorkspace.name
output keyVaultName string = keyVault.name
output keyVaultId string = keyVault.id
output keyVaultUri string = keyVault.properties.vaultUri
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output vnetId string = secureDeployment ? vnet.id : ''
output acaSubnetId string = secureDeployment ? resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, acaSubnetName) : ''
output privateEndpointSubnetId string = secureDeployment ? resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, privateEndpointSubnetName) : ''
