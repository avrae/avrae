# Scripts
These scripts are used in the deploy process.

### gen_command_json.py
Usage: `python gen_command_json.py [-o outfile] test`  
Generates the helpdocs JSON.

### ensure_indices.py
Usage: `python ensure_indices.py`
Creates all the necessary database indices. 
Requires the `MONGO_URL` and `MONGO_DB` env vars.
