#!/bin/bash
.local/bin/pytest --cov=cogs5e --cov=cogsmisc --cov=utils tests/ $DBOT_ARGS
bash <(curl -s https://codecov.io/bash)
