# Zabbix AI Ops

**Zabbix + AI + Feishu** 运维集成平台，当前为 **v0.1 开发预览版**，仓库为 Private。请勿覆盖现有生产部署。

## 项目定位

- Zabbix 告警：Webhook → Redis/RQ → Zabbix MCP 只读查询 → AI 分析 → 飞书告警卡片。
- Web 管理：FastAPI + 静态单页管理界面，支持模型、MCP、Webhook、飞书等配置。
- 安全：初始化管理员 API Token，SQLite 配置存储，Fernet 加密密钥，MCP 工具只读白名单。
- 已加入开发版：飞书群主动问答与进度卡片更新；开发版已接入：回复原告警关联事件、指定管理员本人二次确认（默认模拟）；受限 MCP 写入尚待生产验收；研发中：多用户权限、升级回滚。

> **重要：** 此代码根据此前的项目讨论和已生成补丁重新整合，不是从现有生产服务器导出的最终镜像。仍需在隔离环境完成兼容性和安全验证。

## 快速预览

阅读 [安装文档](docs/INSTALLATION.md)，准备 `APP_ENCRYPTION_KEY`、`ADMIN_API_TOKEN` 后：

```sh
docker compose up -d --build
curl http://127.0.0.1:8088/healthz
```

默认只监听宿主机 loopback；访问 Web 管理界面请通过 SSH 隧道或可信 HTTPS 反向代理。不要直接将 HTTP 管理端口暴露公网。

## 主要模块

| 组件 | 位置 | 当前状态 |
|---|---|---|
| Web 管理接口 | `app/main.py` | 开发版 |
| Web 界面 | `web/index.html` | 开发版 |
| AI 告警 Worker | `app/worker.py` | 开发版 |
| Zabbix MCP 只读查询 | `app/mcp_client.py` | 开发版，待联调 |
| 飞书问答接收与 Worker | `app/feishu_bot.py`、`app/qa_worker.py` | 开发版，待端到端联调 |\n| 只读 MCP 工具问答 | `app/ai_agent.py` | 开发版 |
| Docker Compose | `docker-compose.yml` | 开发版 |
| pytest/CI | `tests/`, `.github/workflows/` | 基础测试 |

## 文档

- [部署与运行](docs/INSTALLATION.md)
- [配置说明](docs/CONFIGURATION.md)
- [常见问题](docs/TROUBLESHOOTING.md)
- [开发状态](docs/STATUS.md)
- [后续路线图](docs/ROADMAP.md)\n- [Zabbix Webhook 对接](docs/ZABBIX.md)\n- [飞书机器人配置](docs/FEISHU.md)\n- [升级与备份](docs/UPGRADING.md)\n- [安全说明](SECURITY.md)\n- [回复告警与变更审批](docs/CHANGE_APPROVAL.md)

## 安全声明

**不要上传生产密钥和配置。** 勿提交 `.env`、Token、数据库、Webhooks 或运行日志；禁止开放 MCP 写入到普通聊天会话。尚未实现完整的 RBAC 和审批执行器。

当前仓库暂未选定开源 License，仅供获授权的私有仓库成员使用。
