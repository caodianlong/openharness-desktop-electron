# host-python MVP

这是一个最小后端验证：

- 以库方式尝试导入 `vendor/OpenHarness/src/openharness`
- 使用环境变量把 DeepSeek（OpenAI-compatible）映射到 OpenHarness 配置语义
- 暴露对前端友好的 HTTP / WebSocket 协议
- 提供 `/health`、`/version`、`/protocol/version`、`/ws`
- 通过 pytest 做最小验证

## 本地运行

```bash
cd apps/host-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL}
export DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
PYTHONPATH=src uvicorn host_mvp.server:app --reload --port 8787
```

## 测试

```bash
cd apps/host-python
source .venv/bin/activate
PYTHONPATH=src pytest -q
```
