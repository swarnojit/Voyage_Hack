#!/usr/bin/env bash
# Explicit opt-in publisher for the fully synthetic TripParadox source. Never runs automatically.
set -euo pipefail
REPO="${1:-TripParadox-Security-Lab}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if ! command -v git >/dev/null 2>&1 || ! command -v gh >/dev/null 2>&1; then
  echo 'ERROR: Install git and GitHub CLI (gh) before publication.' >&2; exit 1
fi
gh auth status >/dev/null || { echo 'ERROR: Run gh auth login first.' >&2; exit 1; }
case "$REPO" in *[!a-zA-Z0-9_-]*|'') echo 'ERROR: Repo name may only contain letters, digits, underscore and hyphen.' >&2; exit 1;; esac
if [ ! -f README.md ] || [ ! -f .gitignore ] || [ ! -f docs/COMPREHENSIVE_SECURITY_TECHNICAL_REPORT.md ]; then
  echo 'ERROR: Run this script from the full verified project package.' >&2; exit 1
fi
if [ ! -d .git ]; then git init -b main; fi
for forbidden in '.env' 'backend/tripparadox.db' 'backend/.env' 'backup.sql'; do
  if [ -e "$forbidden" ] && ! git check-ignore -q "$forbidden"; then
    echo "ERROR: Sensitive local path is not Git ignored: $forbidden" >&2; exit 1
  fi
done
printf '\nThis repository includes intentionally vulnerable demo code that must be used ONLY on localhost.\n'
printf 'You are about to publish the SOURCE CODE publicly; no running service is deployed.\n'
read -r -p 'Type PUBLIC to proceed: ' ack
if [ "$ack" != 'PUBLIC' ]; then echo 'Cancelled.'; exit 1; fi
git add -A
if git diff --cached --name-only | grep -Ei '(^|/)(\.env|.*\.db|.*\.sqlite|.*\.pem|.*\.p12|.*\.key|.*\.bak|.*\.backup|.*\.log)$' ; then
 echo 'ERROR: Sensitive file extension found among staged files. Review and retry.' >&2; exit 1
fi
if ! git diff --cached --quiet; then git commit -m 'Publish TripParadox security research prototype and technical report'; fi
if git remote get-url origin >/dev/null 2>&1; then
 echo 'ERROR: A Git origin already exists. Review manually; refusing to overwrite or push automatically.' >&2; exit 1
fi
gh repo create "$REPO" --public --source . --remote origin --push
URL="$(gh repo view --json url,visibility --jq 'select(.visibility == "PUBLIC") | .url')"
if [ -z "$URL" ]; then echo 'ERROR: Could not verify public visibility.' >&2; exit 1; fi
printf '\nPUBLIC REPOSITORY CREATED AND VERIFIED: %s\n' "$URL"
printf 'Verify the URL in a logged-out browser before sharing.\n'
