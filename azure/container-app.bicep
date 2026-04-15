// =============================================================================
// Balu LLM API — Azure Container App Bicep Template
//
// Deploys:
//   - Log Analytics Workspace
//   - Container App Environment
//   - Azure Container App (external ingress, port 8000)
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file azure/container-app.bicep \
//     --parameters appName=balu-llm apiKey=<secret> imageName=<acr>.azurecr.io/balu-llm-api:latest
// =============================================================================

@description('Azure region for all resources (defaults to the resource group location).')
param location string = resourceGroup().location

@description('Base name used for all resource names.')
param appName string = 'balu-llm'

@description('Full image name including registry and tag, e.g. myacr.azurecr.io/balu-llm-api:latest')
param imageName string

@description('Secret API key to protect the /v1/chat endpoint.')
@secure()
param apiKey string

@description('Ollama server URL (only used when llmBackend=ollama).')
param ollamaUrl string = 'http://localhost:11434'

@description('LLM backend: "ollama" or "azure_openai".')
@allowed(['ollama', 'azure_openai'])
param llmBackend string = 'ollama'

@description('Ollama model name.')
param ollamaModel string = 'orca-mini'

@description('Azure OpenAI endpoint (only used when llmBackend=azure_openai).')
param azureOpenAiEndpoint string = ''

@description('Azure OpenAI API key (only used when llmBackend=azure_openai).')
@secure()
param azureOpenAiKey string = ''

@description('Azure OpenAI deployment name.')
param azureOpenAiDeployment string = 'gpt-4o'

@description('Maximum number of replicas.')
param maxReplicas int = 5

@description('Minimum number of replicas (0 = scale to zero).')
param minReplicas int = 0

@description('Number of CPU cores per replica.')
param cpuCores string = '0.5'

@description('Memory per replica in Gi.')
param memoryGi string = '1.0Gi'

// ---------------------------------------------------------------------------
// Log Analytics Workspace
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// ---------------------------------------------------------------------------
// Container App Environment
// ---------------------------------------------------------------------------
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${appName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Container App
// ---------------------------------------------------------------------------
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'OPTIONS']
          allowedHeaders: ['*']
          allowCredentials: false
        }
      }
      secrets: [
        {
          name: 'api-key'
          value: apiKey
        }
        {
          name: 'azure-openai-key'
          value: azureOpenAiKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'llm-api'
          image: imageName
          resources: {
            cpu: json(cpuCores)
            memory: memoryGi
          }
          env: [
            {
              name: 'LLM_BACKEND'
              value: llmBackend
            }
            {
              name: 'OLLAMA_BASE_URL'
              value: ollamaUrl
            }
            {
              name: 'OLLAMA_MODEL'
              value: ollamaModel
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAiEndpoint
            }
            {
              name: 'AZURE_OPENAI_KEY'
              secretRef: 'azure-openai-key'
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: azureOpenAiDeployment
            }
            {
              name: 'API_KEY'
              secretRef: 'api-key'
            }
            {
              name: 'MAX_TOKENS'
              value: '1024'
            }
            {
              name: 'TEMPERATURE'
              value: '0.7'
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
            {
              name: 'CORS_ORIGINS'
              value: '["*"]'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 30
              timeoutSeconds: 10
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 15
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale-rule'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
@description('The public FQDN of the Container App.')
output appUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'

@description('The resource ID of the Container App.')
output containerAppId string = containerApp.id

@description('The resource ID of the Container App Environment.')
output environmentId string = containerAppEnvironment.id

@description('The Log Analytics Workspace ID.')
output logAnalyticsWorkspaceId string = logAnalytics.id
