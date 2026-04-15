#!/usr/bin/env bash
# =============================================================================
# azure/deploy.sh — Deploy Balu LLM API to Azure Container Apps
#
# What this script does:
#   1. Verifies the Azure CLI is installed and authenticated.
#   2. Creates a resource group (if it doesn't exist).
#   3. Creates an Azure Container Registry (if it doesn't exist).
#   4. Builds the Docker image and pushes it to the ACR.
#   5. Deploys the Bicep template (Container App + Environment + Log Analytics).
#   6. Prints the public URL of the deployed application.
#
# Prerequisites:
#   - Azure CLI (az) installed and in PATH
#   - Docker installed and running
#   - Logged in to Azure: az login
#   - Sufficient RBAC permissions on the target subscription
#
# Usage:
#   bash azure/deploy.sh [options]
#
# Options (all have defaults — override with environment variables or flags):
#   --resource-group  / -g   Azure resource group name   (default: balu-llm-rg)
#   --location        / -l   Azure region                (default: eastus)
#   --app-name        / -n   Container App name          (default: balu-llm)
#   --acr-name        / -r   ACR name (globally unique)  (default: balullmacr)
#   --image-tag       / -t   Docker image tag            (default: latest)
#   --api-key         / -k   API_KEY secret              (required)
#   --llm-backend            "ollama" or "azure_openai"  (default: ollama)
#   --ollama-url             Ollama URL                  (default: http://localhost:11434)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${CYAN}======================================================${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}======================================================${NC}"; }
die()   { error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Default configuration (override via environment or flags below)
# ---------------------------------------------------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-balu-llm-rg}"
LOCATION="${LOCATION:-eastus}"
APP_NAME="${APP_NAME:-balu-llm}"
ACR_NAME="${ACR_NAME:-balullmacr}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
API_KEY="${API_KEY:-}"
LLM_BACKEND="${LLM_BACKEND:-ollama}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"

# Azure OpenAI (only needed when LLM_BACKEND=azure_openai)
AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-}"
AZURE_OPENAI_KEY="${AZURE_OPENAI_KEY:-}"
AZURE_OPENAI_DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-gpt-4o}"

# Script location (so we can find the Bicep template)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BICEP_FILE="${SCRIPT_DIR}/container-app.bicep"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        -g|--resource-group)  RESOURCE_GROUP="$2"; shift 2 ;;
        -l|--location)        LOCATION="$2";        shift 2 ;;
        -n|--app-name)        APP_NAME="$2";        shift 2 ;;
        -r|--acr-name)        ACR_NAME="$2";        shift 2 ;;
        -t|--image-tag)       IMAGE_TAG="$2";       shift 2 ;;
        -k|--api-key)         API_KEY="$2";         shift 2 ;;
        --llm-backend)        LLM_BACKEND="$2";     shift 2 ;;
        --ollama-url)         OLLAMA_URL="$2";      shift 2 ;;
        -h|--help)
            grep '^#' "$0" | head -40 | sed 's/^# \?//'
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
step "Validating prerequisites"

command -v az     &>/dev/null || die "Azure CLI (az) is not installed. Install from https://aka.ms/install-azure-cli"
command -v docker &>/dev/null || die "Docker is not installed or not running."

[[ -f "${BICEP_FILE}" ]] || die "Bicep template not found at ${BICEP_FILE}"

if [[ -z "${API_KEY}" ]]; then
    die "API_KEY is required. Pass it with --api-key or set the API_KEY environment variable."
fi

# ---------------------------------------------------------------------------
# Azure login check
# ---------------------------------------------------------------------------
step "Checking Azure authentication"

if ! az account show &>/dev/null; then
    info "Not logged in — running az login …"
    az login
fi

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
SUBSCRIPTION_NAME="$(az account show --query name -o tsv)"
info "Using subscription: ${SUBSCRIPTION_NAME} (${SUBSCRIPTION_ID})"

# ---------------------------------------------------------------------------
# Resource group
# ---------------------------------------------------------------------------
step "Creating resource group '${RESOURCE_GROUP}' in '${LOCATION}'"

az group create \
    --name "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --output none

info "Resource group ready."

# ---------------------------------------------------------------------------
# Azure Container Registry
# ---------------------------------------------------------------------------
step "Creating / verifying ACR '${ACR_NAME}'"

if ! az acr show --name "${ACR_NAME}" --resource-group "${RESOURCE_GROUP}" &>/dev/null; then
    info "ACR '${ACR_NAME}' not found — creating …"
    az acr create \
        --name "${ACR_NAME}" \
        --resource-group "${RESOURCE_GROUP}" \
        --sku Basic \
        --admin-enabled true \
        --output none
    info "ACR created."
else
    info "ACR '${ACR_NAME}' already exists."
fi

ACR_LOGIN_SERVER="$(az acr show --name "${ACR_NAME}" --query loginServer -o tsv)"
IMAGE_NAME="${ACR_LOGIN_SERVER}/${APP_NAME}:${IMAGE_TAG}"
info "Image will be pushed to: ${IMAGE_NAME}"

# ---------------------------------------------------------------------------
# Build and push Docker image
# ---------------------------------------------------------------------------
step "Building Docker image"

# Resolve the project root (one level up from azure/)
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

docker build \
    --file "${PROJECT_ROOT}/Dockerfile" \
    --tag "${IMAGE_NAME}" \
    --target runtime \
    "${PROJECT_ROOT}"

info "Build complete."

step "Pushing image to ACR"

az acr login --name "${ACR_NAME}"
docker push "${IMAGE_NAME}"

info "Push complete."

# ---------------------------------------------------------------------------
# Deploy Bicep template
# ---------------------------------------------------------------------------
step "Deploying Bicep template"

DEPLOYMENT_NAME="${APP_NAME}-deploy-$(date +%Y%m%d%H%M%S)"

BICEP_PARAMS=(
    "appName=${APP_NAME}"
    "imageName=${IMAGE_NAME}"
    "apiKey=${API_KEY}"
    "llmBackend=${LLM_BACKEND}"
    "ollamaUrl=${OLLAMA_URL}"
    "location=${LOCATION}"
)

if [[ "${LLM_BACKEND}" == "azure_openai" ]]; then
    [[ -z "${AZURE_OPENAI_ENDPOINT}" ]] && die "AZURE_OPENAI_ENDPOINT is required when LLM_BACKEND=azure_openai"
    [[ -z "${AZURE_OPENAI_KEY}" ]]      && die "AZURE_OPENAI_KEY is required when LLM_BACKEND=azure_openai"
    BICEP_PARAMS+=(
        "azureOpenAiEndpoint=${AZURE_OPENAI_ENDPOINT}"
        "azureOpenAiKey=${AZURE_OPENAI_KEY}"
        "azureOpenAiDeployment=${AZURE_OPENAI_DEPLOYMENT}"
    )
fi

DEPLOYMENT_OUTPUT="$(az deployment group create \
    --name "${DEPLOYMENT_NAME}" \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${BICEP_FILE}" \
    --parameters "${BICEP_PARAMS[@]}" \
    --query 'properties.outputs' \
    --output json)"

info "Deployment complete."

# ---------------------------------------------------------------------------
# Extract and display the app URL
# ---------------------------------------------------------------------------
APP_URL="$(echo "${DEPLOYMENT_OUTPUT}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('appUrl',{}).get('value','<unknown>'))")"

step "Deployment Summary"
echo ""
echo -e "  ${GREEN}App URL      :${NC} ${APP_URL}"
echo -e "  ${GREEN}Health check :${NC} ${APP_URL}/health"
echo -e "  ${GREEN}API docs     :${NC} ${APP_URL}/docs"
echo -e "  ${GREEN}Resource group:${NC} ${RESOURCE_GROUP}"
echo -e "  ${GREEN}Image        :${NC} ${IMAGE_NAME}"
echo ""
info "Deployment complete! Test with:"
echo "  curl -H 'X-API-Key: \${API_KEY}' ${APP_URL}/health"
echo ""
