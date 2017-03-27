#!/bin/sh
# launch.sh
# launch discord bots

echo "Launching web"
python3 webLauncher.py &

for ((i=0; i<${SHARDS}; i++))
do
    echo "Launching shard $1 $i with command python3 dbot.py -s $i $1"
    python3 dbot.py -s $i $1 &
    sleep 10
done