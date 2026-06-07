#!/usr/bin/env bash
set -euo pipefail

fail=0

echo "checking for common secret patterns"
if ./scripts/check-secrets.sh; then
  echo "secret pattern check: ok"
else
  echo "secret pattern check: review findings above"
  fail=1
fi

echo "checking for local-only paths and private state markers"
if rg --hidden --glob '!.git/' --glob '!node_modules/' --glob '!dist/' --glob '!build/' -n \
  --glob '!scripts/verify-public-safety.sh' \
  --glob '!src/oss_maintainer_toolkit/checks.py' \
  --glob '!tests/test_checks.py' \
  --glob '!.gitignore' \
  '/Users/|/home/|/opt/|/var/lib/|id_ed25519|codex-home-backup|state_[0-9]+\.sqlite|logs_[0-9]+\.sqlite|session_index\.jsonl|\.codex' .; then
  echo "local/private marker check: review findings above"
  fail=1
else
  echo "local/private marker check: ok"
fi

echo "checking git status"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
current_root="$(pwd)"
if [[ "$repo_root" == "$current_root" ]]; then
  git status --short
elif [[ -n "$repo_root" ]]; then
  echo "git status: skipped because this scaffold is inside another git worktree"
  echo "initialize a new public repository at this directory before publishing"
else
  echo "git status: skipped because this directory is not a git repository"
fi

exit "$fail"
