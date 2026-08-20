#!/usr/bin/env bash
set -euo pipefail

action="${1:-status}"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="$project_root/temp/run"
log_dir="$project_root/logs"

case "$action" in
  start|stop|restart|status) ;;
  *) echo "用法：$0 {start|stop|restart|status}" >&2; exit 2 ;;
esac

if ! command -v node >/dev/null 2>&1 && [ -s "$HOME/.nvm/nvm.sh" ]; then
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
fi

if [ -x "$project_root/.venv/bin/python" ]; then
  python_cmd="$project_root/.venv/bin/python"
else
  python_cmd="python3"
fi

listener_pid() {
  ss -ltnp "sport = :$1" 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -n 1
}

is_musicflow_process() {
  local name="$1" pid="$2" command_line
  [ -r "/proc/$pid/cmdline" ] || return 1
  command_line="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
  if [ "$name" = "backend" ]; then
    [[ "$command_line" == *"uvicorn"*"app.main:app"*"--port 8082"* ]]
  else
    [[ "$command_line" == *"vite"*"--port 3000"* ]]
  fi
}

port_for() {
  [ "$1" = "backend" ] && printf '8082' || printf '3000'
}

url_for() {
  [ "$1" = "backend" ] && printf 'http://127.0.0.1:8082/docs' || printf 'http://127.0.0.1:3000'
}

state_file_for() {
  printf '%s/%s.pid' "$runtime_dir" "$1"
}

wait_for_port() {
  local port="$1" expected="$2" attempts=120
  while [ "$attempts" -gt 0 ]; do
    if [ -n "$(listener_pid "$port")" ]; then listening=1; else listening=0; fi
    [ "$listening" = "$expected" ] && return 0
    sleep 0.25
    attempts=$((attempts - 1))
  done
  return 1
}

stop_pid() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 0
  kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.25
  done
  kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

start_service() {
  local name="$1" port pid
  port="$(port_for "$name")"
  pid="$(listener_pid "$port")"
  if [ -n "$pid" ]; then
    if is_musicflow_process "$name" "$pid"; then
      echo "$name 已在端口 $port 运行"
      return
    fi
    echo "端口 $port 被其他进程占用，拒绝启动 $name" >&2
    return 1
  fi

  mkdir -p "$runtime_dir" "$log_dir"
  if [ "$name" = "backend" ]; then
    setsid bash -c 'cd "$1" && exec "$2" -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload' \
      _ "$project_root/backend" "$python_cmd" \
      >"$log_dir/backend-dev.out.log" 2>"$log_dir/backend-dev.err.log" < /dev/null &
  else
    command -v node >/dev/null 2>&1 || { echo "未找到 Node.js；请运行 scripts/setup-wsl.sh 或检查 NVM 配置" >&2; return 1; }
    setsid bash -c 'cd "$1" && exec npm run dev -- --host 127.0.0.1 --port 3000' \
      _ "$project_root/frontend" \
      >"$log_dir/frontend-dev.out.log" 2>"$log_dir/frontend-dev.err.log" < /dev/null &
  fi
  pid=$!
  printf '%s\n' "$pid" > "$(state_file_for "$name")"
  if ! wait_for_port "$port" 1; then
    echo "$name 启动超时，请检查 $log_dir" >&2
    return 1
  fi
  echo "$name 已启动：http://127.0.0.1:$port"
}

stop_service() {
  local name="$1" port pid state_file
  port="$(port_for "$name")"
  state_file="$(state_file_for "$name")"
  if [ -f "$state_file" ]; then
    pid="$(<"$state_file")"
    if is_musicflow_process "$name" "$pid"; then stop_pid "$pid"; fi
    rm -f "$state_file"
  fi
  pid="$(listener_pid "$port")"
  if [ -n "$pid" ]; then
    if ! is_musicflow_process "$name" "$pid"; then
      echo "端口 $port 属于其他进程，拒绝停止" >&2
      return 1
    fi
    stop_pid "$pid"
  fi
  wait_for_port "$port" 0 || { echo "$name 未能在预期时间停止" >&2; return 1; }
  echo "$name 已停止"
}

show_status() {
  local name port pid url
  for name in backend frontend; do
    port="$(port_for "$name")"
    pid="$(listener_pid "$port")"
    if [ -z "$pid" ]; then echo "$name：已停止"; continue; fi
    if ! is_musicflow_process "$name" "$pid"; then echo "$name：端口 $port 被其他进程占用"; continue; fi
    url="$(url_for "$name")"
    if curl --fail --silent --max-time 5 "$url" >/dev/null; then
      echo "$name：运行中，HTTP 200，PID $pid"
    else
      echo "$name：正在监听但 HTTP 检查失败，PID $pid"
    fi
  done
}

case "$action" in
  start) start_service backend; start_service frontend; show_status ;;
  stop) stop_service frontend; stop_service backend; show_status ;;
  restart) stop_service frontend; stop_service backend; start_service backend; start_service frontend; show_status ;;
  status) show_status ;;
esac
