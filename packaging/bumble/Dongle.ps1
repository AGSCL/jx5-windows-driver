# Comprueba que el TP-Link UB500 (USB 2357:0604) use WinUSB. Con -Prepare abre Zadig (administrador).
[CmdletBinding()]
param([switch]$Prepare)
$ErrorActionPreference = 'Stop'

function Get-DongleService {
    $dongle = @(Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_2357&PID_0604\*')
    if (-not $dongle.Count) { throw 'Conecta el dongle TP-Link UB500 (USB 2357:0604) y vuelve a intentarlo.' }
    (Get-PnpDeviceProperty -InstanceId $dongle[0].InstanceId -KeyName DEVPKEY_Device_Service).Data
}

$service = Get-DongleService
if ($service -eq 'WinUSB') { Write-Output 'OK: el UB500 usa WinUSB; JX05 puede usarlo.'; return }
if (-not $Prepare) {
    Write-Warning "El UB500 usa '$service', no WinUSB. Ejecuta Preparar-dongle.cmd (una vez por PC; pide administrador)."
    return
}
$zadig = Join-Path $PSScriptRoot 'zadig.exe'
$signature = Get-AuthenticodeSignature -LiteralPath $zadig
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Akeo Consulting*') {
    throw 'zadig.exe no tiene una firma valida de Akeo Consulting; no se ejecuta.'
}
Write-Output @'
Se abrira Zadig y Windows pedira permiso de administrador. En Zadig:
  1. Options > List All Devices.
  2. Elige el dispositivo con USB ID 2357 0604 (suele llamarse "Bluetooth Radio" o "UB500").
     Comprueba el USB ID: NO elijas el Bluetooth interno del PC.
  3. A la derecha de la flecha verde deja WinUSB y pulsa "Replace Driver" (o "Install Driver").
  4. Cuando diga que termino, cierra Zadig.
'@
Start-Process -FilePath $zadig -Wait
Start-Sleep -Seconds 2  # Windows vuelve a enumerar el dongle tras cambiar el controlador
$service = Get-DongleService
if ($service -ne 'WinUSB') { throw "El UB500 sigue usando '$service'. Repite el paso en Zadig con el USB ID 2357 0604." }
Write-Output 'OK: el UB500 usa WinUSB. Ya puedes iniciar JX05.'
