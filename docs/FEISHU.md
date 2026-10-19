# 飞书企业机器人与自定义 Webhook

系统目前使用两种独立飞书通道：

1. **告警卡片**：Zabbix AI Worker 通过群自定义机器人 Webhook 发送。
2. **主动问答**：企业自建飞书应用经 WebSocket 长连接接收群内 @，并通过应用 API 发送和更新问答卡片。

## 企业自建应用

打开飞书开放平台创建应用，启用机器人、开通接收群内 @ 消息和以机器人身份发送消息的相关权限；发布应用版本。添加 `im.message.receive_v1` 事件，选择长连接模式，然后将应用机器人加入目标群聊。

在 Web 管理页面填写 `lark_app_id`、`lark_app_secret`、`allowed_chat_ids`。

`allowed_chat_ids` 可以用逗号分隔多个 `oc_...` 群 ID。只有白名单群的文字消息会入队。确保 @ 的是企业应用机器人，而不是告警自定义 Webhook 机器人。

卡片更新需要相应飞书消息修改权限。若更新失败，问答 Worker 尝试发送普通消息兜底。

## 避免长连接抢事件

同一个飞书应用的多台独立 WebSocket 客户端可能竞争分发事件；如果使用相同 App ID，请确保只有一个接收实例，或所有实例都使用相同 Redis 和完全一致的入队逻辑。

## 查看日志

```bash
docker compose logs -f feishu-receiver
docker compose logs -f qa-worker
```

搜索关键字：`FEISHU_RECEIVED`、`FEISHU_FILTERED`、`FEISHU_QUEUED`、`FEISHU_PROGRESS_SENT`、`FEISHU_CARD_UPDATED`。

## 自定义机器人

在 Web 配置 `feishu_webhook_url`；如果机器人开启签名，则同时配置 `feishu_sign_secret`。告警消息会采用 `interactive` 格式。

请对飞书机器人 Webhook 进行网络和使用范围限制；Webhook URL 本身是敏感凭据。
