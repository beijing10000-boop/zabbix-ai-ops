# Docker 安装（开发预览版）

> 尚未完成对现有生产系统的端到端联调；建议使用测试机器，不要覆盖现有 `/data/zabbix-feishu-ai-agent`。

## 安装

准备 Docker Engine、Docker Compose、具有私有仓库访问权限的 GitHub 登录。

```bash
git clone https://github.com/beijing10000-boop/zabbix-ai-ops.git
cd zabbix-ai-ops
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
python3 -c 'import secrets; print(secrets.token_urlsafe(40))'
```

将两段随机输出分别配置为 `APP_ENCRYPTION_KEY` 和 `ADMIN_API_TOKEN`，写入本地 `.env`（权限 `chmod 600 .env`）。禁止上传仓库或发送到聊天中。

```bash
docker compose up -d --build
docker compose ps
curl -f http://127.0.0.1:8088/healthz
```

Web 仅映射到宿主机 `127.0.0.1:8088`；通过 SSH 隧道或受信任 HTTPS 反向代理访问，输入管理 Token。配置 MCP、OpenAI/Azure 模型、飞书 App ID/Secret、群白名单和告警 Webhook。

## 服务

- `web`：FastAPI + Web 管理页面
- `alert-worker`：分析 Zabbix Webhook 的告警
- `qa-worker`：回答飞书群 @AI 问题，并更新同一张卡片
- `feishu-receiver`：飞书 WebSocket 长连接事件接收
- `redis`：任务队列与去重

新飞书应用需启用机器人、发布消息权限、订阅 `im.message.receive_v1`，选择长连接接收事件。请避免同一飞书 App ID 有其他不共享队列的接收实例。

## 查看日志

```bash
docker compose logs -f web
docker compose logs -f feishu-receiver
docker compose logs -f qa-worker
docker compose logs -f alert-worker
```

## 已知限制

- 尚未实现完整升级回滚、密钥轮换、多账号管理。
- 飞书自定义 Webhook 的签名支持待补；启用签名校验的 Webhook 可能无法发送。
- 原告警引用回复、写入审批等尚未接入。
- MCP 和飞书权限需在真实设备上测试。不要把本开发版直接用于生产替换。
