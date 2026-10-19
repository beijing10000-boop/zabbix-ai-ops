# 开发状态

## 可用历史代码

- 飞书 AI 问答进度卡适配器 `backend/feishu_qa_card.py`：来自先前生成的补丁，经过语法校验，**未在此新仓库完整联调**。
- 已确认的服务器运行机制：Zabbix Webhook、Redis 的 `ai-alerts` / `ai-questions` 队列、Azure Responses、Zabbix MCP、飞书 WebSocket。

## 尚未完成

- 独立可安装的后端服务、前端 Web 配置后台、持久化加密配置、管理员登录。
- 告警链路和问答链路在新仓库的完整源码整合、自动测试和发布制品。
- 飞书回复原告警、审批后通过 MCP 修改 Zabbix 配置。
- 可验证的升级和回滚脚本。

## 发布原则

本仓库现在是 **development bootstrap**。不能声称已包含生产服务器最终版本，更不能直接部署覆盖现有系统。
