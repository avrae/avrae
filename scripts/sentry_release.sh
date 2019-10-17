#!/bin/bash
# Usage: bash scripts/sentry_release.sh [environment]
# sentry auth env vars should be set in travis.
ENVIRONMENT=${1:-production}
VERSION=$(sentry-cli releases propose-version)

# Create a release
sentry-cli releases new -p avrae-bot $VERSION

# Associate commits with the release
sentry-cli releases set-commits --auto $VERSION

# deploy the release
sentry-cli releases deploys $VERSION new -e $ENVIRONMENT
