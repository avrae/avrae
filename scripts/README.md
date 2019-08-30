# Scripts
These scripts are used in the deploy process.

### deploy.sh
Usage: `bash scripts/deploy.sh [production|nightly]`   
Top level script that runs the deploy process.  
TODO accepts an argument, "production" or "nightly"

### ecr_push.sh
Usage: `bash scripts/ecr_push.sh [production|nightly]`  
Pushes a built docker image to ECR and updates the ECS service to use it.  
TODO accepts an argument, "production" or "nightly"

### gen_command_json.py
Usage: `python gen_command_json.py [-o outfile] test`  
Generates the helpdocs JSON.

### gen_help.sh
Usage: `bash scripts/gen_help.sh`  
Runs gen_command_json.py, but better. (workaround for python module nonsense)

### upload_help.sh
Usage: `bash scripts/upload_help.sh`  
Uploads a generated helpdocs JSON to S3.