## 任务：重写 OpenHarness Desktop 前端 UI

### 背景
我们正在为 OpenHarness（AI 通用办公协作助手）开发桌面 GUI 外壳。对标产品是 Claude Cowork，不是 Claude Desktop。当前已完成 16/16 功能点的后端开发，但前端 UI 是粗糙的 MVP 版本。现在需要按照 frontend-design-3 skill 的规范，完全重新设计前端 UI/UX，复刻 Claude Cowork 的界面风格。

### 当前后端 API（必须保持完全兼容，不能改 API 端点）
后端是 FastAPI (Python)，端口 8789，提供以下接口：

**REST API:**
- GET /api/health — 健康检查 (返回 {"status": "ok"})
- POST /api/sessions — 创建会话 (返回 {id, title, ...})
- GET /api/sessions — 会话列表
- GET /api/sessions/{id} — 会话详情 + 消息
- POST /api/sessions/{id}/resume — 恢复会话
- POST /api/sessions/{id}/fork — 分叉会话
- PUT /api/sessions/{id}/title — 重命名会话
- PUT /api/sessions/{id}/permission — 切换权限模式 (safe/balanced/full_auto)
- DELETE /api/sessions/{id} — 删除会话
- GET /api/sessions/{id}/approvals — 审批列表
- GET /api/sessions/{id}/artifacts — 产物列表
- GET /api/artifacts/{id} — 产物详情
- GET /api/artifacts/{id}/preview — 产物预览 (返回 base64 内容)
- GET /api/settings — 获取配置 (模型/权限/工作区)
- PUT /api/settings — 保存配置
- GET /api/logs — 后端日志 (最近 500 行)
- GET /api/recovery — 异常中断会话列表

**WebSocket:**
- WS /ws/{session_id} — 实时事件流
- 事件类型：session.ready, session.closed, session.run_complete, session.busy
  - assistant.delta (流式文本), assistant.complete
  - tool.started, tool.completed
  - transcript.item, approval.request, question.request

### 当前前端结构（3289 行 HTML/CSS/JS）
当前文件位于：`apps/host-python/frontend/index.html`

必须保留的功能模块：
1. 侧边栏会话管理（列表 + 搜索 + 新建/删除/重命名/恢复）
2. 权限模式切换（safe/balanced/full_auto）
3. 消息流（用户气泡 + AI 气泡 + 流式输出光标 + 工具卡片）
4. 工具卡片折叠/展开（hover 或点击展开显示工具输出）
5. Slash 命令弹窗（/help 等 50+ 命令）
6. 审批/提问弹窗（当 agent 需要人工确认时弹出）
7. 恢复横幅（当发现未正常关闭的会话时显示在顶部）
8. 文件拖拽上传（拖拽文件到输入栏，显示附件卡片）
9. 设置面板（模型配置 + 权限模式 + 工作区 + 日志查看）
10. 产物面板（右侧滑出面板，预览文件/图片）
11. 导出会话功能（复制消息内容 + 导出 .md）
12. Markdown 渲染（代码块高亮、列表、加粗等）

### UI/UX 设计要求（复刻 Claude Cowork 风格）

**核心设计哲学：**
- 极简、干净、专业的产品化界面
- 以对话为中心，减少视觉噪音
- 侧边栏纤细优雅，不喧宾夺主
- 输入框大而舒适（Auto-resize textarea，类似 Cowork）
- 工具卡片精致内敛，不突兀
- 色彩克制，用少量中性色 + 细微强调色

**具体设计要求：**

1. **色彩方案**：
   - 浅色/深色双主题（默认深色）
   - 深色主题：参考 Claude 的暗色系，偏暖的灰度层级，不是纯黑
   - 浅色主题：干净的白底 + 灰色层级
   - 强调色用温和的色调（不是强烈的紫色/霓虹色）

2. **布局**：
   - 整体三段式：侧边栏 + 主聊天 + 可选右侧预览
   - 侧边栏默认宽度 260px，可折叠（折叠后 60px 图标栏）
   - 主聊天区居中，消息最大宽度约 700px
   - 输入框固定在底部，auto-resize，有附件/语音等按钮位置（预留即可）
   - 右侧预览面板可滑入滑出，预览文件/图片/代码

3. **排版**：
   - 使用现代、干净的无衬线字体
   - 消息间距舒适
   - 工具用等宽字体，但精致美观

4. **交互细节**：
   - 流式输出时有光标闪烁
   - 工具卡片默认折叠，hover 或点击展开
   - 侧边栏会话项 hover 显示操作按钮
   - 输入栏拖拽文件时有视觉反馈
   - 设置面板、审批面板用模态/滑面板形式

5. **空状态**：
   - 无会话时显示漂亮的空状态（logo + 快捷操作 + 示例提示）
   - 新建对话时自动聚焦输入框

### 技术约束
- 必须输出**单文件 HTML**（包含内联 CSS + JS），保持当前文件结构
- 可以用 CDN 引入 marked.js（已有）
- 保持与后端 API 的完全兼容
- 所有 JavaScript 交互逻辑必须完整实现（不能只是 UI，功能要能真用）
- 文件输出到：`apps/host-python/frontend/index.html`
- 覆盖现有文件

### 输出
直接在 `apps/host-python/frontend/index.html` 写入完整的新前端代码，不要分文件，单文件交付。

### frontend-design-3 规范要求
- 避免使用 Inter、Roboto、Arial 等烂大街字体
- 避免 AI 常用的紫色渐变、Space Grotesk 等
- 色彩方案要克制专业，不是过度设计
- 排版讲究层次感和留白
- 整体气质接近 Claude Cowork 的产品风格
