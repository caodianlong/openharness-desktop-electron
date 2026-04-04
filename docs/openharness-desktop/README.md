# OpenHarness Desktop Docs

本文档目录用于沉淀 OpenHarness Desktop（Electron 壳）项目的产品、架构、实施与决策文档。

## 文档列表

- `prd-v0.1.md`：产品需求文档
- `architecture-v0.1.md`：技术架构方案
- `implementation-plan-v0.1.md`：工程实施方案
- `backlog-v0.1.md`：开发计划与 backlog
- `adr.md`：关键架构决策记录

## 默认技术路线

- Electron
- React
- Python Headless Host
- OpenHarness Library Integration

## 原则

- 不做 CLI 集成
- 不重写 AI Agent 内核
- 桌面体验必须一体化
- 默认安全模式，但支持 Full Auto
- OpenHarness 需可升级、可兼容
