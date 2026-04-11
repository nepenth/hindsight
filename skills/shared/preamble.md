## Preamble (run first)

```bash
# Hindsight skill preamble - detect environment and existing config
_HS_VERSION="0.1.0"
_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
_PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || basename "$(pwd)")

# Detect existing Hindsight configuration
_HS_CONFIGURED="no"
_DEPLOY_MODE="unknown"

# 1. Project-level signals first (most specific)
# Check project .env for Hindsight cloud URL
if [ -f .env ] && grep -q "api.hindsight.vectorize.io" .env 2>/dev/null; then
  _HS_CONFIGURED="yes"
  _DEPLOY_MODE="cloud"
elif [ -f .env ] && grep -q "HINDSIGHT_API_URL" .env 2>/dev/null; then
  _HS_CONFIGURED="yes"
  _DEPLOY_MODE="self-hosted"
fi

# Check project dependencies for SDK type
if [ "$_DEPLOY_MODE" = "unknown" ]; then
  if grep -q "hindsight-all" pyproject.toml requirements*.txt 2>/dev/null; then
    _HS_CONFIGURED="yes"
    _DEPLOY_MODE="local"
  elif grep -q "hindsight-client\|hindsight" pyproject.toml requirements*.txt package.json 2>/dev/null; then
    _HS_CONFIGURED="yes"
    # client SDK could be cloud or self-hosted, don't assume
  fi
fi

# 2. Global CLI config (less specific than project)
if [ "$_DEPLOY_MODE" = "unknown" ] && [ -f ~/.hindsight/config ]; then
  _HS_CONFIGURED="yes"
  if grep -q "api.hindsight.vectorize.io" ~/.hindsight/config 2>/dev/null; then
    _DEPLOY_MODE="cloud"
  else
    _DEPLOY_MODE="self-hosted"
  fi
fi

# 3. Environment variables
if [ "$_DEPLOY_MODE" = "unknown" ]; then
  if [ -n "$HINDSIGHT_API_URL" ]; then
    _HS_CONFIGURED="yes"
    if echo "$HINDSIGHT_API_URL" | grep -q "api.hindsight.vectorize.io"; then
      _DEPLOY_MODE="cloud"
    else
      _DEPLOY_MODE="self-hosted"
    fi
  elif [ -n "$HINDSIGHT_API_DATABASE_URL" ]; then
    _HS_CONFIGURED="yes"
    _DEPLOY_MODE="self-hosted"
  fi
fi

# 4. Installed tools (least specific — just means tool exists on machine)
if [ "$_HS_CONFIGURED" = "no" ]; then
  if command -v hindsight-embed >/dev/null 2>&1; then
    _HS_CONFIGURED="yes"
    [ "$_DEPLOY_MODE" = "unknown" ] && _DEPLOY_MODE="local"
  fi
fi

# Detect existing Hindsight usage in current project
_HAS_EXISTING="no"
if grep -rl "hindsight" --include="*.py" --include="*.ts" --include="*.js" --include="*.json" . 2>/dev/null | head -1 | grep -q .; then
  _HAS_EXISTING="yes"
fi

# Detect project language / framework for SDK selection
_LANGUAGE="unknown"
_FRAMEWORK="unknown"
_HAS_NODE="no"
_HAS_PYTHON="no"

if [ -f package.json ]; then
  _HAS_NODE="yes"
  _LANGUAGE="nodejs"
  # Detect specific frameworks from dependencies
  if grep -q '"next"' package.json 2>/dev/null; then
    _FRAMEWORK="next.js"
  elif grep -q '"react"' package.json 2>/dev/null; then
    _FRAMEWORK="react"
  elif grep -q '"express"' package.json 2>/dev/null; then
    _FRAMEWORK="express"
  elif grep -q '"fastify"' package.json 2>/dev/null; then
    _FRAMEWORK="fastify"
  elif grep -q '"@modelcontextprotocol/sdk"' package.json 2>/dev/null; then
    _FRAMEWORK="mcp"
  fi
fi

if [ -f pyproject.toml ] || [ -f requirements.txt ] || [ -f setup.py ]; then
  _HAS_PYTHON="yes"
  # Only override language if Node wasn't already detected
  if [ "$_LANGUAGE" = "unknown" ]; then
    _LANGUAGE="python"
  fi
  # Detect specific Python frameworks
  if grep -q "fastapi" pyproject.toml requirements*.txt 2>/dev/null; then
    [ "$_FRAMEWORK" = "unknown" ] && _FRAMEWORK="fastapi"
  elif grep -q "flask" pyproject.toml requirements*.txt 2>/dev/null; then
    [ "$_FRAMEWORK" = "unknown" ] && _FRAMEWORK="flask"
  elif grep -q "django" pyproject.toml requirements*.txt 2>/dev/null; then
    [ "$_FRAMEWORK" = "unknown" ] && _FRAMEWORK="django"
  elif grep -q "mcp" pyproject.toml requirements*.txt 2>/dev/null; then
    [ "$_FRAMEWORK" = "unknown" ] && _FRAMEWORK="mcp"
  fi
fi

# Mixed-language project → python takes precedence only if it looks like the primary (has main module)
if [ "$_HAS_NODE" = "yes" ] && [ "$_HAS_PYTHON" = "yes" ]; then
  _LANGUAGE="mixed"
fi

# Infer recommended integration method
_INTEGRATION="unknown"
case "$_LANGUAGE" in
  nodejs) _INTEGRATION="nodejs-sdk" ;;
  python) _INTEGRATION="python-sdk" ;;
  mixed) _INTEGRATION="ask" ;;
esac

# If framework is MCP, override
if [ "$_FRAMEWORK" = "mcp" ]; then
  _INTEGRATION="mcp"
fi

echo "HINDSIGHT_SKILL_VERSION: $_HS_VERSION"
echo "BRANCH: $_BRANCH"
echo "PROJECT: $_PROJECT"
echo "HINDSIGHT_CONFIGURED: $_HS_CONFIGURED"
echo "DEPLOY_MODE: $_DEPLOY_MODE"
echo "HAS_EXISTING_SETUP: $_HAS_EXISTING"
echo "LANGUAGE: $_LANGUAGE"
echo "FRAMEWORK: $_FRAMEWORK"
echo "INTEGRATION: $_INTEGRATION"
```
