// Football Intelligence OS — Azure deployment
// Container Apps (KEDA autoscale) + Cosmos DB for MongoDB vCore (vector search) + Azure Cache for Redis
// + Azure Web PubSub + Key Vault (managed identity) + Application Insights. Azure OpenAI / Foundry and
// Azure AI Speech are existing resources whose keys are stored in Key Vault by deploy.sh.
targetScope = 'resourceGroup'

@description('Short name prefix for all resources')
param prefix string = 'fios'
param location string = resourceGroup().location
@description('Container image tags, pushed by deploy.sh')
param backendImage string
param frontendImage string
@description('Existing Azure OpenAI / Foundry endpoint')
param openAiEndpoint string
param openAiDeployment string = 'gpt-4.1-mini'
param openAiDeploymentLarge string = ''
param speechRegion string = 'eastus'
param docIntelEndpoint string = ''
@secure()
param mongoAdminPassword string

var suffix = uniqueString(resourceGroup().id)

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs-${suffix}'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-ai-${suffix}'
  location: location
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-id-${suffix}'
  location: location
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${prefix}acr${suffix}'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefix}-kv-${suffix}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
  }
}

// Role assignments: AcrPull + Key Vault Secrets User for the app identity
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, 'acrpull')
  scope: acr
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, identity.id, 'kvsecrets')
  scope: kv
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// Primary database + vector search in one service
resource mongo 'Microsoft.DocumentDB/mongoClusters@2024-07-01' = {
  name: '${prefix}-mongo-${suffix}'
  location: location
  properties: {
    administrator: { userName: 'fiosadmin', password: mongoAdminPassword }
    serverVersion: '7.0'
    compute: { tier: 'M30' }
    storage: { sizeGb: 32 }
    sharding: { shardCount: 1 }
    highAvailability: { targetMode: 'Disabled' }
    publicNetworkAccess: 'Enabled'
  }
}

resource mongoFirewall 'Microsoft.DocumentDB/mongoClusters/firewallRules@2024-07-01' = {
  parent: mongo
  name: 'allow-azure-services'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// CAG hot context cache
resource redis 'Microsoft.Cache/redis@2024-03-01' = {
  name: '${prefix}-redis-${suffix}'
  location: location
  properties: { sku: { name: 'Standard', family: 'C', capacity: 1 }, enableNonSslPort: false, minimumTlsVersion: '1.2' }
}

// Realtime fan-out to millions of subscribers
resource pubsub 'Microsoft.SignalRService/webPubSub@2024-03-01' = {
  name: '${prefix}-wps-${suffix}'
  location: location
  sku: { name: 'Standard_S1', capacity: 1 }
  properties: {}
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
  }
}

var kvUri = kv.properties.vaultUri

resource backend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-api'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [ acrPull, kvSecretsUser ]
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      registries: [ { server: acr.properties.loginServer, identity: identity.id } ]
      secrets: [
        { name: 'openai-key', keyVaultUrl: '${kvUri}secrets/openai-key', identity: identity.id }
        { name: 'speech-key', keyVaultUrl: '${kvUri}secrets/speech-key', identity: identity.id }
        { name: 'docintel-key', keyVaultUrl: '${kvUri}secrets/docintel-key', identity: identity.id }
        { name: 'mongo-uri', keyVaultUrl: '${kvUri}secrets/mongo-uri', identity: identity.id }
        { name: 'redis-url', value: 'rediss://:${redis.listKeys().primaryKey}@${redis.properties.hostName}:6380/0' }
        { name: 'webpubsub', value: pubsub.listKeys().primaryConnectionString }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: backendImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiDeployment }
            { name: 'AZURE_OPENAI_DEPLOYMENT_LARGE', value: openAiDeploymentLarge }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'openai-key' }
            { name: 'AZURE_SPEECH_KEY', secretRef: 'speech-key' }
            { name: 'AZURE_SPEECH_REGION', value: speechRegion }
            { name: 'AZURE_DOC_INTEL_ENDPOINT', value: docIntelEndpoint }
            { name: 'AZURE_DOC_INTEL_KEY', secretRef: 'docintel-key' }
            { name: 'MONGODB_URI', secretRef: 'mongo-uri' }
            { name: 'VECTOR_BACKEND', value: 'cosmos' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'AZURE_WEB_PUBSUB_CONNECTION_STRING', secretRef: 'webpubsub' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'ENVIRONMENT', value: 'azure' }
          ]
          probes: [ { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30 } ]
        }
      ]
      // Stateless workers: scale on concurrent requests; event partitions keep per-match ordering.
      scale: {
        minReplicas: 1
        maxReplicas: 20
        rules: [ { name: 'http', http: { metadata: { concurrentRequests: '80' } } } ]
      }
    }
  }
}

resource frontend 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-web'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [ acrPull ]
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 80 }
      registries: [ { server: acr.properties.loginServer, identity: identity.id } ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: frontendImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [ { name: 'BACKEND_URL', value: 'https://${backend.properties.configuration.ingress.fqdn}' } ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 10 }
    }
  }
}

output webUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'
output apiUrl string = 'https://${backend.properties.configuration.ingress.fqdn}'
output keyVaultName string = kv.name
output acrName string = acr.name
output mongoHost string = mongo.properties.connectionString
