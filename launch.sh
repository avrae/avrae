#!/bin/bash
# launch.sh
# launch discord bots

_term() { 
    echo "Caught SIGTERM signal!"
}

echo "Launching web"
python3 webLauncher.py &

trap _term SIGTERM

python3 beAnnoying.py $2 # don't fall asleep