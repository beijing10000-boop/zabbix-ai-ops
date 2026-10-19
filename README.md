# Zabbix AI Ops

面向 Zabbix 7.4+ 的 AI 告警分析与飞书群内问答项目（**开发中，尚未发布生产版**）。

## 目标功能

- Zabbix Webhook → Redis/RQ → AI → Zabbix MCP → 飞书交互卡片。
- 飞书群 @AI 主动查询监控数据，先发送“分析中”卡片，再更新同一张卡片。
- Web 后台管理模型、MCP、飞书、告警策略和提示词（**待实现**）。
- 私有仓库、版本发布、升级和回滚（**待完善**）。

## 当前代码状态

当前仓库是根据此前讨论的代码、已保存的飞书问答进度卡补丁，重新建立的开发基线；**不是从生产服务器 172.20.200.92 导出的完整运行镜像**。已有的 `feishu_qa_card.py` 是对旧版 `worker.process_question` 的适配器，尚需集成测试，不能单独部署运行。

禁止直接把此仓库替换到现有生产目录。详情见 [开发状态](docs/STATUS.md)。

## 目录

- `backend/feishu_qa_card.py` — 飞书“分析中 → 分析完成”卡片适配器（历史补丁代码）。
- `docs/INSTALLATION.md` — 安装规划及现有部署检查。
- `docs/CONFIGURATION.md` — 配置项和安全原则。
- `docs/TROUBLESHOOTING.md` — 已验证故障案例。
- `docs/ROADMAP.md` — Web 管理后台与升级规划。

## 安全

勿提交 `.env`、API Token、飞书 App Secret、Webhook URL、运行日志、数据库或生产 IP/主机清单。Git 历史中的泄露密钥必须轮换。写入 Zabbix 配置功能默认禁用，未来必须在后端验证审批身份。

## License

尚未选择开源许可证；本仓库当前为 Private。
