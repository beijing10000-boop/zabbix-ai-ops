# Zabbix MCP：只读访问

当前系统只保留 Zabbix MCP 的只读配置：`mcp_url` 和 `mcp_token`。

- MCP 服务端应使用只读 Zabbix API 账户；务必验证访问范围。
- 运维 AI 仅能够查询监控数据、事件和历史指标，不执行写入工具。
- 飞书告警屏蔽是 **AI Ops 应用层通知过滤**，既不确认事件，也不修改 Zabbix 触发器。
- 旧的写入 MCP 地址、Token、审批执行器和 API 已移除，请不要配置或启用它们。

参见 [配置说明](CONFIGURATION.md) 与 [飞书屏蔽](FEISHU-CARD-MUTE.md)。
