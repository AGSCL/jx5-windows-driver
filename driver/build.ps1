[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$version = '10.0.26100.0'
$vc = Join-Path $repo '.toolchain/vs/VC/Tools/MSVC/14.44.35207'
$sdk = Join-Path $repo '.toolchain/sdk/c'
$sdkLib = Join-Path $repo '.toolchain/sdk-x64/c'
$wdk = Join-Path $repo '.toolchain/wdk/c'
$out = Join-Path $repo 'build/jx05mtu'
$package = Join-Path $out 'package'
New-Item -ItemType Directory -Force $package | Out-Null
$cl = Join-Path $vc 'bin/Hostx64/x64/cl.exe'
$link = Join-Path $vc 'bin/Hostx64/x64/link.exe'
function Run([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed: $LASTEXITCODE" }
}
$common = @('/nologo', '/W4', '/WX', '/external:anglebrackets', '/external:W0',
    "/I$vc/include", "/I$sdk/Include/$version/ucrt")
$env:PATH = "$vc/bin/Hostx64/x64;$env:PATH"
$userLibs = @("/LIBPATH:$vc/lib/x64", "/LIBPATH:$sdkLib/ucrt/x64", "/LIBPATH:$sdkLib/um/x64")
Push-Location $out
try {
    Run $cl ($common + @('/Zi', '/fsanitize=address', '/MD', '/std:c11',
        "$repo/tests/test_mtu.c", "$PSScriptRoot/mtu.c", '/Fe:mtu-tests.exe', '/link') + $userLibs)
    Run (Join-Path $out 'mtu-tests.exe') @()
    $kernel = $common + @('/c', '/kernel', '/O2', '/GS', '/guard:cf', '/Zl', '/Zi',
        '/analyze', '/analyze:external-', '/analyze:log', 'kernel-analysis.xml',
        '/D_AMD64_', '/DAMD64', '/D_WIN64', '/DWINNT=1', '/DNTDDI_VERSION=0x0A000000',
        '/D_WIN32_WINNT=0x0A00', '/DPOOL_NX_OPTIN=1',
        "/I$wdk/Include/$version/km", "/I$wdk/Include/wdf/kmdf/1.15",
        "/I$sdk/Include/$version/shared", "/I$wdk/Include/$version/km/crt")
    Run $cl ($kernel + @("$PSScriptRoot/jx05mtu.c", "$PSScriptRoot/mtu.c"))
    Run $link @('/nologo', '/DRIVER', '/SUBSYSTEM:NATIVE,10.00', '/ENTRY:FxDriverEntry', '/MACHINE:X64',
        '/NODEFAULTLIB', '/INCREMENTAL:NO', '/DEBUG', '/OPT:REF', '/OPT:ICF', '/guard:cf',
        '/DYNAMICBASE', '/NXCOMPAT', '/INTEGRITYCHECK', '/OSVERSION:10.0',
        "/OUT:$package/jx05mtu.sys", '/PDB:jx05mtu.pdb', 'jx05mtu.obj', 'mtu.obj',
        "/LIBPATH:$wdk/Lib/$version/km/x64", "/LIBPATH:$wdk/Lib/wdf/kmdf/x64/1.15",
        'ntoskrnl.lib', 'hal.lib', 'BufferOverflowFastFailK.lib', 'wdfdriverentry.lib', 'wdfldr.lib')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'jx05mtu.inf') -Destination $package -Force
    Run (Join-Path $wdk "tools/$version/x64/infverif.exe") @('/u', "$package/jx05mtu.inf")
    Run (Join-Path $wdk "bin/$version/x86/Inf2Cat.exe") @("/driver:$package", '/os:10_GE_X64', '/uselocaltime')
    Get-FileHash "$package/jx05mtu.sys", "$package/jx05mtu.inf", "$package/jx05mtu.cat" |
        Select-Object Algorithm, Hash, Path | ConvertTo-Json | Set-Content (Join-Path $out 'hashes.json')
    Write-Output "Built and checked: $package (unsigned, not installed)"
} finally { Pop-Location }
