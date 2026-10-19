# 部署指南：开发预览版

> 这是早期开发版本；**不要覆盖当前生产目录**。在隔离环境先验证。尚未提供发布版的迁移和回滚机制。

## 前提

Docker Engine + Compose plugin、可访问的 Redis 镜像和 Python 构建依赖。管理员 Web 接口默认绑定到宿主机 `127.0.0.1:8088`，必须通过可信 HTTPS 反向代理或 SSH 端口转发访问。

## 初始化

```bash
git clone https://github.com/beijing10000-boop/zabbix-ai-ops.git
cd zabbix-ai-ops
# 本仓库为 Private，请使用有访问权限的 GitHub 身份认证
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python3 -c "import secrets; print(secrets.token_urlsafe(40))"
```

将第一条输出设置到服务器的 `APP_ENCRYPTION_KEY`，第二条设置到 `ADMIN_API_TOKEN`。这两个值不要放到仓库中，也不要泄露在聊天或日志里。在仓库同级创建仅管理员可读的 `.env`（文件权限 `chmod 600 .env`）：

```ini
APP_ENCRYPTION_KEY=<生成的Fernet密钥>
ADMIN_API_TOKEN=<生成的随机Token>
```

启动：

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8088/healthz
```

利用 SSH 隧道在浏览器访问 `http://127.0.0.1:8088`，输入管理员 Token，在 Web 页面填写 Zabbix MCP、AI、Webhook 和飞书信息。

## 现阶段限制

- 已有 Web 配置页面，**尚不是正式的多管理员 RBAC 系统**。
- 当前入站告警只处理触发器 Problem 事件，低于阈值不分析。
- worker 通过 MCP 调用已发现的白名单查询工具；不同版本 MCP 的参数可能不兼容，需要核对后调试。
- **飞书主动群问答仍需整合**；此前的适配器 `backend/feishu_qa_card.py` 尚未接入新后台。
- Zabbix 写入/审批不可用，默认禁止写入。
- 飞书自定义 Webhook **签名校验/生成尚未整合**，如果启用签名，发送可能失败；请在正式环境完成前不要替代现有服务。
- 版本升级和回滚自动化仍在开发中。

## 检查日志

```bash
docker compose logs -f web
docker compose logs -f worker
docker compose logs -f redis
```
