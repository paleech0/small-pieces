# Claude Code Popup Notify

把 Claude Code 的权限申请变成 Windows 桌面弹窗——后台运行时不错过权限确认，前台时自动静默不打扰。

> 灵感来自 [KYinCode/claude-code-popup-hooks](https://github.com/KYinCode/claude-code-popup-hooks)，在其基础上重构并增强。

## 效果

![权限申请弹窗](screenshot.png)

## 功能

- **权限弹窗**：CC 申请权限时弹出交互式窗口，支持「同意」「同意并记住」「拒绝」
- **空闲通知**：CC 完成任务等待输入时弹窗提醒（6 秒自动消失）
- **前台检测**：终端在前台时自动跳过弹窗，不打扰当前工作
- **超时机制**：60 秒未操作自动拒绝，附带倒计时
- **一键屏蔽**：空闲通知可临时关闭，重启 CC 后自动恢复
- **键盘快捷键**：`Enter` 同意 · `Esc` 拒绝 · `Ctrl+Enter` 同意并记住

## 安装

### 1. 下载脚本

将 `cc-notify.py` 放到 `~/.claude/hooks/`（全局）或 `.claude/hooks/`（项目级）。

### 2. 配置 hooks

在 `~/.claude/settings.json` 中添加：

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.claude/hooks/cc-notify.py"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.claude/hooks/cc-notify.py"
          }
        ]
      }
    ]
  }
}
```

> 项目级使用时将 `~/.claude/` 改为 `.claude/`。

### 3. 重启 Claude Code

重启后生效。

## 依赖

**零依赖**——仅需要 Python 3 标准库（`tkinter`、`ctypes`、`json` 等），无需 `pip install`。

## 跨平台

自动适配 Windows / macOS / Linux 的字体和窗口行为。前台检测目前仅 Windows 完整支持。

## License

MIT
