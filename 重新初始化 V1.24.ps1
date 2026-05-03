$ErrorActionPreference = 'Stop'

Set-Location -LiteralPath $PSScriptRoot
$LogPath = Join-Path $PSScriptRoot 'init_log.txt'
$TracePath = Join-Path $PSScriptRoot 'init_exit_trace.txt'
$TraceBuild = 'reinit-v1.24-exit-trace-20260428-03'
$ExitTraceEnabled = ($env:CODE880_EXIT_TRACE -eq '1')
$PyprojectExit = ''
$InitExit = ''
$UvResult = ''
$TestExit = ''
$VsCodeExtensionsExit = ''
$VsCodeLaunched = 0
$FinalExit = 1
$CancelledByUser = $false
$ProjectName = ''
$SummaryItems = [ordered]@{}
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)

[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Set-SummaryItem {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][ValidateSet('PASS', 'FAIL', 'WARN')][string]$Status,
        [string]$Reason = ''
    )

    $script:SummaryItems[$Name] = [ordered]@{
        Status = $Status
        Reason = $Reason
    }
}

function Add-LogLine {
    param([string]$Line = '')

    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes($Line + [Environment]::NewLine)
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            $stream = [System.IO.File]::Open($LogPath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
            try {
                $stream.Write($bytes, 0, $bytes.Length)
            } finally {
                $stream.Dispose()
            }
            return
        } catch {
            if ($attempt -eq 10) { throw }
            Start-Sleep -Milliseconds 150
        }
    }
}

function Add-TraceLine {
    param([string]$Line = '')

    if (-not $script:ExitTraceEnabled) {
        return
    }

    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes($Line + [Environment]::NewLine)
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            $stream = [System.IO.File]::Open($TracePath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
            try {
                $stream.Write($bytes, 0, $bytes.Length)
            } finally {
                $stream.Dispose()
            }
            return
        } catch {
            if ($attempt -eq 10) { return }
            Start-Sleep -Milliseconds 100
        }
    }
}

function Write-ExitTrace {
    param([string]$Message = '')

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
    Add-TraceLine ("[{0}] {1}" -f $timestamp, $Message)
}

function Get-ProcessTraceLine {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($null -eq $process) {
            return "pid=$ProcessId <not found>"
        }
        $commandLine = ([string]$process.CommandLine) -replace '\s+', ' '
        return "pid=$($process.ProcessId) ppid=$($process.ParentProcessId) name=$($process.Name) path=$($process.ExecutablePath) cmd=$commandLine"
    } catch {
        return "pid=$ProcessId <query failed: $($_.Exception.Message)>"
    }
}

function Write-ProcessAncestryTrace {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [string]$Label = 'ancestry'
    )

    Write-ExitTrace "$Label begin process_id=$ProcessId"
    $currentPid = $ProcessId
    for ($depth = 0; $depth -lt 8 -and $currentPid -gt 0; $depth++) {
        try {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$currentPid" -ErrorAction Stop
            if ($null -eq $process) { break }
            Write-ExitTrace "$Label depth=$depth $(Get-ProcessTraceLine -ProcessId ([int]$currentPid))"
            $currentPid = [int]$process.ParentProcessId
        } catch {
            Write-ExitTrace "$Label depth=$depth pid=$currentPid query_failed=$($_.Exception.Message)"
            break
        }
    }
    Write-ExitTrace "$Label end"
}

function Write-DescendantProcessTrace {
    param(
        [int[]]$RootProcessIds,
        [string]$Label = 'descendants',
        [int]$Limit = 120
    )

    $roots = @($RootProcessIds | Where-Object { $_ -gt 0 } | Select-Object -Unique)
    Write-ExitTrace "$Label begin roots=$($roots -join ',')"
    if ($roots.Count -eq 0) {
        Write-ExitTrace "$Label no roots"
        return
    }

    try {
        $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
        $seen = @{}
        $frontier = @($roots)
        $count = 0
        while ($frontier.Count -gt 0 -and $count -lt $Limit) {
            $children = @($allProcesses | Where-Object {
                $frontier -contains [int]$_.ParentProcessId -and -not $seen.ContainsKey([string]$_.ProcessId)
            })
            if ($children.Count -eq 0) { break }
            $next = @()
            foreach ($child in $children) {
                $seen[[string]$child.ProcessId] = $true
                $commandLine = ([string]$child.CommandLine) -replace '\s+', ' '
                Write-ExitTrace "$Label child pid=$($child.ProcessId) ppid=$($child.ParentProcessId) name=$($child.Name) path=$($child.ExecutablePath) cmd=$commandLine"
                $next += [int]$child.ProcessId
                $count++
                if ($count -ge $Limit) { break }
            }
            $frontier = @($next)
        }
        Write-ExitTrace "$Label end count=$count"
    } catch {
        Write-ExitTrace "$Label query_failed=$($_.Exception.Message)"
    }
}

function Write-ConsoleProcessTrace {
    param([string]$Label = 'console processes')

    Write-ExitTrace "$Label begin"
    try {
        if (-not ('ConsoleProcessApi' -as [type])) {
            Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class ConsoleProcessApi
{
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint GetConsoleProcessList(uint[] processList, uint processCount);
}
'@
        }

        $processIds = New-Object UInt32[] 256
        $count = [ConsoleProcessApi]::GetConsoleProcessList($processIds, [uint32]$processIds.Length)
        Write-ExitTrace "$Label count=$count"
        for ($index = 0; $index -lt [Math]::Min([int]$count, $processIds.Length); $index++) {
            $consolePid = [int]$processIds[$index]
            Write-ExitTrace "$Label attached[$index] $(Get-ProcessTraceLine -ProcessId $consolePid)"
        }
    } catch {
        Write-ExitTrace "$Label query_failed=$($_.Exception.Message)"
    }
    Write-ExitTrace "$Label end"
}

function Write-StartupExitTrace {
    Write-ExitTrace "trace_build=$TraceBuild"
    Write-ExitTrace "script_path=$PSCommandPath"
    Write-ExitTrace "project_root=$PSScriptRoot"
    Write-ExitTrace "log_path=$LogPath"
    Write-ExitTrace "trace_path=$TracePath"
    Write-ExitTrace "powershell_pid=$PID host=$($Host.Name) ps_version=$($PSVersionTable.PSVersion) command_line=$([Environment]::CommandLine)"
    Write-ExitTrace "env WT_SESSION=$env:WT_SESSION TERM_PROGRAM=$env:TERM_PROGRAM VSCODE_PID=$env:VSCODE_PID COMSPEC=$env:ComSpec"
    Write-ProcessAncestryTrace -ProcessId $PID -Label 'startup ancestry'
    Write-ConsoleProcessTrace -Label 'startup console process list'
}

function Write-Log {
    param([string]$Message = '')

    Write-Host $Message
    if ($Message -eq '') {
        Add-LogLine ''
    } else {
        Add-LogLine ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    }
}

function Write-Section {
    param([string]$Name)

    Write-Log ''
    Write-Log '=================================================='
    Write-Log "========== $Name =========="
    Write-Log '=================================================='
}

function Show-InitializationConsent {
    $body = @'
请先阅读并确认以下说明。勾选同意后才会开始初始化当前项目。

【1. 本脚本会做什么】
1. 根据当前文件夹名称更新 pyproject.toml 的项目名。
2. 删除并重建当前项目的 .venv，优先使用 uv sync 同步依赖。
3. 把本项目自带的 hy127 工具库部署到 .venv。
4. 写入 .vscode/settings.json、launch.json、extensions.json。
5. 运行 Python、依赖和 GUI 初始化测试。
6. 尝试安装 VSCode Python、debugpy、Pylance 扩展，并打开 VSCode。
7. 生成 init_log.txt，便于排查问题。

【2. 重要影响】
1. 仅处理当前项目目录，不会主动删除项目外文件。
2. 会删除当前项目的 .venv；uv.lock 会尽量保留，以减少依赖版本漂移。
3. 会清理项目内 __pycache__；不会清空 .uv-cache。
4. 依赖同步和扩展安装可能访问阿里云 PyPI 镜像、pypi.org 或 VSCode 扩展市场。
5. 如果依赖配置变化，uv 可能更新 uv.lock。

【3. 安全提醒】
1. 初始化过程中不会主动上传你的代码或个人文件。
2. 请不要把 API Key、密码、Token 等敏感信息写入项目文件、日志或截图。
3. 网络代理、安全软件或公司网络策略可能影响依赖和扩展安装。

【4. 法律与许可】
1. Python、uv、VSCode、VSCode 扩展和 PyPI 包适用各自第三方许可、隐私和安全条款。
2. VSCode 和扩展市场可能包含遥测、自动更新或联网功能，具体以 Microsoft 官方条款和设置为准。
3. 本脚本仅面向个人学习、课程练习和本机项目初始化，不构成法律意见。
4. 工程“猿”工具网仅提供信息咨询来源和初始化流程指引，不提供第三方软件的所有权、授权转让、可用性或法律保证。
5. 组织、培训机构、商业分发或批量部署前，请自行复核软件许可、隐私合规和网络安全要求。

如你理解并同意以上内容，请勾选确认后继续。
'@

    $form = $null
    $titleFont = $null
    $normalFont = $null
    $headingFont = $null
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing

        $form = [System.Windows.Forms.Form]::new()
        $form.Text = '项目重新初始化 - 使用前确认'
        $form.Size = [System.Drawing.Size]::new(820, 620)
        $form.StartPosition = 'CenterScreen'
        $form.MinimizeBox = $false
        $form.MaximizeBox = $false

        $title = [System.Windows.Forms.Label]::new()
        $title.Text = '项目重新初始化说明'
        $titleFont = [System.Drawing.Font]::new('Microsoft YaHei UI', 14, [System.Drawing.FontStyle]::Bold)
        $title.Font = $titleFont
        $title.AutoSize = $true
        $title.Location = [System.Drawing.Point]::new(14, 14)
        $form.Controls.Add($title)

        $normalFont = [System.Drawing.Font]::new('Microsoft YaHei UI', 10)
        $headingFont = [System.Drawing.Font]::new('Microsoft YaHei UI', 10.5, [System.Drawing.FontStyle]::Bold)

        $richText = [System.Windows.Forms.RichTextBox]::new()
        $richText.ReadOnly = $true
        $richText.ScrollBars = 'Vertical'
        $richText.WordWrap = $true
        $richText.BorderStyle = 'FixedSingle'
        $richText.BackColor = [System.Drawing.SystemColors]::Window
        $richText.ForeColor = [System.Drawing.SystemColors]::WindowText
        $richText.Font = $normalFont
        $richText.DetectUrls = $false
        $richText.TabStop = $false
        $richText.Location = [System.Drawing.Point]::new(16, 52)
        $richText.Size = [System.Drawing.Size]::new(770, 420)

        foreach ($line in ($body -split '\r?\n')) {
            if ($line -like '【*】') {
                $richText.SelectionFont = $headingFont
                $richText.SelectionColor = [System.Drawing.Color]::FromArgb(25, 82, 140)
            } else {
                $richText.SelectionFont = $normalFont
                $richText.SelectionColor = [System.Drawing.SystemColors]::WindowText
            }
            $richText.AppendText($line + [Environment]::NewLine)
        }
        $richText.Select(0, 0)
        $form.Controls.Add($richText)

        $checkbox = [System.Windows.Forms.CheckBox]::new()
        $checkbox.Text = '我已阅读并同意上述初始化影响、安全提醒和法律许可说明'
        $checkbox.AutoSize = $true
        $checkbox.Font = $normalFont
        $checkbox.Location = [System.Drawing.Point]::new(18, 486)
        $form.Controls.Add($checkbox)

        $continueButton = [System.Windows.Forms.Button]::new()
        $continueButton.Text = '同意并继续'
        $continueButton.Size = [System.Drawing.Size]::new(110, 34)
        $continueButton.Location = [System.Drawing.Point]::new(676, 530)
        $continueButton.Add_Click({
            if (-not $checkbox.Checked) {
                [System.Windows.Forms.MessageBox]::Show($form, '继续前需要先勾选同意说明。', '请先确认', 'OK', 'Warning') | Out-Null
                return
            }
            $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
            $form.Close()
        })
        $form.Controls.Add($continueButton)

        $cancelButton = [System.Windows.Forms.Button]::new()
        $cancelButton.Text = '取消'
        $cancelButton.Size = [System.Drawing.Size]::new(90, 34)
        $cancelButton.Location = [System.Drawing.Point]::new(572, 530)
        $cancelButton.Add_Click({
            $form.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
            $form.Close()
        })
        $form.Controls.Add($cancelButton)

        $form.AcceptButton = $continueButton
        $form.CancelButton = $cancelButton
        $form.ActiveControl = $checkbox
        $dialogResult = $form.ShowDialog()
        return ($dialogResult -eq [System.Windows.Forms.DialogResult]::OK)
    } catch {
        Write-Host $body
        $answer = Read-Host '输入 YES 表示同意并继续，其他任意输入表示取消'
        return ($answer -eq 'YES')
    } finally {
        foreach ($resource in @($form, $titleFont, $normalFont, $headingFont)) {
            if ($null -ne $resource) {
                try {
                    $resource.Dispose()
                } catch {
                    # best-effort cleanup only
                }
            }
        }
    }
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = (Get-Location).Path
    )

    $oldErrorActionPreference = $ErrorActionPreference
    try {
        Push-Location -LiteralPath $WorkingDirectory
        $ErrorActionPreference = 'Continue'
        $output = & $FilePath @Arguments 2>&1
        $exitCode = if ($null -ne $global:LASTEXITCODE) { $global:LASTEXITCODE } else { 0 }
    } catch {
        $output = @($_.Exception.Message)
        $exitCode = 1
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
        Pop-Location
    }

    foreach ($line in $output) {
        Write-Host $line
        Add-LogLine ([string]$line)
    }

    return $exitCode
}

function New-ProjectName {
    param([string]$FolderName)

    if ($FolderName -match '[^\x00-\x7F]') {
        return 'code_' + (Get-Random -Minimum 1000 -Maximum 9999)
    }

    $safe = $FolderName.ToLowerInvariant() -replace '[^a-z0-9._-]', '_'
    $safe = $safe.Trim('_')
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return 'code_' + (Get-Random -Minimum 1000 -Maximum 9999)
    }

    return $safe
}

function Set-JsonProperty {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)]$Value
    )

    if ($null -eq $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    } else {
        $Object.PSObject.Properties[$Name].Value = $Value
    }
}

function Read-JsonObject {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        try {
            return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            Write-Log "[WARN] Could not parse $Path; recreating it. $($_.Exception.Message)"
        }
    }

    return [pscustomobject]@{}
}

function Write-JsonObject {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Object
    )

    $json = $Object | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, $script:Utf8NoBom)
}

function Get-VsCodeLaunchPath {
    $candidateExecutables = @()
    if (-not [string]::IsNullOrWhiteSpace($env:LocalAppData)) {
        $candidateExecutables += (Join-Path $env:LocalAppData 'Programs\Microsoft VS Code\Code.exe')
    }
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
        $candidateExecutables += (Join-Path $env:ProgramFiles 'Microsoft VS Code\Code.exe')
    }
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $candidateExecutables += (Join-Path ${env:ProgramFiles(x86)} 'Microsoft VS Code\Code.exe')
    }

    foreach ($vsCodeExe in $candidateExecutables) {
        if (Test-Path -LiteralPath $vsCodeExe) {
            return $vsCodeExe
        }
    }

    foreach ($commandName in @('code', 'code.cmd')) {
        $codeCommand = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($null -eq $codeCommand -or [string]::IsNullOrWhiteSpace($codeCommand.Source)) {
            continue
        }

        if ($codeCommand.Source -like '*.cmd' -or $codeCommand.Source -like '*.bat') {
            $binDir = Split-Path -Parent $codeCommand.Source
            $installDir = Split-Path -Parent $binDir
            $exeFromCli = Join-Path $installDir 'Code.exe'
            if (Test-Path -LiteralPath $exeFromCli) {
                return $exeFromCli
            }
        }

        return $codeCommand.Source
    }

    return $null
}

function Get-VsCodeCliPath {
    $localCodeCmd = Join-Path $env:LocalAppData 'Programs\Microsoft VS Code\bin\code.cmd'
    if (Test-Path -LiteralPath $localCodeCmd) {
        return $localCodeCmd
    }

    $codeCmd = Get-Command code.cmd -ErrorAction SilentlyContinue
    if ($null -ne $codeCmd) {
        return $codeCmd.Source
    }

    $code = Get-Command code -ErrorAction SilentlyContinue
    if ($null -ne $code -and $code.Source -notlike '*\Code.exe') {
        return $code.Source
    }

    return $null
}

function Start-DetachedVsCode {
    param(
        [Parameter(Mandatory = $true)][string]$VsCodePath,
        [Parameter(Mandatory = $true)][string]$WorkspaceRoot
    )

    $wscriptPath = Join-Path $env:WINDIR 'System32\wscript.exe'
    if (-not (Test-Path -LiteralPath $wscriptPath)) {
        throw "wscript.exe not found: $wscriptPath"
    }

    $command = ('"{0}" "{1}"' -f $VsCodePath, $WorkspaceRoot)
    $escapedCommand = $command.Replace('"', '""')
    $escapedWorkingDirectory = $WorkspaceRoot.Replace('"', '""')
    $scriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("code880_launch_vscode_{0}.vbs" -f ([guid]::NewGuid().ToString('N')))
    $scriptBody = @"
Set shell = CreateObject("WScript.Shell")
Set env = shell.Environment("PROCESS")
env("ELECTRON_NO_ATTACH_CONSOLE") = "1"
shell.CurrentDirectory = "$escapedWorkingDirectory"
shell.Run "$escapedCommand", 1, False
CreateObject("Scripting.FileSystemObject").DeleteFile WScript.ScriptFullName, True
"@

    Write-ExitTrace "vscode_launch method=wscript_bridge vscode_path=$VsCodePath workspace=$WorkspaceRoot vbs=$scriptPath command=$command"
    $unicodeWithBom = [System.Text.UnicodeEncoding]::new($false, $true)
    [System.IO.File]::WriteAllText($scriptPath, $scriptBody, $unicodeWithBom)
    $process = Start-Process -FilePath $wscriptPath `
        -ArgumentList @('//B', "`"$scriptPath`"") `
        -WindowStyle Hidden `
        -PassThru `
        -ErrorAction Stop

    Write-ExitTrace "vscode_launch wscript_pid=$($process.Id) wait=false temp_vbs_self_delete=$scriptPath"
}

function Install-VsCodeExtensions {
    param([string[]]$ExtensionIds)

    foreach ($extensionId in $ExtensionIds) {
        Write-Log "Recommended VSCode extension: $extensionId"
    }

    Write-Log 'VSCode CLI extension query/install is skipped during project re-initialization to prevent Code.exe from inheriting the launcher CMD console.'
    Write-Log 'Required extensions are written to .vscode/extensions.json; the base installer installs Python/debugpy, and VSCode can install recommendations if needed.'

    return 3
}

function Clear-ProjectPycache {
    $excludedRoots = @(
        (Join-Path $PSScriptRoot '.venv'),
        (Join-Path $PSScriptRoot '.uv-cache')
    )

    $removed = 0
    $warnings = @()
    $pycacheDirs = Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -Force -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue
    foreach ($dir in $pycacheDirs) {
        $fullName = $dir.FullName
        $isExcluded = $false
        foreach ($root in $excludedRoots) {
            if ($fullName.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
                $isExcluded = $true
                break
            }
        }
        if ($isExcluded) { continue }

        try {
            Remove-Item -LiteralPath $fullName -Recurse -Force -ErrorAction Stop
            Write-Log "Removed Python cache directory: $fullName"
            $removed += 1
        } catch {
            $warnings += "${fullName}: $($_.Exception.Message)"
            Write-Log "[WARN] Could not remove Python cache directory: $fullName - $($_.Exception.Message)"
        }
    }

    return [pscustomobject]@{
        Removed = $removed
        Warnings = $warnings
    }
}

function Ensure-VsCodeConfiguration {
    $vscodeDir = Join-Path $PSScriptRoot '.vscode'
    if (-not (Test-Path -LiteralPath $vscodeDir)) {
        New-Item -ItemType Directory -Path $vscodeDir | Out-Null
    }

    $settingsPath = Join-Path $vscodeDir 'settings.json'
    $settings = Read-JsonObject -Path $settingsPath
    Set-JsonProperty -Object $settings -Name 'python.defaultInterpreterPath' -Value '${workspaceFolder}/.venv/Scripts/python.exe'
    Set-JsonProperty -Object $settings -Name 'python.venvPath' -Value '${workspaceFolder}'
    Set-JsonProperty -Object $settings -Name 'python.terminal.activateEnvironment' -Value $true
    Set-JsonProperty -Object $settings -Name 'python.terminal.activateEnvInCurrentTerminal' -Value $true
    Write-JsonObject -Path $settingsPath -Object $settings

    $launchPath = Join-Path $vscodeDir 'launch.json'
    $launch = Read-JsonObject -Path $launchPath
    Set-JsonProperty -Object $launch -Name 'version' -Value '0.2.0'

    $currentFileDebug = [ordered]@{
        name = '当前文件 - 终端运行 (F5)'
        type = 'debugpy'
        request = 'launch'
        program = '${file}'
        console = 'integratedTerminal'
        python = '${workspaceFolder}/.venv/Scripts/python.exe'
        cwd = '${workspaceFolder}'
    }

    $mainDebug = [ordered]@{
        name = '运行主程序 src/main.py'
        type = 'debugpy'
        request = 'launch'
        program = '${workspaceFolder}/src/main.py'
        console = 'integratedTerminal'
        python = '${workspaceFolder}/.venv/Scripts/python.exe'
        cwd = '${workspaceFolder}'
    }

    $currentConsoleDebug = [ordered]@{
        name = '当前文件 - 调试控制台'
        type = 'debugpy'
        request = 'launch'
        program = '${file}'
        console = 'internalConsole'
        python = '${workspaceFolder}/.venv/Scripts/python.exe'
        cwd = '${workspaceFolder}'
        redirectOutput = $true
    }

    $remainingConfigs = @()
    foreach ($config in @($launch.configurations)) {
        if ($null -eq $config) { continue }
        if ($config.type -eq 'debugpy') { continue }
        $remainingConfigs += $config
    }
    $canonicalConfigs = @(
        $currentFileDebug,
        $mainDebug,
        $currentConsoleDebug
    )
    Set-JsonProperty -Object $launch -Name 'configurations' -Value ($canonicalConfigs + $remainingConfigs)
    Write-JsonObject -Path $launchPath -Object $launch

    $extensionsPath = Join-Path $vscodeDir 'extensions.json'
    $extensions = Read-JsonObject -Path $extensionsPath
    $requiredRecommendations = @(
        'ms-python.python',
        'ms-python.debugpy',
        'ms-python.vscode-pylance'
    )

    $recommendations = @()
    foreach ($item in @($extensions.recommendations)) {
        if ([string]::IsNullOrWhiteSpace([string]$item)) { continue }
        if ($recommendations -notcontains [string]$item) {
            $recommendations += [string]$item
        }
    }
    foreach ($item in $requiredRecommendations) {
        if ($recommendations -notcontains $item) {
            $recommendations += $item
        }
    }
    Set-JsonProperty -Object $extensions -Name 'recommendations' -Value $recommendations
    Write-JsonObject -Path $extensionsPath -Object $extensions
}

$importantItems = @(
    'Project identification',
    'Log/console encoding',
    'pyproject.toml update',
    'Environment reset',
    'Dependency sync',
    'hy127 deployment',
    'Python interpreter',
    'Environment snapshot',
    'Initialization test',
    'Project cache cleanup',
    'VSCode configuration',
    'VSCode extensions',
    'VSCode launch',
    'Overall initialization'
)
foreach ($item in $importantItems) {
    Set-SummaryItem -Name $item -Status 'FAIL' -Reason 'Not executed because initialization stopped before this step.'
}

try {
    if (-not (Show-InitializationConsent)) {
        $CancelledByUser = $true
        foreach ($item in $importantItems) {
            Set-SummaryItem -Name $item -Status 'WARN' -Reason 'Cancelled by user before initialization started.'
        }
        Set-SummaryItem -Name 'Overall initialization' -Status 'WARN' -Reason 'Cancelled by user before initialization started.'
        $FinalExit = 0
        return
    }

    [System.IO.File]::WriteAllLines($LogPath, @(
        '============================================'
        "  Initialization Log - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        '============================================'
        "Project root: $PSScriptRoot"
        "Script path: $PSCommandPath"
        "Log file: $LogPath"
        "User: $env:USERNAME"
        "PowerShell: $($PSVersionTable.PSVersion)"
        ''
    ), $Utf8NoBom)
    if ($ExitTraceEnabled) {
        Add-TraceLine ''
        Add-TraceLine '============================================'
        Add-TraceLine ("  PowerShell Exit Trace - {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'))
        Add-TraceLine '============================================'
        Write-StartupExitTrace
        Write-Log "Exit trace file: $TracePath"
    }
    Set-SummaryItem -Name 'Log/console encoding' -Status 'PASS' -Reason 'PowerShell console/output and Python IO are configured for UTF-8.'

    $originalName = Split-Path -Leaf (Get-Location).Path
    Write-Section 'PROJECT IDENTIFICATION'
    Write-Log "Original folder name: $originalName"
    $ProjectName = New-ProjectName -FolderName $originalName
    $env:PROJECT_NAME = $ProjectName
    Write-Log "Project name will be: $ProjectName"
    Set-SummaryItem -Name 'Project identification' -Status 'PASS' -Reason "Folder '$originalName' mapped to project '$ProjectName'."

    Write-Section 'PYPROJECT UPDATE'
    Write-Log '>>> BEGIN PYPROJECT UPDATE OUTPUT <<<'
    if (Test-Path -LiteralPath 'pyproject.toml') {
        try {
            $content = Get-Content -LiteralPath 'pyproject.toml' -Raw -Encoding UTF8
            $newContent = $content -replace 'name\s*=\s*".*?"', "name = `"$ProjectName`""
            $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
            [System.IO.File]::WriteAllText((Resolve-Path -LiteralPath 'pyproject.toml').Path, $newContent, $utf8NoBom)
            Write-Log 'pyproject.toml updated successfully'
            $PyprojectExit = 0
            Set-SummaryItem -Name 'pyproject.toml update' -Status 'PASS' -Reason "Project name set to '$ProjectName'."
        } catch {
            Write-Log "Error updating pyproject.toml: $($_.Exception.Message)"
            $PyprojectExit = 1
            Set-SummaryItem -Name 'pyproject.toml update' -Status 'FAIL' -Reason $_.Exception.Message
        }
    } else {
        Write-Log 'Warning: pyproject.toml not found, skipping update'
        $PyprojectExit = 0
        Set-SummaryItem -Name 'pyproject.toml update' -Status 'WARN' -Reason 'pyproject.toml not found; project metadata update skipped.'
    }
    Write-Log "<<< END PYPROJECT UPDATE OUTPUT (exit $PyprojectExit) >>>"
    if ($PyprojectExit -ne 0) { throw 'pyproject.toml update failed.' }

    Write-Section 'ENVIRONMENT RESET'
    $resetWarnings = @()
    if (Test-Path -LiteralPath 'uv.lock') {
        Write-Log 'Keeping uv.lock to preserve dependency reproducibility.'
    }
    if (Test-Path -LiteralPath '.venv') {
        try {
            Remove-Item -LiteralPath '.venv' -Recurse -Force -ErrorAction Stop
            Write-Log 'Removed .venv'
        } catch {
            Write-Log "[WARN] Could not fully remove .venv: $($_.Exception.Message)"
            Write-Log 'Continuing; uv sync will update the existing environment.'
            $resetWarnings += ".venv removal incomplete: $($_.Exception.Message)"
        }
    }
    if (-not (Test-Path -LiteralPath '.uv-cache')) { New-Item -ItemType Directory -Path '.uv-cache' | Out-Null }
    $env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.uv-cache'
    Write-Log 'Cleaned .venv; uv.lock was preserved when present.'
    if ($resetWarnings.Count -gt 0) {
        Set-SummaryItem -Name 'Environment reset' -Status 'WARN' -Reason ($resetWarnings -join '; ')
    } else {
        Set-SummaryItem -Name 'Environment reset' -Status 'PASS' -Reason '.venv reset completed, uv.lock preserved when present, and .uv-cache is ready.'
    }

    Write-Section 'DEPENDENCY SYNC'
    Write-Log 'Reinstalling dependencies (offline)...'
    Write-Log '>>> BEGIN UV ATTEMPT: OFFLINE OUTPUT <<<'
    Write-Log "Command: uv sync --offline --cache-dir $env:UV_CACHE_DIR"
    $UvResult = Invoke-LoggedCommand -FilePath 'uv' -Arguments @('sync', '--offline', '--cache-dir', $env:UV_CACHE_DIR)
    Write-Log "<<< END UV ATTEMPT: OFFLINE OUTPUT (exit $UvResult) >>>"

    if ($UvResult -ne 0) {
        Write-Log '[WARN] Offline sync failed, retrying with mirror index...'
        Write-Log '>>> BEGIN UV ATTEMPT: MIRROR OUTPUT <<<'
        Write-Log "Command: uv sync --cache-dir $env:UV_CACHE_DIR"
        $UvResult = Invoke-LoggedCommand -FilePath 'uv' -Arguments @('sync', '--cache-dir', $env:UV_CACHE_DIR)
        Write-Log "<<< END UV ATTEMPT: MIRROR OUTPUT (exit $UvResult) >>>"
    } else {
        Write-Log 'Offline sync succeeded.'
    }

    if ($UvResult -ne 0) {
        Write-Log '[WARN] Mirror sync failed, retrying with PyPI...'
        $env:UV_INDEX_URL = 'https://pypi.org/simple'
        $env:UV_EXTRA_INDEX_URL = ''
        Write-Log '>>> BEGIN UV ATTEMPT: PYPI OUTPUT <<<'
        Write-Log "Command: uv sync --cache-dir $env:UV_CACHE_DIR"
        Write-Log "Environment: UV_INDEX_URL=$env:UV_INDEX_URL"
        $UvResult = Invoke-LoggedCommand -FilePath 'uv' -Arguments @('sync', '--cache-dir', $env:UV_CACHE_DIR)
        Write-Log "<<< END UV ATTEMPT: PYPI OUTPUT (exit $UvResult) >>>"
    }

    Write-Log "uv sync final exit code: $UvResult"
    if ($UvResult -ne 0) {
        Set-SummaryItem -Name 'Dependency sync' -Status 'FAIL' -Reason "uv sync failed in all fallback modes; final exit code $UvResult."
        throw 'uv sync failed in all fallback modes.'
    }
    Set-SummaryItem -Name 'Dependency sync' -Status 'PASS' -Reason 'uv sync completed successfully.'

    Write-Section 'HY127 DEPLOYMENT'
    $hy127Init = Join-Path $PSScriptRoot '__hy127\init.bat'
    if (Test-Path -LiteralPath $hy127Init) {
        Write-Log 'Running __hy127\init.bat...'
        Write-Log '>>> BEGIN __hy127 DEPLOYMENT OUTPUT <<<'
        $InitExit = Invoke-LoggedCommand -FilePath 'cmd.exe' -Arguments @('/c', 'call init.bat 1') -WorkingDirectory (Join-Path $PSScriptRoot '__hy127')
        Write-Log '<<< END __hy127 DEPLOYMENT OUTPUT >>>'
        if ($InitExit -ne 0) {
            Write-Log "[ERROR] __hy127\init.bat failed with exit code $InitExit."
            Set-SummaryItem -Name 'hy127 deployment' -Status 'FAIL' -Reason "__hy127\init.bat failed with exit code $InitExit."
            throw '__hy127 deployment failed.'
        }
        Write-Log '__hy127 library deployed successfully'
        Write-Log "__hy127 init exit code: $InitExit"
        Set-SummaryItem -Name 'hy127 deployment' -Status 'PASS' -Reason '__hy127 copied into .venv site-packages.'
    } else {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '__hy127')) {
            Write-Log 'Warning: init.bat not found in __hy127 directory'
            Set-SummaryItem -Name 'hy127 deployment' -Status 'WARN' -Reason '__hy127 directory exists, but init.bat was not found.'
        } else {
            Write-Log 'Warning: __hy127 directory not found'
            Set-SummaryItem -Name 'hy127 deployment' -Status 'WARN' -Reason '__hy127 directory not found; local library deployment skipped.'
        }
        $InitExit = 0
    }

    Write-Section 'ENVIRONMENT SNAPSHOT'
    Add-LogLine ''
    Add-LogLine '--- Environment Info ---'
    $pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $pythonExe) {
        Write-Log 'Python interpreter: .venv\Scripts\python.exe'
        Set-SummaryItem -Name 'Python interpreter' -Status 'PASS' -Reason '.venv\Scripts\python.exe exists.'
        Write-Log '>>> BEGIN ENVIRONMENT SNAPSHOT OUTPUT <<<'
        [void](Invoke-LoggedCommand -FilePath $pythonExe -Arguments @('--version'))
        Add-LogLine 'uv version:'
        [void](Invoke-LoggedCommand -FilePath 'uv' -Arguments @('--version'))
        Add-LogLine ''
        Add-LogLine '--- Installed Packages ---'
        [void](Invoke-LoggedCommand -FilePath 'uv' -Arguments @('pip', 'list'))
        Add-LogLine ''
        Write-Log '<<< END ENVIRONMENT SNAPSHOT OUTPUT >>>'
        Set-SummaryItem -Name 'Environment snapshot' -Status 'PASS' -Reason 'Python, uv, and installed package list captured.'
    } else {
        Write-Log 'Warning: .venv\Scripts\python.exe not found'
        Set-SummaryItem -Name 'Python interpreter' -Status 'FAIL' -Reason '.venv\Scripts\python.exe not found.'
        Set-SummaryItem -Name 'Environment snapshot' -Status 'FAIL' -Reason 'Skipped because Python interpreter was missing.'
        throw '.venv\Scripts\python.exe not found after dependency sync; VSCode will not be opened because Python is unavailable.'
    }

    Write-Section 'INITIALIZATION TEST'
    if (Test-Path -LiteralPath $pythonExe) {
        Write-Log ''
        Write-Log '=================================================='
        Write-Log '========== START OF INITIALIZATION TEST =========='
        Write-Log '=================================================='
        Write-Log 'Running initialization test...'
        Write-Log '>>> BEGIN INITIALIZATION TEST OUTPUT <<<'

        $testScript = Join-Path ([System.IO.Path]::GetTempPath()) ("code880_init_test_{0}_{1}.py" -f (Get-Random), (Get-Random))
        $testCode = @'
import sys
import platform
import traceback
from importlib import metadata

results = []
failed = 0

def log(message):
    print(message, flush=True)

def check(name, fn):
    global failed
    try:
        info = fn()
        results.append("  [PASS] {}: {}".format(name, info))
    except Exception as exc:
        results.append("  [FAIL] {}: {}".format(name, exc))
        failed += 1

def package_info(dist_name, module_name=None):
    if module_name:
        __import__(module_name)
    return "{} {}".format(dist_name, metadata.version(dist_name))

log("--- Initialization Test ---")
check("Python version", lambda: platform.python_version())
check("Platform", lambda: "{} {}".format(platform.system(), platform.version()))
check("Encoding", lambda: "stdout={}, fs={}".format(sys.stdout.encoding, sys.getfilesystemencoding()))
check("pandas", lambda: __import__("pandas").__version__)
check("arrow", lambda: __import__("arrow").__version__)
check("psutil", lambda: __import__("psutil").__version__)
check("pyinstaller", lambda: __import__("PyInstaller").__version__)
check("pywin32", lambda: package_info("pywin32", "win32api") + " / win32api OK")
screeninfo_mod = __import__("screeninfo")
check("screeninfo", lambda: "{} monitor(s)".format(len(screeninfo_mod.get_monitors())))
check("ttkbootstrap", lambda: package_info("ttkbootstrap", "ttkbootstrap"))
check("hy127", lambda: str(__import__("hy127")) and "OK")
check("Chinese output", lambda: "中文输出正常")

for result in results:
    log(result)

if failed:
    log("\n[RESULT] {} test(s) FAILED".format(failed))
else:
    log("[RESULT] All {} tests PASSED".format(len(results)))

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import SUCCESS, DANGER, PRIMARY, BOTH

    lines = []
    for i in range(1, 10):
        row = ""
        for j in range(1, i + 1):
            row += "{}x{}={:<4}".format(j, i, i * j)
        lines.append(row)

    title = "All Tests PASSED" if failed == 0 else "{} Test(s) FAILED".format(failed)
    style = SUCCESS if failed == 0 else DANGER

    log("[GUI] creating test window")
    root = ttk.Window(title="Init Test", themename="cosmo", size=(520, 380))
    root.place_window_center()
    log("[GUI] window created and centered")

    ttk.Label(root, text=title, font=("", 16, "bold"), bootstyle=style).pack(pady=(15, 5))
    text = ttk.Text(root, font=("Consolas", 11), wrap="none", height=10)
    text.pack(padx=15, pady=5, fill=BOTH, expand=True)
    text.insert("1.0", "\n".join(lines))
    text.configure(state="disabled")

    btn = ttk.Button(root, text="Auto close in 1s", bootstyle=PRIMARY, command=root.destroy, width=20)
    btn.pack(pady=10)
    root.after(1000, root.destroy)
    log("[GUI] entering mainloop")
    root.mainloop()
    log("[GUI] mainloop exited")
except Exception as exc:
    log("[GUI][ERROR] failed to open or run test window: {}".format(exc))
    traceback.print_exc()

exit_code = 1 if failed > 0 else 0
log("[EXIT] initialization test exiting with code {}".format(exit_code))
sys.exit(exit_code)
'@
        [System.IO.File]::WriteAllText($testScript, $testCode, [System.Text.UTF8Encoding]::new($false))
        $TestExit = Invoke-LoggedCommand -FilePath $pythonExe -Arguments @($testScript)
        Remove-Item -LiteralPath $testScript -Force -ErrorAction SilentlyContinue
        Write-Log '<<< END INITIALIZATION TEST OUTPUT >>>'
        if ($TestExit -ne 0) {
            Write-Log '[WARN] Initialization test reported failures.'
            Set-SummaryItem -Name 'Initialization test' -Status 'FAIL' -Reason "Initialization test exited with code $TestExit; see INITIALIZATION TEST output for failed checks."
        } else {
            Write-Log 'Initialization test PASSED'
            Set-SummaryItem -Name 'Initialization test' -Status 'PASS' -Reason 'All package/import/GUI checks passed.'
        }
        Write-Log "Initialization test exit code: $TestExit"
        Write-Log '=================================================='
        Write-Log '========== END OF INITIALIZATION TEST =========='
        Write-Log '=================================================='
    } else {
        Write-Log 'Warning: .venv\Scripts\python.exe not found, skip initialization test'
        $TestExit = 0
        Set-SummaryItem -Name 'Initialization test' -Status 'FAIL' -Reason 'Skipped because Python interpreter was missing.'
    }

    Write-Log ''
    Write-Log "Project $ProjectName is OK"
    Write-Log ''

    Write-Section 'PROJECT CACHE CLEANUP'
    $cacheCleanup = Clear-ProjectPycache
    if ($cacheCleanup.Warnings.Count -gt 0) {
        Set-SummaryItem -Name 'Project cache cleanup' -Status 'WARN' -Reason "Removed $($cacheCleanup.Removed) project __pycache__ directories; some cache directories could not be removed."
    } else {
        Set-SummaryItem -Name 'Project cache cleanup' -Status 'PASS' -Reason "Removed $($cacheCleanup.Removed) project __pycache__ directories; .venv and .uv-cache were left untouched."
    }

    Write-Section 'VSCODE CONFIGURATION'
    Ensure-VsCodeConfiguration
    Write-Log 'VSCode Python interpreter and F5 launch configuration are ready.'
    Set-SummaryItem -Name 'VSCode configuration' -Status 'PASS' -Reason 'Workspace settings select .venv Python; F5 starts the selected Python file in terminal; src/main.py launch is also available.'

    Write-Section 'VSCODE EXTENSIONS'
    $requiredVsCodeExtensions = @(
        'ms-python.python',
        'ms-python.debugpy',
        'ms-python.vscode-pylance'
    )
    Write-Log '>>> BEGIN VSCODE EXTENSIONS OUTPUT <<<'
    $VsCodeExtensionsExit = Install-VsCodeExtensions -ExtensionIds $requiredVsCodeExtensions
    Write-Log "<<< END VSCODE EXTENSIONS OUTPUT (exit $VsCodeExtensionsExit) >>>"
    if ($VsCodeExtensionsExit -eq 0) {
        Set-SummaryItem -Name 'VSCode extensions' -Status 'PASS' -Reason 'Python, debugpy, and Pylance extensions are installed or already present.'
    } elseif ($VsCodeExtensionsExit -eq 3) {
        Set-SummaryItem -Name 'VSCode extensions' -Status 'PASS' -Reason 'Required extensions are listed in .vscode/extensions.json; VSCode CLI query/install was skipped to keep the launcher CMD detachable.'
    } elseif ($VsCodeExtensionsExit -eq 2) {
        Set-SummaryItem -Name 'VSCode extensions' -Status 'WARN' -Reason "VSCode CLI was not found; extensions are still listed in .vscode/extensions.json."
    } else {
        Set-SummaryItem -Name 'VSCode extensions' -Status 'WARN' -Reason 'One or more VSCode extensions failed to install; use init_log.txt to identify the failed extension.'
    }

    Write-Section 'EDITOR LAUNCH'
    $vsCodeCommandPath = Get-VsCodeLaunchPath
    if (-not [string]::IsNullOrWhiteSpace($vsCodeCommandPath)) {
        $workspaceRoot = (Get-Location).Path
        Write-Log 'Opening VSCode...'
        Write-Log "VSCode launch executable: $vsCodeCommandPath"
        Write-Log "VSCode launch workspace: $workspaceRoot"
        Write-Log "Initialization log file: $LogPath"
        try {
            $launchArgument = "`"$workspaceRoot`""
            Write-Log "VSCode launch arguments: $launchArgument"
            $powerShellProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction SilentlyContinue
            $launcherPid = if ($null -ne $powerShellProcess) { [int]$powerShellProcess.ParentProcessId } else { 0 }
            Write-ExitTrace "editor_launch before path=$vsCodeCommandPath workspace=$workspaceRoot launcher_pid=$launcherPid powershell_pid=$PID"
            Write-DescendantProcessTrace -RootProcessIds @($launcherPid, $PID) -Label 'before vscode launch descendants'
            Write-ConsoleProcessTrace -Label 'before vscode launch console process list'
            Start-DetachedVsCode -VsCodePath $vsCodeCommandPath -WorkspaceRoot $workspaceRoot
            $VsCodeLaunched = 1
            Start-Sleep -Milliseconds 800
            Write-DescendantProcessTrace -RootProcessIds @($launcherPid, $PID) -Label 'after vscode launch descendants'
            Write-ConsoleProcessTrace -Label 'after vscode launch console process list'
            Write-Log "VSCode launch requested through detached wscript bridge. Initialization details are saved to: $LogPath"
            Set-SummaryItem -Name 'VSCode launch' -Status 'PASS' -Reason "VSCode found at '$vsCodeCommandPath' and launch requested for '$workspaceRoot'."
        } catch {
            Write-ExitTrace "editor_launch failed=$($_.Exception.Message)"
            Write-Log "[WARN] VSCode launch failed: $($_.Exception.Message)"
            Set-SummaryItem -Name 'VSCode launch' -Status 'WARN' -Reason "VSCode was found at '$vsCodeCommandPath', but launch failed: $($_.Exception.Message)"
        }
    } else {
        Write-Log "Warning: VSCode CLI 'code' not found, skip opening VSCode."
        Set-SummaryItem -Name 'VSCode launch' -Status 'WARN' -Reason "VSCode executable and CLI 'code' were not found; environment initialization is unaffected."
    }

    $FinalExit = 0
} catch {
    Write-Log ''
    Write-Log "[ERROR] Re-initialization failed. $($_.Exception.Message)"
    Write-Log 'Please review init_log.txt'
    $FinalExit = 1
} finally {
    if ($CancelledByUser) {
        Set-SummaryItem -Name 'Overall initialization' -Status 'WARN' -Reason 'Cancelled by user before initialization started.'
    } elseif ($FinalExit -eq 0) {
        Set-SummaryItem -Name 'Overall initialization' -Status 'PASS' -Reason 'All blocking initialization steps completed successfully.'
    } else {
        Set-SummaryItem -Name 'Overall initialization' -Status 'FAIL' -Reason 'One or more blocking initialization steps failed; review failed items above.'
    }

    if ($CancelledByUser) {
        Write-Host 'Initialization cancelled by user before any project changes were made.'
    } else {
        Write-Section '关键事项结果总结'
        Write-Log '>>> BEGIN KEY PASS SUMMARY <<<'
        Write-Log "项目名称: $ProjectName"
        Write-Log "项目根目录: $PSScriptRoot"
        Write-Log "日志文件: $LogPath"
        Write-Log "退出码: $FinalExit"
        Write-Log "pyproject 更新退出码: $PyprojectExit"
        Write-Log "__hy127 初始化退出码: $InitExit"
        Write-Log "uv sync 退出码: $UvResult"
        Write-Log "初始化测试退出码: $TestExit"
        Write-Log "VSCode 插件安装退出码: $VsCodeExtensionsExit"
        Write-Log "VSCode 是否已请求启动: $VsCodeLaunched"
        Write-Log ''

        $passItems = @($SummaryItems.GetEnumerator() | Where-Object { $_.Value.Status -eq 'PASS' })
        $warnItems = @($SummaryItems.GetEnumerator() | Where-Object { $_.Value.Status -eq 'WARN' })
        $failedItems = @($SummaryItems.GetEnumerator() | Where-Object { $_.Value.Status -eq 'FAIL' })

        Write-Log ("关键事项统计: PASS {0} / WARN {1} / FAIL {2}" -f $passItems.Count, $warnItems.Count, $failedItems.Count)
        if ($FinalExit -eq 0) {
            if ($warnItems.Count -gt 0) {
                Write-Log '整体结论: 初始化完成，存在不阻断使用的 WARN 提醒。'
            } else {
                Write-Log '整体结论: 初始化关键事项全部 PASS。'
            }
        } else {
            Write-Log '整体结论: 初始化未完全通过，请优先处理 FAIL 项。'
        }
        Write-Log ''
        Write-Log '关键事项明细:'
        foreach ($entry in $SummaryItems.GetEnumerator()) {
            Write-Log ("[{0}] {1} - {2}" -f $entry.Value.Status, $entry.Key, $entry.Value.Reason)
        }

        Write-Log ''
        if ($passItems.Count -eq 0) {
            Write-Log 'PASS 项: 无'
        } else {
            Write-Log 'PASS 项及说明:'
            foreach ($entry in $passItems) {
                Write-Log ("- {0}: {1}" -f $entry.Key, $entry.Value.Reason)
            }
        }

        Write-Log ''
        if ($warnItems.Count -eq 0) {
            Write-Log 'WARN 项: 无'
        } else {
            Write-Log 'WARN 项及提醒:'
            foreach ($entry in $warnItems) {
                Write-Log ("- {0}: {1}" -f $entry.Key, $entry.Value.Reason)
            }
        }

        Write-Log ''
        if ($failedItems.Count -eq 0) {
            Write-Log 'FAIL 项: 无'
        } else {
            Write-Log 'FAIL 项及原因:'
            foreach ($entry in $failedItems) {
                Write-Log ("- {0}: {1}" -f $entry.Key, $entry.Value.Reason)
            }
        }
        Write-Log ''
        Write-Log "最终退出码: $FinalExit"
        Write-Log "日志已保存: $LogPath"
        Write-Log '<<< END KEY PASS SUMMARY >>>'
    }

    try {
        $powerShellProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction SilentlyContinue
        $launcherPid = if ($null -ne $powerShellProcess) { [int]$powerShellProcess.ParentProcessId } else { 0 }
        Write-ExitTrace "final_boundary before_environment_exit final_exit=$FinalExit powershell_pid=$PID launcher_pid=$launcherPid"
        Write-DescendantProcessTrace -RootProcessIds @($launcherPid, $PID) -Label 'final descendants before Environment.Exit'
        Write-ConsoleProcessTrace -Label 'final console process list before Environment.Exit'
        Write-ExitTrace 'final_boundary next_line_calls_Environment.Exit'
    } catch {
        Write-ExitTrace "final_boundary trace_failed=$($_.Exception.Message)"
    }
}

[Environment]::Exit([int]$FinalExit)
