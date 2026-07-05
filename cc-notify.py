#!/usr/bin/env python3
"""
Claude Code 桌面弹窗 Hook — 权限对话框 + 空闲通知

功能：
  PermissionRequest → 交互式弹窗（同意 / 同意并记住 / 拒绝），60s 超时自动拒绝
  Notification (idle_prompt) → 轻量通知，6s 自动消失

安装：
  将本文件放到 ~/.claude/hooks/ 并在 settings.json 中配置 hooks（见下方 MAINFEST）
  仅依赖 Python 标准库（tkinter），无需 pip install

键盘快捷键：
  Enter = 同意    Esc = 拒绝    Ctrl+Enter = 同意并记住
"""

import sys
import os
import json
import traceback
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG = os.path.join(SCRIPT_DIR, 'cc-notify_error.log')

# ═══════════════════════════════════════════════════════════════════════
# 平台检测 & 字体
# ═══════════════════════════════════════════════════════════════════════

IS_WIN = sys.platform == 'win32'
IS_MAC = sys.platform == 'darwin'

if IS_WIN:
    FONT_SANS = ('Microsoft YaHei UI', 10)
    FONT_SANS_BOLD = ('Microsoft YaHei UI', 11, 'bold')
    FONT_MONO = ('Consolas', 9)
    FONT_TITLE = ('Microsoft YaHei UI', 13, 'bold')
    FONT_COUNTDOWN = ('Microsoft YaHei UI', 8)
elif IS_MAC:
    FONT_SANS = ('Helvetica Neue', 10)
    FONT_SANS_BOLD = ('Helvetica Neue', 11, 'bold')
    FONT_MONO = ('Menlo', 9)
    FONT_TITLE = ('Helvetica Neue', 13, 'bold')
    FONT_COUNTDOWN = ('Helvetica Neue', 8)
else:
    FONT_SANS = ('Noto Sans', 10)
    FONT_SANS_BOLD = ('Noto Sans', 11, 'bold')
    FONT_MONO = ('DejaVu Sans Mono', 9)
    FONT_TITLE = ('Noto Sans', 13, 'bold')
    FONT_COUNTDOWN = ('Noto Sans', 8)

# ═══════════════════════════════════════════════════════════════════════
# 配色
# ═══════════════════════════════════════════════════════════════════════

COLORS = {
    'bg':           '#f0f2f5',
    'card':         '#ffffff',
    'card_input':   '#f8f9fa',
    'text':         '#1a1a2e',
    'muted':        '#8b8fa3',
    'accent':       '#4f46e5',
    'accent_hover': '#4338ca',
    'danger':       '#dc2626',
    'danger_hover': '#b91c1c',
    'remember':     '#059669',
    'remember_hover': '#047857',
    'border':       '#e5e7eb',
    'footer_bg':    '#f9fafb',
}

# ═══════════════════════════════════════════════════════════════════════
# 超时（秒）
# ═══════════════════════════════════════════════════════════════════════

PERMISSION_TIMEOUT = 60
IDLE_AUTO_CLOSE = 6

# 空闲通知屏蔽（同一 CC 会话内有效，重启 CC 后重置）
# 原理：存储 CC 进程 PID，PID 不同 = 新会话 → 屏蔽失效
MUTE_FILE = os.path.join(SCRIPT_DIR, 'cc-notify_muted.json')


def _is_idle_muted():
    """检查当前 CC 会话是否已屏蔽空闲通知。"""
    if not os.path.exists(MUTE_FILE):
        return False
    try:
        with open(MUTE_FILE, 'r', encoding='utf-8') as f:
            data = json.loads(f.read())
        if data.get('pid') == os.getppid():
            return True
        # PID 不匹配 → 旧会话残留 → 清除
        os.remove(MUTE_FILE)
    except Exception:
        try:
            os.remove(MUTE_FILE)
        except Exception:
            pass
    return False


def _mute_idle():
    """屏蔽当前 CC 会话的空闲通知。"""
    try:
        with open(MUTE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'pid': os.getppid()}, f)
    except Exception:
        pass


# 静默模式（弹窗最小化到任务栏，不抢焦点）
# 持久标记文件，手动创建/删除即可切换
QUIET_FILE = os.path.join(SCRIPT_DIR, 'cc-notify_quiet')


def _is_quiet():
    """检查静默模式是否开启。"""
    return os.path.exists(QUIET_FILE)


def _toggle_quiet():
    """切换静默模式。"""
    try:
        if os.path.exists(QUIET_FILE):
            os.remove(QUIET_FILE)
            return False
        else:
            with open(QUIET_FILE, 'w') as f:
                f.write('quiet')
            return True
    except Exception:
        return _is_quiet()

# ═══════════════════════════════════════════════════════════════════════
# Windows 原生辅助
# ═══════════════════════════════════════════════════════════════════════

def _win32_flash_taskbar(hwnd):
    """闪烁任务栏图标，吸引用户注意。"""
    try:
        import ctypes
        FLASHW_ALL = 0x3 | 0xC  # caption + tray + timer no foreground
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.c_uint),
                ('hwnd', ctypes.c_void_p),
                ('dwFlags', ctypes.c_uint),
                ('uCount', ctypes.c_uint),
                ('dwTimeout', ctypes.c_uint),
            ]
        fwi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_ALL, 0, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(fwi))
    except Exception:
        pass

def _win32_force_foreground(hwnd):
    """强制将窗口拉到前台。"""
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)   # ASFW_ANY
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, 9)             # SW_RESTORE
    except Exception:
        pass

def _win32_get_tk_hwnd(root):
    """从 tkinter root 获取原生 HWND。"""
    try:
        # .frame() 返回十六进制字符串 → int
        return int(root.frame(), 16)
    except Exception:
        return None

def _is_terminal_foreground():
    """
    检测 Claude Code 所在的终端是否在前台。
    在前台 → 用户正盯着终端 → 无需弹窗，让 CC 原生提示处理。
    在后台 → 用户在做别的事 → 弹窗通知。
    """
    if not IS_WIN:
        # macOS / Linux：暂不做检测（实现复杂，后续可加）
        return False

    try:
        import ctypes

        fg = ctypes.windll.user32.GetForegroundWindow()
        if not fg:
            return False

        # ── 方法 1：直接比较控制台窗口 ──────────────────────────
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console and console == fg:
            return True

        # ── 方法 2：检查前台窗口的根所有者 ──────────────────────
        GA_ROOT = 2
        root_owner = ctypes.windll.user32.GetAncestor(fg, GA_ROOT)
        if console and root_owner == console:
            return True

        # ── 方法 3：检查窗口类名（Windows Terminal / 传统控制台）
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(fg, buf, 256)
        cls = buf.value

        # 已知终端窗口类名
        if cls in (
            'ConsoleWindowClass',             # 传统 conhost.exe
            'CASCADIA_HOSTING_WINDOW_CLASS',  # Windows Terminal
        ):
            return True

        # ── 方法 4：检查前台进程名 ──────────────────────────────
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        hproc = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if hproc:
            buf = ctypes.create_unicode_buffer(260)
            size = ctypes.c_ulong(260)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                hproc, 0, buf, ctypes.byref(size)
            ):
                exe = buf.value.lower()
                ctypes.windll.kernel32.CloseHandle(hproc)
                for name in (
                    'cmd.exe', 'powershell', 'winterminal', 'conhost',
                    'mintty', 'bash.exe', 'alacritty', 'wezterm',
                    'conemu', 'kitty', 'putty',
                ):
                    if name in exe:
                        return True
                return False
            ctypes.windll.kernel32.CloseHandle(hproc)

        return False
    except Exception:
        return False  # 无法判断 → 宁可弹窗也不错漏


# ═══════════════════════════════════════════════════════════════════════
# tkinter 工具函数
# ═══════════════════════════════════════════════════════════════════════

def _center_window(root, w, h):
    """将窗口放在鼠标所在显示器的中央。"""
    root.update_idletasks()
    try:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f'{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}')
    except Exception:
        root.geometry(f'{w}x{h}+100+100')

def _bring_to_front(root, default_btn):
    """弹窗置顶 + 获取焦点 + 任务栏闪烁。"""
    root.lift()
    root.attributes('-topmost', True)
    root.after(300, lambda: root.attributes('-topmost', False))
    root.focus_force()
    if default_btn:
        default_btn.focus_set()
    if IS_WIN:
        hwnd = _win32_get_tk_hwnd(root)
        if hwnd:
            root.after(50, lambda: _win32_force_foreground(hwnd))
            root.after(400, lambda: _win32_flash_taskbar(hwnd))

def _generate_summary(tool_name, tool_input):
    """根据工具名和参数生成中文权限概述。"""
    desc = tool_input.get('description', '')

    if tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        if desc:
            return desc
        cmd_short = cmd[:120].replace('\n', ' ') + ('…' if len(cmd) > 120 else '')
        return f'执行命令：{cmd_short}'

    elif tool_name == 'PowerShell':
        cmd = tool_input.get('command', '')
        if desc:
            return desc
        return '执行 PowerShell 命令'

    elif tool_name == 'Write':
        filepath = tool_input.get('file_path', '')
        filename = os.path.basename(filepath)
        dirname = os.path.dirname(filepath)
        if desc:
            return desc
        return f'写入文件：{filename}（{dirname}）'

    elif tool_name == 'Edit':
        filepath = tool_input.get('file_path', '')
        filename = os.path.basename(filepath)
        if desc:
            return desc
        return f'编辑文件：{filename}'

    elif tool_name == 'Read':
        filepath = tool_input.get('file_path', '')
        filename = os.path.basename(filepath)
        return f'读取文件：{filename}'

    else:
        return desc if desc else f'使用工具：{tool_name}'


def _extract_detail(tool_input):
    """从 tool_input 字典提取可读文本。"""
    if not tool_input:
        return ''
    lines = []
    for k, v in tool_input.items():
        if k == 'description':
            continue
        if isinstance(v, str):
            lines.append(f'{k}: {v}')
        elif isinstance(v, (int, float, bool)):
            lines.append(f'{k}: {v}')
        elif isinstance(v, (dict, list)):
            lines.append(f'{k}: {json.dumps(v, ensure_ascii=False)}')
    return '\n'.join(lines)

# ═══════════════════════════════════════════════════════════════════════
# 权限请求弹窗（阻塞，需要用户操作）
# ═══════════════════════════════════════════════════════════════════════

def show_permission_dialog(data):
    """
    显示交互式权限确认弹窗。
    返回: {'behavior': 'allow'|'deny', 'updatedPermissions': [...]}
    """

    import tkinter as tk
    from tkinter import ttk

    tool_name = data.get('tool_name', 'Unknown Tool')
    tool_input = data.get('tool_input', {})
    suggestions = data.get('permission_suggestions', [])

    # ── 默认拒绝 ──
    decision = {'behavior': 'deny'}
    timed_out = threading.Event()

    root = tk.Tk()
    root.title('Claude Code · 权限确认')
    root.resizable(False, False)
    root.configure(bg=COLORS['bg'])

    # 窗口尺寸
    win_w = 560
    n_sug = max(len(suggestions), 1)
    win_h = 265 + min(n_sug, 4) * 36
    _center_window(root, win_w, win_h)

    # ── Header ────────────────────────────────────────────────────
    header = tk.Frame(root, bg=COLORS['bg'])
    header.pack(fill='x', padx=24, pady=(16, 8))

    tk.Label(
        header, text='🔐', font=('Segoe UI Emoji', 18), bg=COLORS['bg']
    ).pack(side='left', padx=(0, 8))
    tk.Label(
        header, text='Claude Code 请求权限',
        font=FONT_TITLE, fg=COLORS['text'], bg=COLORS['bg']
    ).pack(side='left')

    # ── 工具信息卡片 ──────────────────────────────────────────────
    card = tk.Frame(
        root, bg=COLORS['card'], padx=14, pady=10,
        highlightbackground=COLORS['border'], highlightthickness=1
    )
    card.pack(fill='x', padx=20, pady=(0, 8))

    # 权限概述（中文自然语言描述）
    summary = _generate_summary(tool_name, tool_input)
    if summary:
        summary_label = tk.Label(
            card, text=summary,
            font=FONT_SANS, fg='#374151', bg=COLORS['card'],
            wraplength=win_w - 52, justify='left'
        )
        summary_label.pack(anchor='w')

        # 概述和工具名之间加一点间距
        tk.Frame(card, bg=COLORS['card'], height=6).pack(fill='x')

    tk.Label(
        card, text=f'工具：{tool_name}',
        font=FONT_SANS_BOLD, fg=COLORS['accent'], bg=COLORS['card']
    ).pack(anchor='w')

    detail = _extract_detail(tool_input)
    if detail:
        detail_frame = tk.Frame(card, bg=COLORS['card'])
        detail_frame.pack(fill='x', pady=(6, 0))

        detail_text = tk.Text(
            detail_frame, font=FONT_MONO, fg=COLORS['text'],
            bg=COLORS['card_input'], wrap='word', height=4,
            bd=1, padx=8, pady=5, cursor='arrow', relief='solid'
        )
        detail_text.insert('1.0', detail)
        detail_text.configure(state='disabled')
        detail_text.pack(side='left', fill='both', expand=True)

        scrollbar = tk.Scrollbar(
            detail_frame, command=detail_text.yview,
            bd=0, elementborderwidth=0, highlightthickness=0
        )
        scrollbar.pack(side='right', fill='y')
        detail_text.configure(yscrollcommand=scrollbar.set)

    # ── 倒计时 + 静默开关 ──────────────────────────────────────────
    bottom_row = tk.Frame(root, bg=COLORS['bg'])
    bottom_row.pack(fill='x', padx=20, pady=(0, 6))

    countdown_var = tk.StringVar(value=f'⏱ {PERMISSION_TIMEOUT}s 后自动拒绝')
    tk.Label(
        bottom_row, textvariable=countdown_var,
        font=FONT_COUNTDOWN, fg=COLORS['muted'], bg=COLORS['bg']
    ).pack(side='left')

    def _toggle_quiet_from_dialog():
        _toggle_quiet()
        # 切换后最小化当前弹窗（让效果立刻可见）
        if _is_quiet():
            root.iconify()

    quiet_label = '🔇 静默' if not _is_quiet() else '🔊 恢复'
    quiet_fg = COLORS['muted'] if not _is_quiet() else COLORS['accent']
    tk.Button(
        bottom_row, text=quiet_label, command=_toggle_quiet_from_dialog,
        bg=COLORS['bg'], fg=quiet_fg,
        font=FONT_SANS_BOLD,
        activebackground=COLORS['bg'],
        activeforeground=COLORS['accent'],
        relief='flat', padx=8, pady=2, cursor='hand2', bd=0
    ).pack(side='right')

    # ── 按钮区 ────────────────────────────────────────────────────
    tk.Frame(root, bg=COLORS['border'], height=1).pack(fill='x', side='bottom')
    bar = tk.Frame(root, bg=COLORS['footer_bg'], padx=16, pady=12)
    bar.pack(fill='x', side='bottom')

    # ── 回调 ──────────────────────────────────────────────────────
    def _allow_once():
        decision['behavior'] = 'allow'
        root.destroy()

    def _allow_remember(sugg):
        decision['behavior'] = 'allow'
        decision['updatedPermissions'] = [sugg]
        root.destroy()

    def _deny():
        root.destroy()

    def _on_timeout():
        if not timed_out.is_set():
            timed_out.set()
            root.destroy()

    # ── 如果没有官方 suggestions，自动构造"记住"规则 ──
    if not suggestions:
        suggestions = [{
            'type': 'addRules',
            'rules': [{'toolName': tool_name}],
            'behavior': 'allow',
            'destination': 'localSettings',
        }]

    # ── 按钮（从右到左排列） ──────────────────────────────────────
    btn_deny = tk.Button(
        bar, text='🚫  拒绝', command=_deny,
        bg='#fee2e2', fg=COLORS['danger'],
        font=FONT_SANS_BOLD,
        activebackground='#fecaca', activeforeground=COLORS['danger_hover'],
        relief='flat', padx=18, pady=8, cursor='hand2', bd=0
    )
    btn_deny.pack(side='right', padx=(8, 0))

    btn_remember = tk.Button(
        bar, text='✅  同意并记住',
        command=lambda s=suggestions[0]: _allow_remember(s),
        bg=COLORS['remember'], fg='#ffffff',
        font=FONT_SANS,
        activebackground=COLORS['remember_hover'],
        activeforeground='#ffffff',
        relief='flat', padx=14, pady=8, cursor='hand2', bd=0
    )
    btn_remember.pack(side='right', padx=(0, 6))

    btn_allow = tk.Button(
        bar, text='✓  同意', command=_allow_once,
        bg=COLORS['accent'], fg='#ffffff',
        font=FONT_SANS_BOLD,
        activebackground=COLORS['accent_hover'],
        activeforeground='#ffffff',
        relief='flat', padx=22, pady=8, cursor='hand2', bd=0
    )
    btn_allow.pack(side='right', padx=(0, 8))

    # ── 键盘快捷键 ────────────────────────────────────────────────
    root.bind('<Return>',          lambda e: _allow_once())
    root.bind('<Escape>',          lambda e: _deny())
    root.bind('<Control-Return>',  lambda e: _allow_remember(suggestions[0]))

    # ── 超时计时器 ────────────────────────────────────────────────
    root.after(PERMISSION_TIMEOUT * 1000, _on_timeout)

    def _tick(remaining):
        if timed_out.is_set():
            return
        if remaining <= 10:
            countdown_var.set(f'⏱ {remaining}s 后自动拒绝  ⚠️')
        else:
            countdown_var.set(f'⏱ {remaining}s 后自动拒绝')
        if remaining > 1:
            root.after(1000, lambda: _tick(remaining - 1))

    root.after(1000, lambda: _tick(PERMISSION_TIMEOUT - 1))

    # ── 展示 ──────────────────────────────────────────────────────
    if _is_quiet():
        root.iconify()  # 静默模式：最小化到任务栏，不抢焦点
    else:
        _bring_to_front(root, btn_allow)

    # 每 12 秒重新闪烁任务栏（防止用户没注意到）
    def _reflash():
        if timed_out.is_set():
            return
        if IS_WIN:
            hwnd = _win32_get_tk_hwnd(root)
            if hwnd:
                _win32_flash_taskbar(hwnd)
        if not timed_out.is_set():
            root.after(12000, _reflash)

    root.after(12000, _reflash)
    root.mainloop()

    if timed_out.is_set():
        return {'behavior': 'deny'}
    return decision

# ═══════════════════════════════════════════════════════════════════════
# 空闲通知（轻量，6 秒自动消失）
# ═══════════════════════════════════════════════════════════════════════

def show_idle_notification(_data):
    """
    轻量空闲通知弹窗。
    6 秒后自动关闭，也可点击按钮或按 Esc/Enter 立即关闭。
    """

    import tkinter as tk

    root = tk.Tk()
    root.title('Claude Code')
    root.resizable(False, False)
    root.configure(bg=COLORS['bg'])

    _center_window(root, 400, 170)

    main = tk.Frame(root, bg=COLORS['bg'], padx=20, pady=16)
    main.pack(fill='both', expand=True)

    tk.Label(
        main, text='✅ 任务已完成，等待输入',
        font=FONT_SANS, fg=COLORS['text'], bg=COLORS['bg']
    ).pack()

    def _close():
        root.destroy()

    def _close_and_mute():
        _mute_idle()
        root.destroy()

    def _close_and_toggle_quiet():
        _toggle_quiet()
        root.destroy()

    # 操作按钮行（静默 + 屏蔽）
    toggle_row = tk.Frame(main, bg=COLORS['bg'])
    toggle_row.pack(pady=(14, 0))

    quiet_label = '🔊 静默模式' if not _is_quiet() else '🔇 取消静默'
    quiet_fg = COLORS['muted'] if not _is_quiet() else COLORS['accent']
    btn_quiet = tk.Button(
        toggle_row, text=quiet_label, command=_close_and_toggle_quiet,
        bg=COLORS['bg'], fg=quiet_fg,
        font=FONT_SANS_BOLD,
        activebackground=COLORS['bg'],
        activeforeground=COLORS['accent'],
        relief='flat', padx=10, pady=4, cursor='hand2', bd=0
    )
    btn_quiet.pack(side='left', padx=(0, 16))

    btn_mute = tk.Button(
        toggle_row, text='🔕 以后不再提醒', command=_close_and_mute,
        bg=COLORS['bg'], fg=COLORS['muted'],
        font=FONT_SANS_BOLD,
        activebackground=COLORS['bg'],
        activeforeground=COLORS['danger'],
        relief='flat', padx=10, pady=4, cursor='hand2', bd=0
    )
    btn_mute.pack(side='left')

    # 知道了按钮（独立一行，居中）
    btn_row = tk.Frame(main, bg=COLORS['bg'])
    btn_row.pack(pady=(10, 0))

    btn = tk.Button(
        btn_row, text='知道了', command=_close,
        bg=COLORS['accent'], fg='#ffffff',
        font=FONT_SANS_BOLD,
        activebackground=COLORS['accent_hover'],
        activeforeground='#ffffff',
        relief='flat', padx=30, pady=5, cursor='hand2', bd=0
    )
    btn.pack()

    root.bind('<Escape>', lambda e: _close())
    root.bind('<Return>', lambda e: _close())

    if _is_quiet():
        root.iconify()
    else:
        _bring_to_front(root, btn)

    # 6 秒后自动关闭
    root.after(IDLE_AUTO_CLOSE * 1000, _close)
    root.mainloop()

# ═══════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════

def main():
    # 1. 读取 stdin 中的事件 JSON
    try:
        raw = sys.stdin.buffer.read()
        if not raw:
            return
        data = json.loads(raw.decode())
    except Exception:
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f'[stdin-error] {traceback.format_exc()}\n')
        return

    event = data.get('hook_event_name', '')

    # 2. 前台检测：终端在前台 → 不弹窗，让 CC 原生提示处理
    if _is_terminal_foreground():
        return

    # 3. 按事件类型分发
    try:
        if event == 'PermissionRequest':
            decision = show_permission_dialog(data)
            output = {
                'hookSpecificOutput': {
                    'hookEventName': 'PermissionRequest',
                    'decision': decision,
                }
            }
            print(json.dumps(output, ensure_ascii=False))

        elif event == 'Notification':
            if not _is_idle_muted():
                show_idle_notification(data)

    except Exception:
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f'[gui-error] {traceback.format_exc()}\n')

if __name__ == '__main__':
    main()
