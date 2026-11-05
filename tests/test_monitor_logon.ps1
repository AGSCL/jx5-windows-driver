# Simula el Programador de tareas: nunca registra ni elimina tareas reales.
$ErrorActionPreference = 'Stop'
$monitorCalls = [Collections.Generic.List[string]]::new()
function New-ScheduledTaskAction { param($Execute, $Argument, $WorkingDirectory, $ErrorAction)
    if ($Execute -notlike '*pythonw.exe' -or $Argument -notmatch '^".+monitor_jx05.py" --run$' -or -not (Test-Path $WorkingDirectory)) { throw 'Accion incorrecta' }
    $monitorCalls.Add('action'); return 'action'
}
function New-ScheduledTaskTrigger { param([switch]$AtLogOn, $User, $ErrorAction)
    if (-not $AtLogOn -or -not $User) { throw 'Trigger incorrecto' }
    return 'trigger'
}
function New-ScheduledTaskPrincipal { param($UserId, $LogonType, $RunLevel, $ErrorAction)
    if (-not $UserId -or $LogonType -ne 'Interactive' -or $RunLevel -ne 'Limited') { throw 'Principal incorrecto' }
    return 'principal'
}
function New-ScheduledTaskSettingsSet { param($ExecutionTimeLimit, $MultipleInstances, [switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries, $ErrorAction)
    if ($ExecutionTimeLimit -ne [TimeSpan]::Zero -or $MultipleInstances -ne 'IgnoreNew') { throw 'Settings incorrectos' }
    return 'settings'
}
function Register-ScheduledTask { param($TaskName, $Action, $Trigger, $Principal, $Settings, $ErrorAction)
    if ($TaskName -ne 'JX05 Monitor' -or $Action -ne 'action' -or $Trigger -ne 'trigger' -or $Principal -ne 'principal' -or $Settings -ne 'settings') { throw 'Registro incorrecto' }
    $monitorCalls.Add('install')
}
function Unregister-ScheduledTask { param($TaskName, [switch]$Confirm, $ErrorAction)
    if ($TaskName -ne 'JX05 Monitor' -or $Confirm) { throw 'Desinstalacion incorrecta' }
    $monitorCalls.Add('uninstall')
}
$entry = Join-Path (Split-Path -Parent $PSScriptRoot) 'tools/monitor_logon.ps1'
& $entry -Action Install -WhatIf
& $entry -Action Uninstall -WhatIf
if ($monitorCalls.Count) { throw 'WhatIf ejecuto operaciones' }
& $entry -Action Install
& $entry -Action Uninstall
if (($monitorCalls -join ',') -ne 'action,install,uninstall') { throw 'Flujo incorrecto' }
Write-Output 'OK: inicio y desinstalacion simulados; WhatIf sin operaciones'
