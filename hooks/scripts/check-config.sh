#!/bin/bash
set -euo pipefail

# Check if last24hours has any configuration source available.
# Priority: .claude/last24hours.env > ~/.config/last24hours/.env > env vars

PROJECT_ENV=".claude/last24hours.env"
GLOBAL_ENV="$HOME/.config/last24hours/.env"

# Helper: warn if file permissions are too open
check_perms() {
  local file="$1"
  if [[ ! -f "$file" ]]; then return; fi
  local perms
  perms=$(stat -f '%Lp' "$file" 2>/dev/null || stat -c '%a' "$file" 2>/dev/null || echo "")
  if [[ -n "$perms" && "$perms" != "600" && "$perms" != "400" ]]; then
    echo "/last24hours: WARNING — $file has permissions $perms (should be 600)."
    echo "  Fix: chmod 600 $file"
  fi
}

# Check per-project config
if [[ -f "$PROJECT_ENV" ]]; then
  check_perms "$PROJECT_ENV"
  exit 0
fi

# Check global config
if [[ -f "$GLOBAL_ENV" ]]; then
  check_perms "$GLOBAL_ENV"
  exit 0
fi

# Check if OPENAI_API_KEY is set in environment (minimum requirement)
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  exit 0
fi

# Check if SCRAPECREATORS_API_KEY is set (also sufficient)
if [[ -n "${SCRAPECREATORS_API_KEY:-}" ]]; then
  exit 0
fi

# No config found — inform user
cat <<'EOF'
/last24hours: No API keys configured.

Create .claude/last24hours.env with your API keys, or create
~/.config/last24hours/.env globally. At minimum, SCRAPECREATORS_API_KEY
or OPENAI_API_KEY is required. See the README for setup instructions.
EOF
