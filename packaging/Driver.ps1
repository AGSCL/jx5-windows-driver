[CmdletBinding(SupportsShouldProcess)]
param([switch]$Install)
$ErrorActionPreference = 'Stop'
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -or [Environment]::OSVersion.Version.Build -lt 22000) { throw 'Se requiere Windows 11 x64.' }
$expectedHardware = 'USB\VID_13D3&PID_3567&REV_0100&MI_00'
$devices = @(Get-PnpDevice -Class Bluetooth -PresentOnly | Where-Object {
    $ids = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_HardwareIds -ErrorAction SilentlyContinue).Data
    $ids -contains $expectedHardware
})
if ($devices.Count -ne 1) { throw 'Este controlador solo admite el adaptador USB 13D3:3567 rev0100 MI00 probado. No se instala en otro hardware.' }
$ring = @(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like '*B7FC01C6F37E*' })
if (-not $ring.Count) { throw 'Empareja primero el anillo B7:FC:01:C6:F3:7E. Este piloto no admite otro anillo.' }
$manifest = Get-Content (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
foreach ($name in @('jx05mtu.sys','jx05mtu.inf','jx05mtu.cat','jx05-test.cer')) {
    $relative = 'driver/' + $name
    if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $relative)).Hash -ne $manifest.files.$relative) { throw "Archivo de controlador alterado: $name" }
}
$service = Get-Service Jx05Mtu -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq 'Running') {
    $loaded = Get-CimInstance Win32_SystemDriver -Filter "Name='Jx05Mtu'"
    $binary = $loaded.PathName -replace '^\\SystemRoot', $env:WINDIR
    if ((Get-FileHash -LiteralPath $binary).Hash -ne $manifest.files.'driver/jx05mtu.sys') { throw 'Hay otra version de Jx05Mtu en uso. Requiere revision antes de actualizar.' }
    Write-Output 'Jx05Mtu ya esta en ejecucion. No se reinstala ni se reinicia el adaptador.'
    return
}
Write-Output 'Hardware compatible con el piloto. El controlador requiere firma de prueba ya habilitada y puede requerir reinicio/reemparejar solo JX-05.'
if (-not $Install) { return }
$identity = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Para instalar el controlador, ejecuta Instalar-controlador.cmd como administrador.'
}
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Jx05CodeIntegrity {
    [StructLayout(LayoutKind.Sequential)] public struct Info { public uint Length; public uint Options; }
    [DllImport("ntdll.dll")] static extern int NtQuerySystemInformation(int type, ref Info info, int size, out int returned);
    public static bool TestMode() { var info = new Info { Length = 8 }; int count; int hr = NtQuerySystemInformation(103, ref info, 8, out count); if (hr != 0) throw new InvalidOperationException("No se pudo consultar Code Integrity"); return (info.Options & 2) != 0; }
}
'@
if (-not [Jx05CodeIntegrity]::TestMode()) {
    throw 'Windows no esta en modo de prueba. Este instalador no cambia Secure Boot, BitLocker ni el arranque. Para distribucion normal falta firma Microsoft.'
}
$cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new((Join-Path $PSScriptRoot 'driver/jx05-test.cer'))
if ($cert.Thumbprint -ne '515214F5FB0AA25C02FC5BD484303F722EC10B35') { throw 'Certificado de piloto inesperado.' }
if (-not $PSCmdlet.ShouldProcess($devices[0].InstanceId, 'Confiar en certificado de prueba JX05 e instalar filtro USB experimental')) { return }
if ((Read-Host 'Se agregara un certificado de prueba y un filtro al adaptador Bluetooth. Escribe INSTALAR para continuar') -cne 'INSTALAR') { return }
Import-Certificate -FilePath (Join-Path $PSScriptRoot 'driver/jx05-test.cer') -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
Import-Certificate -FilePath (Join-Path $PSScriptRoot 'driver/jx05-test.cer') -CertStoreLocation Cert:\LocalMachine\TrustedPublisher | Out-Null
& "$env:WINDIR\System32\pnputil.exe" /add-driver (Join-Path $PSScriptRoot 'driver/jx05mtu.inf') /install
if ($LASTEXITCODE -notin @(0,3010)) { throw "PnPUtil fallo: $LASTEXITCODE" }
Write-Output 'Revisa el resultado de PnPUtil. Si solicita reiniciar, guarda el trabajo y reinicia manualmente. No se ha reiniciado Windows.'
