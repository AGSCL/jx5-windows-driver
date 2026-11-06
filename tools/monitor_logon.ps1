# Preparar con -WhatIf; registrar solo tras confirmar el inicio automatico.
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidateSet('Install', 'Uninstall')][string]$Action,
    [string]$Pythonw = 'C:\ProgramData\anaconda3\pythonw.exe',
    [string]$Application,
    [switch]$EnableControls
)
$ErrorActionPreference = 'Stop'
$taskName = 'JX05 Monitor'
$monitorRoot = Split-Path -Parent $PSScriptRoot
$monitorScript = Join-Path $PSScriptRoot 'monitor_jx05.py'

if ($Action -eq 'Uninstall') {
    if ($PSCmdlet.ShouldProcess($taskName, 'Quitar inicio automatico (conserva registros)')) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    }
    return
}

if ($Application) {
    $executable = (Resolve-Path -LiteralPath $Application).Path
    $monitorRoot = Split-Path -Parent $executable
    $arguments = '--run'
} else {
    $executable = (Resolve-Path -LiteralPath $Pythonw).Path
    if ([IO.Path]::GetFileName($executable) -ine 'pythonw.exe') {
        throw 'Usa pythonw.exe para ejecutar sin ventana.'
    }
    $arguments = '"' + $monitorScript + '" --run'
}
if ($EnableControls) { $arguments += ' --enabled' }
$monitorUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($PSCmdlet.ShouldProcess($taskName, "Registrar inicio automatico; controles=$EnableControls")) {
    $taskAction = New-ScheduledTaskAction -Execute $executable -Argument $arguments -WorkingDirectory $monitorRoot -ErrorAction Stop
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $monitorUser -ErrorAction Stop
    $principal = New-ScheduledTaskPrincipal -UserId $monitorUser -LogonType Interactive -RunLevel Limited -ErrorAction Stop
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ErrorAction Stop
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop
}
