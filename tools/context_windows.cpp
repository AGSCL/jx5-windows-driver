#include <windows.h>
#include <uiautomation.h>
#include <winrt/base.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Media.Control.h>
#include <cwchar>

using namespace winrt::Windows::Media::Control;

struct Foreground {
    UINT64 window;
    wchar_t process[260];
    wchar_t url[8192];
};

static void Apartment()
{
    static thread_local const bool initialized = [] {
        winrt::init_apartment(winrt::apartment_type::multi_threaded);
        return true;
    }();
    (void)initialized;
}

extern "C" __declspec(dllexport) HRESULT __cdecl JxForeground(Foreground* result)
{
    if (!result) return E_POINTER;
    *result = {};
    try {
        Apartment();
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
        winrt::com_ptr<IUIAutomationElementArray> documents;
        winrt::check_hresult(root->FindAll(TreeScope_Descendants, condition.get(), documents.put()));
        int count = 0;
        winrt::check_hresult(documents->get_Length(&count));
        for (int index = 0; index < count && index < 64; ++index) {
            winrt::com_ptr<IUIAutomationElement> document;
            winrt::check_hresult(documents->GetElement(index, document.put()));
            BOOL offscreen = TRUE;
            if (FAILED(document->get_CurrentIsOffscreen(&offscreen)) || offscreen) continue;
            VARIANT value;
            VariantInit(&value);
            HRESULT hr = document->GetCurrentPropertyValue(UIA_LegacyIAccessibleValuePropertyId, &value);
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

// 0=query (4=playing, 5=paused), 1=previous, 2=next, 3=play/pause.
extern "C" __declspec(dllexport) int __cdecl JxMedia(int command)
{
    try {
        Apartment();
        static thread_local auto manager = GlobalSystemMediaTransportControlsSessionManager::RequestAsync().get();
        auto session = manager.GetCurrentSession();
        if (!session) return 0;
        auto playback = session.GetPlaybackInfo();
        if (!playback) return 0;
        auto status = playback.PlaybackStatus();
        if (status != GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing &&
            status != GlobalSystemMediaTransportControlsSessionPlaybackStatus::Paused) return 0;
        if (command == 0) return static_cast<int>(status);
        auto controls = playback.Controls();
        switch (command) {
        case 1: return controls.IsPreviousEnabled() && session.TrySkipPreviousAsync().get() ? 1 : 0;
        case 2: return controls.IsNextEnabled() && session.TrySkipNextAsync().get() ? 1 : 0;
        case 3: return controls.IsPlayPauseToggleEnabled() && session.TryTogglePlayPauseAsync().get() ? 1 : 0;
        default: return E_INVALIDARG;
        }
    } catch (...) {
        return winrt::to_hresult();
    }
}
