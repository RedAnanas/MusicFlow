#!/bin/sh
set -eu

uvicorn app.main:app --host 127.0.0.1 --port 8082 &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true; wait "$backend_pid" 2>/dev/null || true' INT TERM EXIT
nginx -g 'daemon off;'
