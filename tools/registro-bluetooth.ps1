param([int]$Segundos = 120, [string]$Nombre = 'JX-05')
$ErrorActionPreference = 'Continue'
$archivo = Join-Path (Get-Location) ('jx05-log-{0}.txt' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
function Escribir($texto) { $linea = '{0:yyyy-MM-dd HH:mm:ss.fff zzz} {1}' -f (Get-Date), $texto; Write-Host $linea; Add-Content -LiteralPath $archivo -Value $linea -Encoding UTF8 }
Escribir "Inicio. Duración: $Segundos segundos. Filtro de dispositivos: $Nombre"
Escribir 'El registro puede contener nombres e identificadores de dispositivos: revísalo antes de compartirlo.'
$canales = @('System', 'Microsoft-Windows-Bluetooth-BthLEEnum/Operational', 'Microsoft-Windows-Bluetooth-BTHUSB/Operational', 'Microsoft-Windows-DeviceSetupManager/Admin', 'Microsoft-Windows-Kernel-PnP/Configuration')
$activos = @()
foreach ($canal in $canales) {
    try { $info = Get-WinEvent -ListLog $canal -ErrorAction Stop; if ($info.IsEnabled) { $activos += $canal; Escribir "Canal disponible: $canal" } else { Escribir "Canal desactivado: $canal" } } catch { Escribir "Canal no disponible o sin acceso: $canal" }
}
Escribir 'Intentando consultar dispositivos presentes. Ahora intenta conectar el anillo.'
$inicio = Get-Date
$desde = $inicio.AddSeconds(-2)
$ultimoEstado = ''
while ((Get-Date) -lt $inicio.AddSeconds($Segundos)) {
    foreach ($canal in $activos) {
        try {
            $eventos = @(Get-WinEvent -FilterHashtable @{LogName=$canal; StartTime=$desde} -ErrorAction Stop | Where-Object { $_.TimeCreated -ge $desde } | Sort-Object TimeCreated, RecordId)
            foreach ($evento in $eventos) {
                if ($canal -eq 'System' -and $evento.ProviderName -notmatch 'Bluetooth|BTH|Kernel-PnP|UserPnp|DeviceSetupManager') { continue }
                $mensaje = $evento.Message -replace '[\r\n]+', ' '
                Escribir ("EVENTO fecha={0:o} canal={1} proveedor={2} id={3} nivel={4} mensaje={5}" -f $evento.TimeCreated, $canal, $evento.ProviderName, $evento.Id, $evento.LevelDisplayName, $mensaje)
            }
        } catch { if ($_.FullyQualifiedErrorId -notmatch 'NoMatchingEventsFound') { Escribir "Error leyendo ${canal}: $($_.Exception.Message)" } }
    }
    $desde = Get-Date
    try {
        $estado = (Get-PnpDevice -ErrorAction Stop | Where-Object { $_.FriendlyName -like "*$Nombre*" } | Sort-Object InstanceId | ForEach-Object { "nombre=$($_.FriendlyName) estado=$($_.Status) clase=$($_.Class) id=$($_.InstanceId)" }) -join ' | '
        if (-not $estado) { $estado = 'Sin dispositivos con ese nombre' }
        if ($estado -ne $ultimoEstado) { Escribir "PNP $estado"; $ultimoEstado = $estado }
    } catch { Escribir "Error consultando dispositivos: $($_.Exception.Message)" }
    Start-Sleep -Seconds 2
}
Escribir "Fin. Archivo: $archivo"
