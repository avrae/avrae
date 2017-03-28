#!/bin/bash
# launch.sh
# launch discord bots

_term() { 
    echo "Caught SIGTERM signal!"
}

echo "Launching web"
python3 webLauncher.py &

for ((i=0; i<$1; i++))
do
    echo "Launching shard $2 $i with command python3 dbot.py -s $i $2"
    python3 dbot.py -s $i $2 &
    sleep 10
done

trap _term SIGTERM

python3 beAnnoying.py $2 # don't fall asleep