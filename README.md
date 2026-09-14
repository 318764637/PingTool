<img src="assets/app.png" alt="Ping Tool" width="96" align="right">

# Ping Tool

一个 Windows 桌面 Ping 工具，支持多目标并行 Ping 测试，以及 Tailscale、Windows 防火墙的服务管理。

## 功能特性

- 多目标并行 Ping：同时监控多个 IP/域名
- 实时延迟显示：显示当前延迟和平均延迟
- 目标管理：添加、删除、持久化保存 Ping 目标
- Tailscale 管理：一键重启 Tailscale 服务
- 防火墙管理：一键关闭 Windows 防火墙，也可随时恢复开启并查看当前状态
- 输入验证：支持 IPv4、IPv6、域名格式验证

## 下载

打包好的可执行文件在 [Releases](https://github.com/318764637/PingTool/releases) 页面：
下载 `PingTool.exe` 双击即可运行，无需安装 Python。

> 提示：仓库当前为私有，下载链接需要登录有权限的账号才能访问。

## 安装依赖

```bash
pip install -r requirements.txt
```

运行测试（可选）：

```bash
pip install -r requirements-dev.txt
pytest
```

## 运行

```bash
python main.py
```

## 打包

```bash
build.bat
```

打包后的可执行文件位于 `dist/PingTool.exe`（已内嵌 `assets/app.ico` 图标）。

图标由 `tools/make_icon.py` 用几何图形绘制生成，修改配色或造型后重新运行该脚本即可
重新生成 `assets/app.ico`（含 16–256px 共 9 种尺寸）。

## 配置

配置文件位于 `%APPDATA%/PingTool/config.json`。程序不会自动创建该文件，需要修改默认值时手动新建即可（未写的配置项使用下表默认值）。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| window_width | 500 | 窗口宽度 |
| window_height | 640 | 窗口高度 |
| ping_interval | 1.0 | Ping 间隔（秒），自本次发起算起 |
| ping_timeout | 3000 | Ping 超时（毫秒） |
| max_targets | 20 | 最大目标数 |
| log_max_bytes | 5242880 | 日志文件最大大小 |
| log_backup_count | 3 | 日志备份数量 |
| tailscale_stop_wait | 3 | 停止 Tailscale 后等待秒数 |
| tailscale_cmd_timeout | 30 | 服务命令超时（秒） |
| firewall_cmd_timeout | 30 | 防火墙命令超时（秒） |

## 权限说明

- 重启 Tailscale 服务需要管理员权限，点击按钮后会弹出 UAC 确认窗口。
- 关闭/开启 Windows 防火墙同样需要管理员权限，点击后弹出 UAC 确认窗口；状态显示读取注册表，无需提权。
- 关闭防火墙会降低系统的安全防护，程序会在操作前二次确认。

## 目录结构

```
ping_tool/
├── main.py              # 入口文件
├── config.py            # 配置管理
├── logger.py            # 日志系统
├── data/
│   └── manager.py       # 数据管理
├── core/
│   ├── ping_worker.py   # Ping 引擎
│   ├── tailscale.py     # Tailscale 管理
│   ├── firewall.py      # Windows 防火墙管理
│   └── elevation.py     # 管理员权限判定与 UAC 提权（各功能共用）
├── ui/
│   ├── app.py           # 主窗口
│   ├── styles.py        # 样式常量
│   └── components/      # UI 组件（目标卡片 / Tailscale / 防火墙 / 状态栏）
└── utils/
    └── validators.py    # 输入验证
```

## 日志

日志文件位于 `%LOCALAPPDATA%/PingTool/logs/pingtool.log`。
