#!/usr/bin/env bash
set -euo pipefail

patterns=(
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----'
  'ghp_[A-Za-z0-9_]{20,}'
  'github_pat_[A-Za-z0-9_]{20,}'
  'sk-[A-Za-z0-9]{20,}'
  'xox[baprs]-[A-Za-z0-9-]{10,}'
  'AIza[0-9A-Za-z_-]{20,}'
)

status=0
for pattern in "${patterns[@]}"; do
  if rg --hidden --glob '!.git/' --glob '!node_modules/' --glob '!dist/' --glob '!build/' -n -- "$pattern" .; then
    status=1
  fi
done

exit "$status"
