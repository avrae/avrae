#!/bin/bash
.local/bin/pytest --cov=cogs5e --cov=cogsmisc --cov=utils tests/ $DBOT_ARGS
cp .coverage /shared/.coverage
