# OpenHarness Desktop — Windows 打包构建经验总结

> 日期：2026-04-06
> 背景：Electron + Python (uvicorn) 桌面应用，面向 Windows 10/11 x64

---

## 1. Electron + Python spawn 的 ENOENT 问题

### 症状

```
spawn('C:\\Program Files\\Python312\\python.exe') 报错
Error: ENOENT: no such file or directory
```

### 根因

**不是"找不到文件"**，而是 **cwd 工作目录不存在**。`child_process.spawn()` 在 `cwd` 路径不存在时返回 `ENOENT`，而不是常见的路径错误。

另一个常见原因：**32-bit Electron + WOW64 重定向**，`system32` 被映射到 `SysWOW64`，导致 `cmd.exe` 也找不到。

### 解法

```javascript
// spawn 前验证 cwd 存在
ensureDirExists(hostDir, 'Host directory');

// 绝对不用 shell: true（Windows 上 Electron spawn cmd.exe 容易失败）
// 用 pythonw.exe（无窗口）而非 python.exe
const pythonBin = 'C:\\Program Files\\Python312\\pythonw.exe';

hostProcess = spawn(pythonBin, args, {
  cwd: hostDir,
  windowsHide: true,   // 隐藏控制台窗口
  stdio: 'ignore',      // 彻底断开源输出
  detached: false,
});
```

### 参考代码（main.js）

```javascript
function ensureDirExists(dirPath, label) {
  if (!fs.existsSync(dirPath)) {
    throw new Error(`${label} not found: ${dirPath}`);
  }
}

function resolvePythonBin() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  if (process.platform === 'win32') {
    const candidates = [
      'C:\\Program Files\\Python312\\pythonw.exe',
      'C:\\Program Files\\Python312\\python.exe',
      'C:\\Windows\\py.exe',
    ];
    return candidates.find(p => fs.existsSync(p)) || 'python';
  }
  return path.join(resolveHostDir(), '.venv', 'bin', 'python3');
}
```

---

## 2. electron-builder 资源配置（最容易踩的坑）

### 问题

默认 `files` 打包规则把 `apps/` 和 `vendor/` 打入 `app.asar`，但 `main.js` 运行时用 `process.resourcesPath + '/apps/host-python'` 作为 cwd——**这个路径在 asar 内根本不存在**，asar 内的路径解压后才能访问，且不是合法文件系统路径。

### 解法：`extraResources`

```yaml
# electron-builder.yml
appId: com.openharness.desktop
productName: OpenHarness Desktop
directories:
  output: dist
files:
  - main.js
  - preload.js
  - package.json
extraResources:
  - from: apps/host-python
    to: apps/host-python   # → resources/apps/host-python（不在 asar 内）
    filter:
      - '**/*'
  - from: vendor/OpenHarness
    to: vendor/OpenHarness
    filter:
      - '**/*'
win:
  target:
    - target: nsis
      arch:
        - x64
    - target: portable
      arch:
        - x64
```

运行时路径解析：
```javascript
function resolveHostDir() {
  // isPackaged() 时，process.resourcesPath 指向 app.asar 所在目录的 resources/
  // extraResources 的文件在 resources/apps/ 下，完全是真实文件系统路径
  return path.join(process.resourcesPath, 'apps', 'host-python');
}
```

---

## 3. NSIS 安装包本地构建（绕过 wine + rcedit）

### 背景

Electron Builder 的 NSIS 目标默认用 `rcedit` 写入 exe 元数据（版本信息、图标），这需要 wine32 + 32-bit Windows 执行环境。在 Linux 容器里 wine32 经常损坏或不完整：

```
wine: could not load kernel32.dll, status c0000135
rcedit-ia32.exe: Internal error
```

### 解法：直接用系统 makensis

```bash
sudo apt-get install nsis
cd /path/to/project
makensis openharness.nsi
```

### NSIS 脚本关键写法

```nsis
; openharness.nsi
Unicode True
!include "MUI2.nsh"

Name "OpenHarness Desktop"
OutFile "OpenHarness-Desktop-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\OpenHarness Desktop"
RequestExecutionLevel user

VIProductVersion "0.1.0.0"
VIAddVersionKey "ProductName" "OpenHarness Desktop"
VIAddVersionKey "CompanyName" "OpenHarness"
VIAddVersionKey "FileVersion" "0.1.0"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Section "install"
    SetOutPath "$INSTDIR"
    File /r "dist\win-unpacked\*.*"

    WriteRegStr HKCU "Software\OpenHarness Desktop" "InstallDir" "$INSTDIR"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; 桌面快捷方式
    CreateShortCut "$DESKTOP\OpenHarness Desktop.lnk" `
        "$INSTDIR\OpenHarness Desktop.exe" "" "$INSTDIR\OpenHarness Desktop.exe" 0

    ; 开始菜单
    CreateDirectory "$SMPROGRAMS\OpenHarness Desktop"
    CreateShortCut "$SMPROGRAMS\OpenHarness Desktop\OpenHarness Desktop.lnk" `
        "$INSTDIR\OpenHarness Desktop.exe" "" "$INSTDIR\OpenHarness Desktop.exe" 0
    CreateShortCut "$SMPROGRAMS\OpenHarness Desktop\Uninstall.lnk" `
        "$INSTDIR\Uninstall.exe" "" "$INSTDIR\Uninstall.exe" 0

    ExecWait '"$INSTDIR\OpenHarness Desktop.exe" --disable-gpu'
SectionEnd

Section "uninstall"
    ExecWait 'taskkill /F /IM "OpenHarness Desktop.exe" 2>nul'
    ExecWait 'taskkill /F /IM "python.exe" 2>nul'
    ExecWait 'taskkill /F /IM "pythonw.exe" 2>nul'
    RMDir /r "$INSTDIR"
    Delete "$DESKTOP\OpenHarness Desktop.lnk"
    RMDir /r "$SMPROGRAMS\OpenHarness Desktop"
    DeleteRegKey HKCU "Software\OpenHarness Desktop"
SectionEnd
```

**注意**：`LICENSE.txt` 文件必须存在于 makensis 执行目录下。

---

## 4. Windows 文件传输（tar + scp > rsync）

Windows 服务器通常没有 `rsync`，也没有标准 `tar` 命令。最佳方式：

### Linux → Windows

```bash
# Linux 端打包
tar czf /tmp/win-unpacked.tar.gz -C dist win-unpacked

# SCP 传到 Windows
scp /tmp/win-unpacked.tar.gz administrator@WIN_IP:C:/Temp/win-unpacked.tar.gz
```

### Windows 端解压

```powershell
# PowerShell 内置（Win 10 1803+）
Expand-Archive -Path 'C:\Temp\win-unpacked.tar.gz' -DestinationPath 'C:\Temp' -Force

# 或用 tar（PowerShell 7+）
tar -xzf 'C:\Temp\win-unpacked.tar.gz' -C 'C:\Target\Directory'
```

### 常用检查命令

```powershell
# 检查目录内容
Get-ChildItem 'C:\path\to\resources' | Select-Object Name

# 检查端口监听
netstat -ano | Select-String ":8789.*LISTENING"

# 检查进程
Get-Process | Where-Object { $_.Name -match 'OpenHarness|python' }
```

---

## 5. PowerShell 在 SSH 里的变量转义

PowerShell 的 `$var` 在 SSH 双引号里会被**本地** shell 解释，造成报错。

### 错误写法

```bash
# $env:TEMP 被本地 shell 解释为空
ssh admin@server "powershell -Command \"Get-Content $env:TEMP\\log.txt\""
```

### 正确写法（用 -File 执行脚本文件）

```bash
# 准备脚本文件
cat > /tmp/debug.ps1 <<'EOF'
$errLog = "$env:TEMP\oh_err.log"
$P = Start-Process -FilePath "C:\path\to\app.exe" -RedirectStandardError $errLog -PassThru
Start-Sleep 5
if (Test-Path $errLog) { Get-Content $errLog | Select-Object -First 15 }
if (-not $P.HasExited) {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8789/api/health" -TimeoutSec 5
    Write-Host "OK:" $h.service
}
EOF

# 上传并执行
scp /tmp/debug.ps1 admin@server:C:/Temp/debug.ps1
ssh admin@server "powershell -ExecutionPolicy Bypass -File C:\Temp\debug.ps1"
```

---

## 6. Windows 单例锁（Singleton Lock）与多进程清理

Electron 默认有单例锁机制（`app.requestSingleInstanceLock()`），但异常退出时 Lock 文件残留会导致后续启动直接退出（Error code 32）。

### 清理单例锁

```powershell
# 启动前删除锁文件
Remove-Item -Path "$env:LOCALAPPDATA\openharness-desktop\SingletonLock" -Force -ErrorAction SilentlyContinue

# 或删除整个 Singleton* 文件
Remove-Item -Path "$env:LOCALAPPDATA\Programs\OpenHarness Desktop\SingletonLock" -Force -ErrorAction SilentlyContinue
```

### 进程杀不干净的处理

taskkill 可能一次杀不干净（进程重启或子进程），需要：
1. 先 `tasklist` 确认进程 ID
2. 循环 `taskkill /f /PID xxx` 逐个击破
3. 或用 PowerShell 的 `Get-Process | Stop-Process -Force`

```powershell
# 完整清理脚本
$procNames = @("OpenHarness Desktop", "python", "pythonw")
foreach ($name in $procNames) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
Start-Sleep 1
# 再杀一次确保干净
Get-Process | Where-Object { $_.Name -match "OpenHarness|python" } | Stop-Process -Force
```

---

## 7. Python 后端窗口控制

| 场景 | 用什么 | 原因 |
|------|--------|------|
| 需要看到输出调试 | `python.exe` | 标准窗口 |
| 正式发布 / 无黑框 | `pythonw.exe` | 完全无窗口 |
| Electron spawn 后台进程 | `pythonw.exe` | 配合 `windowsHide: true` |

---

## 8. 验证三板斧

判断应用是否真正跑起来，依次检查：

```powershell
# 1. 进程存在
Get-Process | Where-Object { $_.Name -match 'OpenHarness|python' }

# 2. 端口监听
netstat -ano | Select-String ":8789.*LISTENING"

# 3. Health API
Invoke-RestMethod -Uri "http://127.0.0.1:8789/api/health" -TimeoutSec 5
```

成功响应示例：
```json
{"service":"openharness-desktop-host","version":"0.3.0","protocol":"http+websocket","protocol_version":"1","active_sessions":0}
```

---

## 9. 已知限制与备选方案

- **无 wine / wine32 损坏**：改用 `makensis` 本地打包，不依赖 electron-builder 的 NSIS + rcedit 链
- **Windows Server 无显示器**：截图用 `CopyFromScreen` 会报错，用 DevTools 协议（`--remote-debugging-port=9222`）验证页面是否加载
- **NSIS 静默安装参数**：使用 `/S`（大写），不要用 `/s`
- **安装路径含空格**：NSIS `InstallDir` 用 `"$LOCALAPPDATA\Programs\My App"` 格式即可，WSH CreateShortcut 自动处理

---

## 10. 快速参考

```bash
# 构建便携版（Linux）
cd ~/dev/openharness-desktop-electron
npm install
npx electron-builder --win portable --x64 --dir --config electron-builder.yml

# 构建 NSIS 安装包（Linux）
tar czf /tmp/win-unpacked.tar.gz -C dist win-unpacked
scp /tmp/win-unpacked.tar.gz admin@WIN_IP:C:/Temp/
# Windows 上执行 makensis...

# 传到 Windows 后解压
ssh admin@WIN_IP "powershell -Command Expand-Archive -Path C:\Temp\win-unpacked.tar.gz -DestinationPath C:\Temp -Force"

# Windows 一键安装 + 启动
scp install_v3.ps1 admin@WIN_IP:C:/Temp/
ssh admin@WIN_IP "powershell -ExecutionPolicy Bypass -File C:\Temp\install_v3.ps1"
```
