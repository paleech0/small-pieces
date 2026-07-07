# Claude Code Popup Notify - 一键安装脚本
# 用法：右键本文件 → 使用 PowerShell 运行

$ErrorActionPreference = "Stop"
$hookDir = "$env:USERPROFILE\.claude\hooks"
$hookFile = "$hookDir\cc-notify.py"
$settingsFile = "$env:USERPROFILE\.claude\settings.json"
$downloadUrl = "https://raw.githubusercontent.com/paleech0/small-pieces/master/cc-notify.py"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Claude Code Popup Notify 安装程序" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 创建 hooks 目录
Write-Host "[1/3] 创建 hooks 目录..." -ForegroundColor Yellow
if (-not (Test-Path $hookDir)) {
    New-Item -ItemType Directory -Path $hookDir -Force | Out-Null
    Write-Host "  ✓ 已创建 $hookDir" -ForegroundColor Green
} else {
    Write-Host "  ✓ 目录已存在" -ForegroundColor Green
}

# 2. 下载脚本
Write-Host "[2/3] 下载 cc-notify.py..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $hookFile -ErrorAction Stop
    Write-Host "  ✓ 已下载到 $hookFile" -ForegroundColor Green
} catch {
    Write-Host "  ✗ 下载失败: $_" -ForegroundColor Red
    Write-Host "  请手动下载: $downloadUrl" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# 3. 配置 settings.json
Write-Host "[3/3] 配置 hooks..." -ForegroundColor Yellow

$hookConfig = @{
    hooks = @{
        SessionStart = @(
            @{
                matcher = ""
                hooks = @(
                    @{
                        type = "command"
                        command = "cmd /c del /f `"$env:USERPROFILE\.claude\hooks\cc-notify_muted.json`" 2>nul || exit 0"
                    }
                )
            }
        )
        PermissionRequest = @(
            @{
                matcher = ""
                hooks = @(
                    @{
                        type = "command"
                        command = "python $env:USERPROFILE\.claude\hooks\cc-notify.py"
                    }
                )
            }
        )
        Notification = @(
            @{
                matcher = "idle_prompt"
                hooks = @(
                    @{
                        type = "command"
                        command = "python $env:USERPROFILE\.claude\hooks\cc-notify.py"
                    }
                )
            }
        )
    }
}

if (Test-Path $settingsFile) {
    # 已有 settings.json → 合并
    try {
        $existing = Get-Content $settingsFile -Raw | ConvertFrom-Json -ErrorAction Stop
        Write-Host "  ✓ 找到现有 settings.json，将合并 hooks 配置" -ForegroundColor Green

        # 合并 hooks
        if (-not $existing.PSObject.Properties['hooks']) {
            $existing | Add-Member -NotePropertyName 'hooks' -NotePropertyValue $hookConfig.hooks -Force
        } else {
            # 保留已有的其他事件，只更新 SessionStart / PermissionRequest / Notification
            $existing.hooks | Add-Member -NotePropertyName 'SessionStart' -NotePropertyValue $hookConfig.hooks.SessionStart -Force
            $existing.hooks | Add-Member -NotePropertyName 'PermissionRequest' -NotePropertyValue $hookConfig.hooks.PermissionRequest -Force
            $existing.hooks | Add-Member -NotePropertyName 'Notification' -NotePropertyValue $hookConfig.hooks.Notification -Force
        }

        # 备份原文件
        Copy-Item $settingsFile "$settingsFile.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Force
        Write-Host "  ✓ 已备份原配置文件" -ForegroundColor Green

        # 写入
        $existing | ConvertTo-Json -Depth 10 | Set-Content $settingsFile -Encoding UTF8
        Write-Host "  ✓ hooks 配置已合并到 $settingsFile" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ 解析现有 settings.json 失败，将创建新文件" -ForegroundColor Yellow
        $hookConfig | ConvertTo-Json -Depth 10 | Set-Content $settingsFile -Encoding UTF8
    }
} else {
    # 无 settings.json → 新建
    $hookConfig | ConvertTo-Json -Depth 10 | Set-Content $settingsFile -Encoding UTF8
    Write-Host "  ✓ 已创建 $settingsFile" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步：重启 Claude Code 让 hooks 生效。" -ForegroundColor White
Write-Host "验证方法：在 CC 中输入 /hooks 查看已加载的 hooks。" -ForegroundColor White
Write-Host ""
Read-Host "按 Enter 退出"
