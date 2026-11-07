#!/bun/bash

$NUMBER="40000"
$IP="100.x.x.x"
cd scripts/
python remote_gamepad_forward.py --to $IP:$NUMBER -v
