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

## 飞书账号登录（新版 Web 控制台）

后台使用企业自建飞书应用网页授权，登录用户 Open ID 必须处于服务器环境变量 `FEISHU_ADMIN_OPEN_IDS` 白名单中。服务器端保存随机会话，浏览器只保存 HttpOnly、Secure、SameSite=Lax Cookie；写入接口要求 CSRF Token。**要求 HTTPS，不能直接通过 `http://172.20.200.93:8088` 完成 OAuth 登录。**

1. 在飞书开放平台的当前自建应用中开通网页授权，进入“安全设置 → 重定向 URL”，填写与服务器完全一致的 `https://你的域名/api/v1/auth/callback`，并发布应用配置。
2. 将该域名使用 HTTPS 反向代理到 `127.0.0.1:8088`；建议仅管理网络能访问。
3. 在服务器 `.env` 中增加：
   ```ini
   FEISHU_LOGIN_REDIRECT_URI=https://你的域名/api/v1/auth/callback
   FEISHU_ADMIN_OPEN_IDS=ou_你的飞书管理员OpenID
   ALLOW_LEGACY_ADMIN_TOKEN=false
   ```
4. `docker compose up -d --build web`，访问 HTTPS 地址，点击“使用飞书账号登录”。复用之前 Web 已保存的 `lark_app_id`、`lark_app_secret`，无需再次写到浏览器。
5. 验证 `/api/v1/auth/me`、配置、AI 测试与日志可用，退出后不能再访问受保护接口。

**从旧 Web 迁移：** 旧版管理员 Token 不再是页面登录方式。仅在故障迁移时可临时设置 `ALLOW_LEGACY_ADMIN_TOKEN=true` 启用旧 API Token；结束后必须关闭。不要删除 `APP_ENCRYPTION_KEY` 或原 SQLite 数据卷。飞书应用的 OAuth 登录和飞书机器人 WebSocket 接收是独立功能，不要求立即把 92 的长连接切换到 93。
