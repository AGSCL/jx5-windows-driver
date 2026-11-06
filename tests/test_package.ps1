param([Parameter(Mandatory)][string]$PackagePath)
$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath $PackagePath).Path
foreach ($script in @('Install.ps1','Uninstall.ps1','Driver.ps1','tools/monitor_logon.ps1')) {
    $tokens = $null; $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $package $script), [ref]$tokens, [ref]$errors)
    if ($errors) { throw "$script : $errors" }
}
& (Join-Path $package 'Install.ps1') -WhatIf
$exe = Join-Path $package 'JX05.exe'
$original = [IO.File]::ReadAllBytes($exe)
try {
    [IO.File]::WriteAllBytes($exe, [byte[]]@(0,1,2))
    $rejected = $false
    try { & (Join-Path $package 'Install.ps1') -WhatIf }
    catch { if ($_.Exception.Message -like 'Archivo alterado:*') { $rejected = $true } else { throw } }
    if (-not $rejected) { throw 'El instalador acepto un binario alterado.' }
} finally { [IO.File]::WriteAllBytes($exe, $original) }
function Get-PnpDevice { param($Class, [switch]$PresentOnly) return @() }
try {
    & (Join-Path $package 'Driver.ps1') -Install -WhatIf
    throw 'Se acepto hardware no compatible.'
} catch {
    if ($_.Exception.Message -notlike 'Este controlador solo admite*') { throw }
}
Write-Output 'OK: scripts validos, WhatIf sin cambios, binario alterado y hardware desconocido rechazados.'
