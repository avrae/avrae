#!/bin/bash
# launch.sh
# launch discord bots

_term() { 
    echo "l.0: Caught SIGTERM signal!"
}

echo "l.0: Launching web"
python3 webLauncher.py &

trap _term SIGTERM

python3 beAnnoying.py $2 # don't fall asleep