# 技术架构方案 v0.1

## 1. 总体架构

采用四层结构：

1. **React Renderer**：展示与交互层  
2. **Electron Main**：桌面控制层  
3. **Python Headless Host**：宿主服务层  
4. **OpenHarness Core**：执行内核层  

### 架构原则
- 产品体验一体化，工程实现分层化
- OpenHarness 只通过 Host Adapter 暴露能力
- UI 不碰 OpenHarness 私有结构
- 事件驱动优先，命令调用为辅
- 运行态和产品态分离

## 2. 为什么选这个方案

### 2.1 采用 Electron + React + Python Host + Library Integration 的原因
1. **Electron** 最适合复杂桌面工作台
   - 窗口、托盘、菜单、自动更新成熟
   - 与 React 组合成熟
   - 跨平台成本最低

2. **React** 适合高交互复杂界面
   - 会话、任务、审批、日志、文件预览都适合 React

3. **Python Headless Host** 适合深度集成 OpenHarness
   - OpenHarness 本身就是 Python 生态
   - 直接库调用优于命令行桥接
   - 便于做适配、恢复、拦截、能力探测

4. **Library Integration** 是长期可维护路线
   - 更稳的能力边界
   - 更好的升级控制
   - 没有 CLI 黑窗口和 stdout 协议脆弱性

## 3. 为什么不采用 CLI 集成

### 结论
**CLI 集成不适合作为正式产品底座。**

### 原因
- CLI 输出本质是人类可读，不是稳定协议
- stdout/stderr 不是理想事件总线
- Windows 黑窗口、编码、路径、信号处理问题多
- 审批挂起/恢复难做
- 版本兼容性差
- 很难优雅实现“无感一体化桌面体验”

## 4. 各层职责划分

| 层 | 职责 | 不负责 |
|---|---|---|
| React Renderer | 会话 UI、任务 UI、审批 UI、预览器、设置 | 直接调 OpenHarness |
| Electron Main | 窗口、托盘、单实例、Host 拉起、系统能力、安全桥 | 业务编排 |
| Python Headless Host | 适配 OpenHarness、运行控制、审批挂起、恢复、协议输出 | 桌面 UI |
| OpenHarness Core | Agent 执行、tools、tasks、event 产出 | 产品数据模型 |

## 5. 通信方案

### 5.1 MVP
#### Renderer ↔ Main
- Electron IPC + preload bridge

#### Main ↔ Python Host
- **HTTP + WebSocket**
  - HTTP：命令与查询
  - WebSocket：流式事件

### 5.2 后续演进
- 增加 `/capabilities` 能力协商
- 增加 `/protocol/version` 协议协商
- 未来可评估 gRPC / domain socket / msgpack-rpc

## 6. 数据模型设计

### 核心实体
- `workspace`
- `conversation`
- `message`
- `run`
- `task`
- `agent_instance`
- `approval_request`
- `artifact`
- `file_asset`
- `event_log`
- `trace_span`
- `host_session`
- `setting`

### 建模原则
- 产品主模型由桌面壳定义
- OpenHarness 内部对象只做映射
- 每个主实体预留 `external_ref` 对应 OpenHarness 内核对象

## 7. 存储设计

### 7.1 方案
- **SQLite**：结构化元数据
- **文件系统归档**：产物、日志、快照、附件

### 7.2 推荐目录
```text
AppData/
  db/app.db
  artifacts/
    conv_{id}/run_{id}/
  logs/
  snapshots/
  cache/
  host/
```

## 8. 会话与历史方案

### 核心逻辑
- `conversation`：用户工作入口
- `message`：用户可见历史
- `run/task`：执行视图
- `event/trace`：诊断视图
- `artifact`：结果视图

### UI 表现
- 左栏：会话列表
- 中间：消息/任务主面板
- 右栏：审批/文件/日志/详情

### 复用策略
可以复用 OpenHarness 底层 session 机制，但**产品层会话历史必须由桌面壳统一管理**。

## 9. 权限与 Full Auto 模型

### 9.1 权限层级
1. App 级
2. Workspace 级
3. Conversation 级
4. Run 级临时授权

### 9.2 模式定义

| 模式 | 默认 | 特征 |
|---|---|---|
| Safe | 是 | 敏感动作需审批 |
| Balanced | 否 | 常规低风险动作自动放行 |
| Full Auto | 否 | 在授权范围内自动执行，完整审计 |

### 9.3 Full Auto 原则
- 必须显式开启
- 必须显示当前作用域
- 必须可一键停止
- 必须保留行为审计
- 必须可按目录、能力进行限制

## 10. 升级与兼容策略

### 核心原则
**适配 OpenHarness 的逻辑只能集中在 Python Host Adapter。**

### 具体策略
1. 引入 `HarnessAdapter`
2. UI 只依赖 Host 提供的稳定 facade
3. 做版本能力探测
4. 维护兼容矩阵：
   - Desktop App Version
   - Host Adapter Version
   - OpenHarness Version
   - Protocol Version

### 升级机制
- 小版本：兼容升级
- 大版本：先适配 Host，再升级分发
- 保留 pinned version
- 升级失败自动回退到上个可用版本

## 11. 打包与发布建议

### Windows
- `electron-builder`
- Python Host 以无窗口后台方式启动
- 处理 Defender、签名、安装权限、编码与路径问题

### macOS
- codesign + notarization
- Python runtime 与 app bundle 一起签名
- 处理文件访问权限

### Linux
- 优先 AppImage / deb
- 尽量内置隔离运行时
- 兼容 Wayland/X11 差异

## 12. 是否未来评估 Tauri

### 当前结论
**当前不建议。**

### 只有满足以下前提才值得评估
- Python Host 生命周期已稳定
- 自动更新与签名链路成熟
- Electron 包体或内存已成为明确业务瓶颈
- 团队具备 Rust 工程能力
- 有单独 2~4 周 spike 验证资源
