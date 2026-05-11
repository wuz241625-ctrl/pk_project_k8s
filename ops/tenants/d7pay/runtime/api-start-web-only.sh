#!/usr/bin/env bash
set -euo pipefail

cd /app/api
mkdir -p /app/api/logs

nginx
python main.py --port=9000 --logfile=api.log > /app/api/logs/api.out.log 2>&1 &
API_PID=$!

for _ in $(seq 1 30); do
  if python - <<'PY'
import socket
s = socket.socket()
s.settimeout(1)
s.connect(("127.0.0.1", 9000))
s.close()
PY
  then
    break
  fi
  sleep 1
done

wait "${API_PID}"
