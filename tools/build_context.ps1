$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$vc = Join-Path $repo '.toolchain/vs/VC/Tools/MSVC/14.44.35207'
$sdk = Join-Path $repo '.toolchain/sdk/c/Include/10.0.26100.0'
$libs = Join-Path $repo '.toolchain/sdk-x64/c'
$out = Join-Path $repo 'build/context'
New-Item -ItemType Directory -Force $out | Out-Null
Push-Location $out
try {
    & "$vc/bin/Hostx64/x64/cl.exe" /nologo /LD /MT /EHsc /std:c++20 /O2 /W4 /WX /guard:cf /GS /utf-8 `
        /external:anglebrackets /external:W0 "/I$vc/include" "/I$sdk/ucrt" "/I$sdk/shared" "/I$sdk/um" "/I$sdk/winrt" "/I$sdk/cppwinrt" `
        "$PSScriptRoot/context_windows.cpp" /link "/LIBPATH:$vc/lib/x64" "/LIBPATH:$libs/ucrt/x64" "/LIBPATH:$libs/um/x64" `
        windowsapp.lib user32.lib ole32.lib oleaut32.lib uiautomationcore.lib /OUT:jx05_context.dll /DYNAMICBASE /NXCOMPAT
    if ($LASTEXITCODE) { throw 'Context helper build failed' }
    Get-FileHash jx05_context.dll
} finally { Pop-Location }
