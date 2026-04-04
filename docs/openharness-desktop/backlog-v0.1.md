# 开发计划与 Backlog v0.1

## 1. 阶段划分

### 阶段 0：预研 / Spike（1~2 周）
目标：验证关键技术路线可行。

#### Spike 清单
1. Electron 拉起 Python Headless Host，且无黑窗口
2. OpenHarness 作为库模块可被 Host 调用
3. Host 能输出稳定 HTTP + WS 协议
4. MVP 数据模型是否覆盖核心场景
5. OpenHarness 升级适配策略可行

### 阶段 1：MVP（4~6 周）
目标：形成完整最小可用桌面工作台。

#### 范围
- 会话列表
- 消息流
- 审批
- 基础任务面板
- 文件预览
- 设置
- SQLite
- 崩溃恢复基础版

### 阶段 2：Beta（4~6 周）
目标：增强稳定性、任务流和可追溯能力。

#### 范围
- 任务中心
- trace 浏览
- 审批规则模板
- 搜索与过滤
- OpenHarness 版本管理

### 阶段 3：1.0（6~8 周）
目标：达到可长期使用的正式桌面产品标准。

#### 范围
- 细粒度权限
- 更完整恢复
- 自动更新与回滚
- 多 workspace
- 更强诊断能力

## 2. 按周建议

### Week 1
- 仓库结构搭建
- Electron + Host 启动链路打通
- 协议草案冻结 v0

### Week 2
- HarnessAdapter 原型
- HTTP + WS 跑通
- DB schema v0
- Host 健康检查

### Week 3
- 会话列表
- 消息主视图
- 新建会话流程

### Week 4
- run/task 状态面板
- 审批 UI
- 基础 artifact 列表

### Week 5
- 设置页
- Full Auto 模式切换
- 文件预览器

### Week 6
- 崩溃恢复基础版
- 诊断导出
- 集成测试与首轮修复

## 3. Backlog 优先级

### P0
- 无黑窗口 Host 启动
- HarnessAdapter
- 协议定义
- SQLite schema
- 会话列表
- 消息流
- 审批机制
- 基础 artifact 预览
- Safe / Balanced / Full Auto 模式

### P1
- task 面板
- trace/event log
- 崩溃恢复
- 设置页
- 诊断包导出
- OpenHarness 版本管理

### P2
- 搜索/过滤
- diff 预览
- 审批模板
- 多 workspace
- 自动更新
- 更丰富日志视图

## 4. 依赖关系与关键路径

### 关键路径
1. Host 启动与协议
2. HarnessAdapter
3. 数据模型与 DB
4. 会话与消息主链路
5. 审批链路
6. artifact/预览
7. 恢复与诊断

### 强依赖
- 审批 UI 依赖 approval service + 事件协议
- 会话历史依赖 DB schema
- 恢复依赖 event log + snapshots
- 版本升级依赖 HarnessAdapter 能力探测
