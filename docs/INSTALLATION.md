# 安装指南（开发版）

**本仓库尚无完整安装器，请勿直接覆盖生产环境。**

原部署参考环境：
- Rocky Linux 9、Python 3.11。
- Redis + RQ：独立队列 `ai-alerts` 和 `ai-questions`。
- Zabbix 7.4、外部 Zabbix MCP Server、Azure OpenAI Responses API。
- 飞书企业应用通过 WebSocket 接收群聊 @；独立 Webhook 用于告警卡片。

正式版计划支持：
1. Docker Compose 快速安装。
2. Rocky Linux 9/10 systemd 部署。
3. Web 首次初始化管理员、连接 MCP、配置模型与飞书。
4. 发布校验、配置备份及版本回滚。

当前不能直接执行 README 中不存在的 `install.sh`。
