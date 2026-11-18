#!/bin/bash
# 启动/重启后端 API（端口 8000）。密钥等配置从仓库根目录 .env 读取，外网代理沿用新闻采集 cron 的配置。
#   bash scripts/start_api.sh          # 重启
#   tail -f /tmp/jobnav_api.log        # 查看日志
cd "$(dirname "$0")/.." || exit 1
set -a
[ -f .env ] && . ./.env
[ -f /etc/cron.d/jobnav-news ] && eval "$(grep -E '^(https?_proxy|HTTPS?_PROXY)=' /etc/cron.d/jobnav-news)"
JOBNAV_PATH_PLANNER=${JOBNAV_PATH_PLANNER:-v4}
JOBNAV_RANKER=${JOBNAV_RANKER:-ltr}
HF_HOME=${HF_HOME:-/var/lib/hf}
no_proxy=${no_proxy:-localhost,127.0.0.1,10.0.0.0/8,100.0.0.0/8,.pjlab.org.cn}
set +a
PY=${JOBNAV_PYTHON:-/var/lib/jobnav-env/bin/python}
pkill -f "uvicorn app.main:app" && sleep 2
nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/jobnav_api.log 2>&1 &
for i in $(seq 1 60); do
  sleep 2
  curl -s -m 2 http://127.0.0.1:8000/v1/health >/dev/null && { echo "API 已启动 (pid $!)"; exit 0; }
done
echo "API 启动超时，见 /tmp/jobnav_api.log"; tail -20 /tmp/jobnav_api.log; exit 1
