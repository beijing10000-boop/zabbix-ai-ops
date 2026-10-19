# Zabbix Webhook 对接

项目开发版通过 `POST /zabbix` 接收 JSON 告警，使用 `Authorization: Bearer <secret>` 校验。

## 必要字段

```json
{
  "event_id": "123456",
  "event_value": "1",
  "event_source": "0",
  "event_name": "Linux: Zabbix agent is not available",
  "severity": "3",
  "host_id": "123",
  "host_name": "example-linux",
  "host_ip": "192.0.2.10",
  "trigger_id": "456",
  "subject": "Zabbix alert",
  "message": ""
}
```

Webhook Secret 必须在 Web 管理台设置。不要在任何公共渠道共享密钥。

## 过滤行为

当前预览版只接受触发器 Problem 事件：`event_source=0`、`event_value=1`。严重级别由 Web 的 `min_severity` 管控（0–5）。恢复事件默认跳过。成功排入队列返回 HTTP 202 + `status=queued`。重复 ID 则返回 `status=duplicate`，低等级或其他事件返回 `skipped`。

**注意：HTTP 202 并不保证任务成功执行；请检查 Worker 日志及 Redis 队列。**

## 常见诊断

- HTTP 401：Webhook Bearer 密钥错误。
- HTTP 422：事件 ID 缺失、级别值格式错误等。
- HTTP 202 `skipped`：确认事件类型和阈值。
- `duplicate`：24 小时内同一事件 ID 已接收过。
- Worker 没有处理：检查 `docker compose logs -f alert-worker`。

生产对接之前建议在隔离环境测试媒体类型和动作的具体 JSON 参数。
