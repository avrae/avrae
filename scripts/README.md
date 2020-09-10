# Scripts
These scripts are used in the deploy process.

### deploy.sh
Usage: `bash scripts/deploy.sh [production|nightly]`   
Top level script that runs the deploy process.  

### ecr_push.sh
Usage: `bash scripts/ecr_push.sh [production|nightly]`  
Pushes a built docker image to ECR and updates the ECS service to use it.  

### gen_command_json.py
Usage: `python gen_command_json.py [-o outfile] test`  
Generates the helpdocs JSON.

### gen_help.sh
Usage: `bash scripts/gen_help.sh`  
Runs gen_command_json.py, but better. (workaround for python module nonsense)

### upload_help.sh
Usage: `bash scripts/upload_help.sh`  
Uploads a generated helpdocs JSON to S3.

### sentry_release.sh
Usage: `bash scripts/sentry_release.sh [environment]`  
Must be run in a Git repo. Sets up a new Sentry release.  
Requires the `SENTRY_AUTH_TOKEN` and `SENTRY_ORG` env vars (set in Travis).

### ensure_indices.py
Usage: `python ensure_indices.py`
Creates all the necessary database indices. 
Requires the `MONGO_URL` and `MONGO_DB` env vars.
