# tg-monitor

macOS 菜单栏小工具,以个人 Telegram 账号(MTProto)身份监控所有已加入的群,实时捕获 5 类需要关注的消息并发系统通知:

- 私聊
- @username 直接提及
- 别人回复你的消息
- @all / @channel / @everyone / @here 群播
- 自定义关键词(在 `config.json` 中维护)

所有命中条目落地到 SQLite (`~/Library/Application Support/TGMonitor/data.db`),最近 20 条会出现在菜单栏弹出列表里;点击查看全文,系统不会自动把消息标为已读。

## 安装

> 需要 macOS、网络可访问 Telegram、公司下发的 `creds.env`(包含 `API_ID` / `API_HASH`)。

```bash
unzip tg-monitor-<version>.zip
cd tg-monitor
./install.sh
```

`install.sh` 会:

1. 检查/安装 [`uv`](https://astral.sh/uv)
2. 创建 venv 与数据目录 `~/Library/Application Support/TGMonitor/`
3. 把 `tg-monitor` 安装到 venv
4. 写 `config.json`,填入中心化的 `api_id` / `api_hash`
5. 启动交互式登录(手机号 + 短信验证码 + 可选 2FA)
6. 写 LaunchAgent `~/Library/LaunchAgents/com.tgmonitor.agent.plist` 并 bootstrap
7. 菜单栏出现 🔔 图标即可

首次弹通知时 macOS 会请求通知权限,允许即可。

## 使用

- 菜单栏 🔔 → 看到提醒数(`🔔 3` 表示 3 条未点击)
- **最近提醒** → 列出最近 20 条;点击任意一条弹窗看全文,关窗后该条变已查看
- **设置** → 编辑关键词(打开 `config.json` 用默认编辑器)/ 切换开机自启 / 切换通知声音 / 打开数据目录 / 查看日志
- **退出** → 同时停掉 LaunchAgent 拉起的常驻进程

## 卸载

```bash
./install.sh --uninstall
```

会卸 LaunchAgent;脚本会问是否一并删掉数据目录(含 session/DB/config)。

## 开发

```bash
uv venv
uv pip install -e .
# 直接跑(不走 LaunchAgent)
.venv/bin/python -m tg_monitor
# 单独跑登录
.venv/bin/tg-monitor-login
```

## 文件结构

```
tg_monitor/
├── __main__.py        程序入口
├── app.py             rumps 菜单栏 App、提醒预览、设置项
├── tg_client.py       Telethon worker 线程
├── matcher.py         5 类命中规则(纯函数,可单测)
├── store.py           SQLite 存档
├── config.py          config.json 读写
├── notifier.py        macOS 系统通知封装
├── paths.py           ~/Library 路径常量
└── login_cli.py       install.sh 调用的交互式登录
install.sh             一键安装/卸载
creds.env.example      凭据模板
pyproject.toml         依赖
```

## 风险与边界

- 不发送任何消息,只是被动监听 + 本地存档
- `mentioned` 标记 Telethon 在某些群播场景也会置位,因此 `mention` 与 `broadcast` 用 `entities + 正则` 双重判定
- 中心化 `api_id` 多账号共用属于公司可承担风险;每个账号工作量极低
- 修改 `config.json` 中 `keywords` 后立即生效,无需重启
