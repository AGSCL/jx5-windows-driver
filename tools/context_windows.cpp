#include <windows.h>
#include <uiautomation.h>
#include <winrt/base.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Media.h>
#include <winrt/Windows.Media.Control.h>
#include <cwchar>
#include <chrono>
#include <string>
#include <cwctype>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <algorithm>
#include <cmath>

using namespace winrt::Windows::Media::Control;

struct Foreground {
    UINT64 window;
    wchar_t process[260];
    wchar_t url[8192];
};

struct Apartment {
    Apartment() { winrt::init_apartment(winrt::apartment_type::multi_threaded); }
    ~Apartment() { winrt::uninit_apartment(); }
};

// direction: signed steps of 5 points (-2..2), 0=query. Result: percent or HRESULT.
extern "C" __declspec(dllexport) int __cdecl JxVolume(int direction)
{
    if (direction < -2 || direction > 2) return E_INVALIDARG;
    try {
        Apartment apartment;
        winrt::com_ptr<IMMDeviceEnumerator> enumerator;
        winrt::check_hresult(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr,
            CLSCTX_INPROC_SERVER, IID_PPV_ARGS(enumerator.put())));
        winrt::com_ptr<IMMDevice> device;
        winrt::check_hresult(enumerator->GetDefaultAudioEndpoint(eRender, eMultimedia, device.put()));
        winrt::com_ptr<IAudioEndpointVolume> volume;
        winrt::check_hresult(device->Activate(__uuidof(IAudioEndpointVolume), CLSCTX_INPROC_SERVER,
            nullptr, volume.put_void()));
        float level = 0;
        winrt::check_hresult(volume->GetMasterVolumeLevelScalar(&level));
        if (direction) {
            level = std::clamp(level + static_cast<float>(direction) * 0.05f, 0.0f, 1.0f);
            winrt::check_hresult(volume->SetMasterVolumeLevelScalar(level, nullptr));
        }
        return static_cast<int>(std::lround(level * 100));
    } catch (...) { return winrt::to_hresult(); }
}

template<typename T> static auto Finish(T const& operation)
{
    if (operation.wait_for(std::chrono::milliseconds(800)) != winrt::Windows::Foundation::AsyncStatus::Completed) {
        operation.Cancel();
        winrt::throw_hresult(HRESULT_FROM_WIN32(ERROR_TIMEOUT));
    }
    return operation.GetResults();
}

extern "C" __declspec(dllexport) HRESULT __cdecl JxForeground(Foreground* result)
{
    if (!result) return E_POINTER;
    *result = {};
    try {
        Apartment apartment;
        HWND window = GetForegroundWindow();
        if (!window) return S_FALSE;
        result->window = reinterpret_cast<UINT64>(window);
        DWORD pid = 0;
        GetWindowThreadProcessId(window, &pid);
        HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if (!process) return HRESULT_FROM_WIN32(GetLastError());
        DWORD capacity = ARRAYSIZE(result->process);
        BOOL success = QueryFullProcessImageNameW(process, 0, result->process, &capacity);
        DWORD error = GetLastError();
        CloseHandle(process);
        if (!success) return HRESULT_FROM_WIN32(error);
        const wchar_t* name = wcsrchr(result->process, L'\\');
        name = name ? name + 1 : result->process;
        if (_wcsicmp(name, L"chrome.exe") && _wcsicmp(name, L"msedge.exe") &&
            _wcsicmp(name, L"firefox.exe") && _wcsicmp(name, L"brave.exe") &&
            _wcsicmp(name, L"opera.exe")) return S_OK;

        winrt::com_ptr<IUIAutomation> automation;
        winrt::check_hresult(CoCreateInstance(CLSID_CUIAutomation, nullptr, CLSCTX_INPROC_SERVER,
                                              IID_PPV_ARGS(automation.put())));
        auto timeouts = automation.try_as<IUIAutomation2>();
        if (timeouts) {
            (void)timeouts->put_ConnectionTimeout(500);
            (void)timeouts->put_TransactionTimeout(500);
        }
        winrt::com_ptr<IUIAutomationElement> root;
        winrt::check_hresult(automation->ElementFromHandle(window, root.put()));
        VARIANT type;
        VariantInit(&type);
        type.vt = VT_I4;
        type.lVal = UIA_DocumentControlTypeId;
        winrt::com_ptr<IUIAutomationCondition> condition;
        winrt::check_hresult(automation->CreatePropertyCondition(UIA_ControlTypePropertyId, type, condition.put()));
        VARIANT visible;
        VariantInit(&visible);
        visible.vt = VT_BOOL;
        visible.boolVal = VARIANT_FALSE;
        winrt::com_ptr<IUIAutomationCondition> onScreen, combined;
        winrt::check_hresult(automation->CreatePropertyCondition(UIA_IsOffscreenPropertyId, visible, onScreen.put()));
        winrt::check_hresult(automation->CreateAndCondition(condition.get(), onScreen.get(), combined.put()));
        winrt::com_ptr<IUIAutomationElement> document;
        winrt::check_hresult(root->FindFirst(TreeScope_Descendants, combined.get(), document.put()));
        if (!document) return S_OK;
        for (PROPERTYID property : {UIA_LegacyIAccessibleValuePropertyId, UIA_ValueValuePropertyId}) {
            VARIANT value;
            VariantInit(&value);
            HRESULT hr = document->GetCurrentPropertyValue(property, &value);
            if (SUCCEEDED(hr) && value.vt == VT_BSTR && value.bstrVal && SysStringLen(value.bstrVal) < ARRAYSIZE(result->url)) {
                wcscpy_s(result->url, value.bstrVal);
            }
            VariantClear(&value);
            if (result->url[0]) break;
        }
        if (window != GetForegroundWindow()) { *result = {}; return S_FALSE; }
        return S_OK;
    } catch (...) {
        return winrt::to_hresult();
    }
}

static bool MusicApp(GlobalSystemMediaTransportControlsSession const& session)
{
    if (!session) return false;
    try {
        auto info = session.GetPlaybackInfo();
        auto status = info.PlaybackStatus();
        if (status != GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing &&
            status != GlobalSystemMediaTransportControlsSessionPlaybackStatus::Paused) return false;
        std::wstring app(session.SourceAppUserModelId());
        for (auto& letter : app) letter = static_cast<wchar_t>(towlower(letter));
        for (auto browser : {L"chrome", L"msedge", L"firefox", L"brave", L"opera", L"vivaldi", L"arc.exe", L"browser"})
            if (app.find(browser) != std::wstring::npos) return false;
        auto type = Finish(session.TryGetMediaPropertiesAsync()).PlaybackType();
        return type && type.Value() == winrt::Windows::Media::MediaPlaybackType::Music;
    } catch (...) { return false; }
}

static BOOL CALLBACK FindVlc(HWND window, LPARAM parameter)
{
    if (!IsWindowVisible(window) || GetWindow(window, GW_OWNER)) return TRUE;
    wchar_t title[1024], path[32768];
    if (!GetWindowTextW(window, title, ARRAYSIZE(title))) return TRUE;
    // shortcut: VLC's default loaded-item title; custom window titles need a VLC adapter API.
    if (!wcsstr(title, L" - ") || !wcsstr(title, L"VLC")) return TRUE;
    DWORD pid = 0, length = ARRAYSIZE(path);
    GetWindowThreadProcessId(window, &pid);
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!process) return TRUE;
    BOOL success = QueryFullProcessImageNameW(process, 0, path, &length);
    CloseHandle(process);
    const wchar_t* name = success ? wcsrchr(path, L'\\') : nullptr;
    if (!name || _wcsicmp(name + 1, L"vlc.exe")) return TRUE;
    auto target = reinterpret_cast<HWND*>(parameter);
    // More than one player is ambiguous; do not choose one arbitrarily.
    if (*target) { *target = nullptr; return FALSE; }
    *target = window;
    return TRUE;
}

static int Vlc(int command, UINT64 expectedWindow)
{
    HWND target = nullptr;
    EnumWindows(FindVlc, reinterpret_cast<LPARAM>(&target));
    if (!target) return 0;
    if (command == 0) return 5;
    if (reinterpret_cast<UINT64>(GetForegroundWindow()) != expectedWindow) return 0;
    const int commands[] = {0, APPCOMMAND_MEDIA_PREVIOUSTRACK, APPCOMMAND_MEDIA_NEXTTRACK, APPCOMMAND_MEDIA_PLAY_PAUSE};
    if (command < 1 || command > 3) return E_INVALIDARG;
    DWORD_PTR result = 0;
    return SendMessageTimeoutW(target, WM_APPCOMMAND, reinterpret_cast<WPARAM>(target),
        static_cast<LPARAM>(commands[command]) << 16, SMTO_ABORTIFHUNG | SMTO_BLOCK, 200, &result) && result ? 1 : 0;
}

// 0=query (4=playing, 5=paused), 1=previous, 2=next, 3=play/pause.
extern "C" __declspec(dllexport) int __cdecl JxMedia(int command, UINT64 expectedWindow)
{
    // VLC 3 has no SMTC session; its targeted command path needs no broker.
    if (Vlc(0, 0)) return Vlc(command, expectedWindow);
    try {
        Apartment apartment;
        auto manager = Finish(GlobalSystemMediaTransportControlsSessionManager::RequestAsync());
        auto session = manager.GetCurrentSession();
        if (!MusicApp(session)) {
            session = nullptr;
            for (auto candidate : manager.GetSessions()) {
                if (!MusicApp(candidate)) continue;
                if (!session || candidate.GetPlaybackInfo().PlaybackStatus() == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing)
                    session = candidate;
                if (session.GetPlaybackInfo().PlaybackStatus() == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing) break;
            }
        }
        if (!session) return Vlc(command, expectedWindow);
        auto playback = session.GetPlaybackInfo();
        if (!playback) return 0;
        auto status = playback.PlaybackStatus();
        if (status != GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing &&
            status != GlobalSystemMediaTransportControlsSessionPlaybackStatus::Paused) return 0;
        if (command == 0) return static_cast<int>(status);
        if (reinterpret_cast<UINT64>(GetForegroundWindow()) != expectedWindow) return 0;
        auto controls = playback.Controls();
        switch (command) {
        case 1: return controls.IsPreviousEnabled() && Finish(session.TrySkipPreviousAsync()) ? 1 : 0;
        case 2: return controls.IsNextEnabled() && Finish(session.TrySkipNextAsync()) ? 1 : 0;
        case 3: return controls.IsPlayPauseToggleEnabled() && Finish(session.TryTogglePlayPauseAsync()) ? 1 : 0;
        default: return E_INVALIDARG;
        }
    } catch (...) {
        return winrt::to_hresult();
    }
}
