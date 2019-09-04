#!/bin/bash
# Usage: bash scripts/deploy.sh [production|nightly]
environment=${1:-production}

bash scripts/upload_help.sh
bash scripts/ecr_push.sh "$environment"
