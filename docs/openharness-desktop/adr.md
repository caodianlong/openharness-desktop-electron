# ADR（Architecture Decision Records）

## ADR-001：采用 Electron 而非 Tauri
**决策**：MVP 与 Beta 使用 Electron。  
**原因**：桌面工作台复杂、Node 生态成熟、Python Host 集成更稳。  
**后果**：包体更大，但研发速度和稳定性更优。

## ADR-002：不采用 CLI 集成
**决策**：禁止以 OpenHarness CLI 作为产品主集成方式。  
**原因**：协议脆弱、生命周期差、黑窗口、恢复差。  
**后果**：需要额外开发 Python Host Adapter。

## ADR-003：OpenHarness 仅通过 Host Adapter 暴露
**决策**：UI 不直接依赖 OpenHarness。  
**原因**：降低升级破坏面。  
**后果**：Host 层成为关键适配边界。

## ADR-004：产品态数据由桌面壳主导
**决策**：conversation / message / run / task 等主模型由产品层定义。  
**原因**：OpenHarness 内部状态不应直接成为产品模型。  
**后果**：需要映射层与同步逻辑。

## ADR-005：默认安全模式，支持 Full Auto
**决策**：默认 Safe，支持显式 Full Auto。  
**原因**：平衡风险与效率。  
**后果**：必须实现审批、审计、作用域控制。

## ADR-006：MVP 通信协议使用 HTTP + WebSocket
**决策**：先不用 gRPC。  
**原因**：实现简单、调试方便。  
**后果**：后续若性能成为瓶颈再升级。
