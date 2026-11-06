[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
$destination = Join-Path $env:LOCALAPPDATA 'Programs\JX05'
$data = Join-Path $env:LOCALAPPDATA 'JX05'
$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'JX05'
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'Este paquete requiere Windows x64; ARM64 no esta validado.'
}
if ([Environment]::OSVersion.Version.Build -lt 22000) { throw 'Se requiere Windows 11.' }
$manifest = Get-Content (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $manifest.files.PSObject.Properties) {
    $path = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $entry.Name))
    if (-not $path.StartsWith($PSScriptRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Ruta de paquete invalida' }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $entry.Value) { throw "Archivo alterado: $($entry.Name)" }
}
if (Test-Path $destination) {
    if (-not (Test-Path (Join-Path $destination 'manifest.json'))) { throw 'La carpeta destino no es una instalacion JX05.' }
    $links = @(Get-Item -LiteralPath $destination) + @(Get-ChildItem -LiteralPath $destination -Recurse -Force)
    if ($links | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'No se admiten enlaces en la instalacion.' }
}
if (-not $PSCmdlet.ShouldProcess($destination, 'Instalar JX05 y activar al iniciar sesion')) { return }

# Stop only the installed monitor; never terminate a process by a stale PID.
if (Test-Path (Join-Path $destination 'JX05.exe')) {
    & (Join-Path $destination 'JX05.exe') --stop
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $task = Get-ScheduledTask -TaskName 'JX05 Monitor' -ErrorAction SilentlyContinue
        if (-not $task -or $task.State -ne 'Running') { break }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)
    if ($task -and $task.State -eq 'Running') { throw 'El monitor no termino; se conserva la instalacion anterior.' }
}
New-Item -ItemType Directory -Force $destination, $data, $menu | Out-Null
foreach ($entry in $manifest.files.PSObject.Properties) {
    $target = Join-Path $destination $entry.Name
    New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $entry.Name) -Destination $target -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Destination $destination -Force
if (-not (Test-Path (Join-Path $data 'buttons.json'))) {
    @{upper='previous';lower='next';left='previous';right='next';center='present'} |
        ConvertTo-Json | Set-Content (Join-Path $data 'buttons.json') -Encoding ASCII
}
& (Join-Path $destination 'runtime/python.exe') -B (Join-Path $destination 'tools/monitor_jx05.py') --self-test
if ($LASTEXITCODE) { throw 'La aplicacion no supero su comprobacion inicial.' }
$exe = Join-Path $destination 'JX05.exe'
& (Join-Path $destination 'tools/monitor_logon.ps1') -Action Install -Application $exe -EnableControls
$shell = New-Object -ComObject WScript.Shell
foreach ($item in @(@('JX05 - Iniciar', '--run --enabled'), @('JX05 - Activar', '--presenter-on'),
                    @('JX05 - Pausar', '--presenter-off'), @('JX05 - Estado', '--show-status'), @('JX05 - Botones', '--map'))) {
    $shortcut = $shell.CreateShortcut((Join-Path $menu ($item[0] + '.lnk')))
    $shortcut.TargetPath = $exe
    $shortcut.Arguments = $item[1]
    $shortcut.WorkingDirectory = $destination
    $shortcut.Save()
}
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\JX05'
New-Item -Path $key -Force | Out-Null
New-ItemProperty $key -Name DisplayName -Value 'JX05 Presenter (piloto)' -Force | Out-Null
New-ItemProperty $key -Name DisplayVersion -Value $manifest.version -Force | Out-Null
New-ItemProperty $key -Name InstallLocation -Value $destination -Force | Out-Null
$uninstall = '"' + (Join-Path $PSHOME 'powershell.exe') + '" -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $destination 'Uninstall.ps1') + '"'
New-ItemProperty $key -Name UninstallString -Value $uninstall -Force | Out-Null
Start-ScheduledTask -TaskName 'JX05 Monitor'
Write-Output "Aplicacion instalada en $destination. Datos en $data."
Write-Output 'El controlador se comprueba/instala aparte con Instalar-controlador.cmd; no se modifica seguridad ni se reinicia Windows.'
