$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$version = '0.2.0'
$runtimeZip = Join-Path $repo '.toolchain/python-3.15.2-embed-amd64.zip'
if ((Get-FileHash $runtimeZip).Hash -ne 'D012F3AA29CF07436DAE8AEA1FEC0FD195C2612A0B059B1F915AE0AFB9AD1F62') {
    throw 'Falta el runtime oficial verificado. Consulta packaging/LEEME.txt.'
}
$out = Join-Path $repo ('build/JX05-' + $version + '-win-x64-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory $out | Out-Null
New-Item -ItemType Directory (Join-Path $out 'runtime'), (Join-Path $out 'tools'), (Join-Path $out 'build/context'), (Join-Path $out 'driver') | Out-Null
Expand-Archive -LiteralPath $runtimeZip -DestinationPath (Join-Path $out 'runtime')
@('python315.zip', '.', '../tools') | Set-Content (Join-Path $out 'runtime/python315._pth') -Encoding ASCII
foreach ($name in @('capture_raw_hid.py','context_jx05.py','jx05_gestures.py','map_jx05.py','monitor_jx05.py','paths_jx05.py','monitor_logon.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $out 'tools')
}
Copy-Item -LiteralPath (Join-Path $repo 'build/context/jx05_context.dll') -Destination (Join-Path $out 'build/context')
foreach ($entry in (Get-Content (Join-Path $repo 'build/jx05mtu/hashes.json') -Raw | ConvertFrom-Json)) {
    $name = Split-Path $entry.Path -Leaf
    $source = if ($name -eq 'jx05-test.cer') { Join-Path $repo "build/jx05mtu/$name" } else { Join-Path $repo "build/jx05mtu/package/$name" }
    if ((Get-FileHash $source).Hash -ne $entry.Hash) { throw "El paquete firmado cambio: $name" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $out 'driver')
}
Copy-Item (Join-Path $repo 'packaging/*') -Destination $out
$vc = Join-Path $repo '.toolchain/vs/VC/Tools/MSVC/14.44.35207'
$sdk = Join-Path $repo '.toolchain/sdk/c/Include/10.0.26100.0'
$libs = Join-Path $repo '.toolchain/sdk-x64/c'
Push-Location $out
try {
    & "$vc/bin/Hostx64/x64/cl.exe" /nologo /MT /EHsc /std:c++17 /O2 /W4 /WX /guard:cf /GS /utf-8 `
        /external:anglebrackets /external:W0 "/I$vc/include" "/I$sdk/ucrt" "/I$sdk/shared" "/I$sdk/um" `
        "$PSScriptRoot/launcher_jx05.cpp" "/Fo$repo/build/launcher_jx05.obj" /link "/LIBPATH:$vc/lib/x64" "/LIBPATH:$libs/ucrt/x64" "/LIBPATH:$libs/um/x64" `
        user32.lib /SUBSYSTEM:WINDOWS /OUT:JX05.exe /DYNAMICBASE /NXCOMPAT
    if ($LASTEXITCODE) { throw 'Launcher build failed' }
    & './runtime/python.exe' -B './tools/monitor_jx05.py' --self-test
    if ($LASTEXITCODE) { throw 'Bundled runtime self-test failed' }
    $files = [ordered]@{}
    Get-ChildItem -LiteralPath $out -File -Recurse | Sort-Object FullName | ForEach-Object {
        $relative = $_.FullName.Substring($out.Length + 1).Replace('\','/')
        $files[$relative] = (Get-FileHash -LiteralPath $_.FullName).Hash
    }
    @{version=$version; architecture='x64'; ring='B7:FC:01:C6:F3:7E'; adapter='USB\VID_13D3&PID_3567&REV_0100&MI_00'; files=$files} |
        ConvertTo-Json -Depth 5 | Set-Content 'manifest.json' -Encoding UTF8
    Compress-Archive -Path (Join-Path $out '*') -DestinationPath ($out + '.zip')
    Set-Content (Join-Path $repo 'build/latest-package.txt') $out -Encoding UTF8
    Get-FileHash ($out + '.zip')
} finally { Pop-Location }
