#!/bin/zsh
set -e
cd "$(dirname "$0")"
uv_bin="$(command -v uv || true)"
if [[ -z "$uv_bin" && -x "$HOME/.local/bin/uv" ]]; then
  uv_bin="$HOME/.local/bin/uv"
fi
if [[ -z "$uv_bin" ]]; then
  echo '请先安装 uv，见 README。'
  exit 1
fi
"$uv_bin" sync --locked
"$uv_bin" run uvicorn nl2sql.api:app --host 127.0.0.1 --port 8000 &
api_process=$!
trap 'kill "$api_process" 2>/dev/null || true' EXIT INT TERM
"$uv_bin" run streamlit run src/nl2sql/demo.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
