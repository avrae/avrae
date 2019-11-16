#!/bin/bash
# Usage: bash scripts/deploy.sh [production|nightly]
environment=${1:-production}

bash scripts/sentry_release.sh "$environment"
if [[ "$environment" = "production" ]]; then
    bash scripts/upload_help.sh
fi;
bash scripts/ecr_push.sh "$environment"
