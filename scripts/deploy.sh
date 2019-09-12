#!/bin/bash
# Usage: bash scripts/deploy.sh [production|nightly]
environment=${1:-production}

if [[ "$environment" = "production" ]]; then
    bash scripts/upload_help.sh
fi;
bash scripts/ecr_push.sh "$environment"
