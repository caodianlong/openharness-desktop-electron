# 后端 MVP 验证记录

## 目标
验证以下关键链路是否成立：

1. 在桌面项目中将 OpenHarness 作为 **Python 库** 导入，而不是调用 CLI
2. 封装一层对前端友好的协议
3. 提供最小可工作的 Host MVP
4. 跑通自动化测试

## 结果
已完成。

## 实现位置
- `apps/host-python/src/host_mvp/adapter.py`
- `apps/host-python/src/host_mvp/server.py`
- `apps/host-python/tests/test_mvp.py`

## 当前能力
### OpenHarness 库导入
- 通过 `vendor/OpenHarness/src` 注入 `sys.path`
- 成功 `import openharness`
- 当前已验证库可被 Host 进程直接加载

### DeepSeek 环境变量映射
- 检测系统环境变量：`DEEPSEEK_BASE_URL`、`DEEPSEEK_API_KEY`
- 不直接读取或输出变量值到文档/日志
- 在 Host 启动阶段映射为 OpenHarness 可识别的配置语义：
  - `OPENHARNESS_API_FORMAT=openai`
  - `OPENHARNESS_BASE_URL <- DEEPSEEK_BASE_URL`
  - `OPENAI_API_KEY <- DEEPSEEK_API_KEY`
- `/health` 中只展示“使用了哪些环境变量名”和映射状态，不暴露具体值

### 对前端友好的协议
已实现：
- `GET /health`
- `GET /version`
- `GET /protocol/version`
- `WS /ws`

### WebSocket 事件
- 启动后发送 `host.ready`
- 支持 `ping -> host.pong`
- 未识别消息走 `host.echo`

## 测试结果
已通过：
- health endpoint
- protocol version endpoint
- websocket bootstrap + ping

## 当前限制
这个 MVP 只验证“库导入 + Host 协议 + 基础测试”三件事，还没有接入真正的 OpenHarness 会话执行/任务流。

## 下一步建议
1. 增加 `POST /conversations` 和 `POST /runs` 的假实现壳
2. 把 OpenHarness 的实际交互能力映射为结构化事件流
3. 定义 conversation/run/task/event 的正式 schema
4. 增加前端 demo 页面验证协议消费
