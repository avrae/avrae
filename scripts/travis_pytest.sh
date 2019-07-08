#!/bin/bash
pytest --cov=cogs5e --cov=cogsmisc --cov=utils tests/ $DBOT_ARGS
mv .coverage shared/.coverage
