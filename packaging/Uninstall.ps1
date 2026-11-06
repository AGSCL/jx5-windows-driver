[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
$destination = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\JX05'))
$menu = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('Programs')) 'JX05'))
if ([IO.Path]::GetFullPath($PSScriptRoot) -ne $destination -or -not (Test-Path (Join-Path $destination 'manifest.json'))) {
    throw 'Ejecuta el desinstalador desde la instalacion JX05.'
}
foreach ($path in @($destination, $menu)) {
    if (Test-Path -LiteralPath $path) {
        $entries = @(Get-Item -LiteralPath $path) + @(Get-ChildItem -LiteralPath $path -Recurse -Force)
        if ($entries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'No se eliminan carpetas con enlaces.' }
    }
}
if (-not $PSCmdlet.ShouldProcess($destination, 'Quitar aplicacion e inicio automatico; conservar datos y controlador')) { return }
& (Join-Path $destination 'JX05.exe') --stop
$deadline = (Get-Date).AddSeconds(10)
do {
    $task = Get-ScheduledTask -TaskName 'JX05 Monitor' -ErrorAction SilentlyContinue
    if (-not $task -or $task.State -ne 'Running') { break }
    Start-Sleep -Milliseconds 200
} while ((Get-Date) -lt $deadline)
if ($task -and $task.State -eq 'Running') { throw 'El monitor no termino; no se borraron archivos.' }
if ($task) { & (Join-Path $destination 'tools/monitor_logon.ps1') -Action Uninstall }
if (Test-Path -LiteralPath $menu) { Remove-Item -LiteralPath $menu -Recurse -Force }
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JX05' -Recurse -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $destination -Recurse -Force
Write-Output 'Aplicacion eliminada. Se conservan configuracion, registros y controlador; consulta la guia del controlador para retirarlo.'
