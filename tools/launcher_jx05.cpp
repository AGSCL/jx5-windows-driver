#include <windows.h>
#include <string>
#include <vector>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR arguments, int)
{
    wchar_t location[32768];
    DWORD count = GetModuleFileNameW(nullptr, location, ARRAYSIZE(location));
    if (!count || count >= ARRAYSIZE(location)) return 1;
    std::wstring root(location);
    root.resize(root.find_last_of(L"\\/"));
    std::wstring options(arguments);
    bool mapping = options == L"--map";
    bool console = mapping || options == L"--self-test" || options == L"--status";
    if (options.empty()) options = L"--run --enabled";
    std::wstring python = root + (console ? L"\\runtime\\python.exe" : L"\\runtime\\pythonw.exe");
    std::wstring script = root + (mapping ? L"\\tools\\map_jx05.py" : L"\\tools\\monitor_jx05.py");
    std::wstring command = L"\"" + python + L"\" -B \"" + script + L"\" " + (mapping ? L"" : options);
    std::vector<wchar_t> buffer(command.begin(), command.end());
    buffer.push_back(0);
    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    DWORD flags = mapping ? CREATE_NEW_CONSOLE : CREATE_NO_WINDOW;
    if (!CreateProcessW(python.c_str(), buffer.data(), nullptr, nullptr, FALSE, flags,
                        nullptr, root.c_str(), &startup, &process)) {
        MessageBoxW(nullptr, L"No se pudo iniciar JX05. Reinstala la aplicación completa.", L"JX05", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hProcess);
    return static_cast<int>(code);
}
