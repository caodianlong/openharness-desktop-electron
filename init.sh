#!/bin/bash
set -e

echo "=== OpenHarness Desktop Electron Init ==="

cd "$(dirname "$0")"

# 1. 确保 venv 存在
if [ ! -d "apps/host-python/.venv" ]; then
  echo "Creating venv..."
  python3 -m venv apps/host-python/.venv
  apps/host-python/.venv/bin/pip install -q -U pip
fi
echo "✅ venv ready"

# 2. 安装依赖
apps/host-python/.venv/bin/pip install -q -r apps/host-python/requirements.txt
echo "✅ dependencies installed"

# 3. 创建数据目录
mkdir -p ~/.openharness
mkdir -p ~/.openharness/sessions
echo "✅ data directories ready"

# 4. 杀掉残留进程
pkill -9 -f uvicorn 2>/dev/null || true
pkill -f "http.server 8091" 2>/dev/null || true
sleep 1

# 5. 启动后端（nohup 方式）
cd apps/host-python
export PYTHONPATH=src
env PYTHONPATH=src nohup .venv/bin/python3 -m uvicorn host_mvp.ws_server:app \
  --host 0.0.0.0 --port 8789 --log-level info > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo "✅ Backend PID=$BACKEND_PID"

# 6. 等待就绪
for i in $(seq 1 15); do
  if curl -s http://127.0.0.1:8789/api/health | grep -q "openharness"; then
    echo "✅ Backend is ready"
    echo "🌐 Frontend: http://127.0.0.1:8789/"
    echo "🔧 API Health: http://127.0.0.1:8789/api/health"
    echo "=== INIT COMPLETE ==="
    exit 0
  fi
  sleep 1
done

echo "❌ Backend failed to start within 15s"
tail -20 /tmp/backend.log
exit 1
