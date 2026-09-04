#!/usr/bin/env sh
# Emit a SECRET_KEY line for .env:  ./scripts/generate-secret.sh >> .env
set -eu
printf 'SECRET_KEY=%s\n' "$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
