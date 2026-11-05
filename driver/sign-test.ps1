[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$out = Join-Path $repo 'build/jx05mtu'
$package = Join-Path $out 'package'
$signtool = Join-Path $repo '.toolchain/sdk/c/bin/10.0.26100.0/x64/signtool.exe'
$inf2cat = Join-Path $repo '.toolchain/wdk/c/bin/10.0.26100.0/x86/Inf2Cat.exe'
$pfx = Join-Path $out 'signing-temp.pfx'
if (!(Test-Path -LiteralPath "$package/jx05mtu.sys") -or !(Test-Path -LiteralPath "$package/jx05mtu.inf")) {
    throw 'Run driver/build.ps1 first.'
}
if (Test-Path -LiteralPath $pfx) { throw 'A temporary signing key already exists; inspect it before continuing.' }
$rsa = [System.Security.Cryptography.RSACng]::new(3072)
$password = [Guid]::NewGuid().ToString('N')
$cert = $null
try {
    $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
        'CN=JX05 Local Driver Test', $rsa, [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $usage = [System.Security.Cryptography.OidCollection]::new()
    [void]$usage.Add([System.Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.3'))
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($usage, $true))
    $request.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
        [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature, $true))
    $cert = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5), [DateTimeOffset]::UtcNow.AddYears(1))
    [IO.File]::WriteAllBytes($pfx, $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Pfx, $password))
    [IO.File]::WriteAllBytes((Join-Path $out 'jx05-test.cer'), $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
    & $signtool sign /fd SHA256 /f $pfx /p $password "$package/jx05mtu.sys"
    if ($LASTEXITCODE) { throw 'SYS signing failed.' }
    & $inf2cat "/driver:$package" /os:10_GE_X64 /uselocaltime
    if ($LASTEXITCODE) { throw 'Catalog generation failed.' }
    & $signtool sign /fd SHA256 /f $pfx /p $password "$package/jx05mtu.cat"
    if ($LASTEXITCODE) { throw 'Catalog signing failed.' }
    Add-Type -AssemblyName System.Security
    $cms = [System.Security.Cryptography.Pkcs.SignedCms]::new()
    $cms.Decode([IO.File]::ReadAllBytes("$package/jx05mtu.cat"))
    $cms.CheckSignature($true)
    if ($cms.SignerInfos.Count -ne 1 -or $cms.SignerInfos[0].Certificate.Thumbprint -ne $cert.Thumbprint) {
        throw 'Unexpected catalog signer.'
    }
    Get-FileHash "$package/jx05mtu.sys", "$package/jx05mtu.inf", "$package/jx05mtu.cat", "$out/jx05-test.cer" |
        Select-Object Algorithm, Hash, Path | ConvertTo-Json | Set-Content "$out/hashes.json"
    Write-Output "Test-signed. Certificate: $($cert.Thumbprint). No trust store or boot settings changed."
} finally {
    if (Test-Path -LiteralPath $pfx) { Remove-Item -LiteralPath $pfx -Force }
    if ($cert) { $cert.Dispose() }
    $rsa.Dispose()
}
