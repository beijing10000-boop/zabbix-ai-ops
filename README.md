# Zabbix AI Ops

**Zabbix + AI + Feishu** 运维集成平台，当前为 **v0.2 开发预览版**，仓库目前为 Public。请勿覆盖现有生产部署。

## 项目定位

- Zabbix 告警：Webhook → Redis/RQ → Zabbix MCP 只读查询 → AI 分析 → 飞书告警卡片。
- Web 管理：FastAPI + 静态单页管理界面，支持模型、MCP、Webhook、飞书等配置。
- 安全：飞书 OAuth 管理员登录（旧 Token 可选），SQLite 配置存储，Fernet 加密密钥，MCP 工具只读白名单。
- 已加入开发版：飞书群主动问答、进度卡片更新、回复原告警关联事件。仅允许使用只读 MCP，不包含任何 Zabbix 写入或审批执行器；多用户权限、升级回滚仍待完善。

> **重要：** 此代码根据此前的项目讨论和已生成补丁重新整合，不是从现有生产服务器导出的最终镜像。仍需在隔离环境完成兼容性和安全验证。

## 快速预览

阅读 [安装文档](docs/INSTALLATION.md)，准备必需的 `APP_ENCRYPTION_KEY`、飞书 OAuth 登录环境变量后：

```sh
docker compose up -d --build
curl http://127.0.0.1:8088/healthz
```

默认只监听宿主机 loopback；访问 Web 管理界面请通过可信 HTTPS 反向代理。不要直接将 HTTP 管理端口暴露公网。

## 主要模块

| 组件 | 位置 | 当前状态 |
|---|---|---|
| Web 管理接口 | `app/main.py` | 开发版 |
| Web 界面 | `web/index.html`、`web/assets/` | 开发版 |
| AI 告警 Worker | `app/worker.py` | 开发版 |
| Zabbix MCP 只读查询 | `app/mcp_client.py` | 开发版，待联调 |
| 飞书问答接收与 Worker | `app/feishu_bot.py`、`app/qa_worker.py` | 开发版，待端到端联调 |
| 只读 MCP 工具问答 | `app/ai_agent.py` | 开发版 |
| Docker Compose | `docker-compose.yml` | 开发版 |
| pytest/CI | `tests/`, `.github/workflows/` | 基础测试 |

## 文档

- [部署与运行](docs/INSTALLATION.md)
- [配置说明](docs/CONFIGURATION.md)
- [常见问题](docs/TROUBLESHOOTING.md)
- [开发状态](docs/STATUS.md)
- [后续路线图](docs/ROADMAP.md)
- [Zabbix Webhook 对接](docs/ZABBIX.md)
- [飞书机器人配置](docs/FEISHU.md)
- [升级与备份](docs/UPGRADING.md)
- [安全说明](SECURITY.md)

## 安全声明

**不要上传生产密钥和配置。** 勿提交 `.env`、Token、数据库、Webhooks 或运行日志；系统只使用只读 MCP；尚未实现完整 RBAC。

当前仓库暂未选定开源 License，目前公开展示，尚未选定开源许可；未经授权不得假定可再分发。
