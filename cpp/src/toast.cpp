#include "toast.hpp"

#include "paths.hpp"
#include "win32_helpers.hpp"

#include <windows.data.xml.dom.h>
#include <windows.ui.notifications.h>
#include <propkey.h>
#include <propvarutil.h>
#include <roapi.h>
#include <shlobj.h>

#include <wrl/client.h>

namespace nm {
namespace {

using Microsoft::WRL::ComPtr;
using ABI::Windows::Data::Xml::Dom::IXmlDocument;
using ABI::Windows::Data::Xml::Dom::IXmlDocumentIO;
using ABI::Windows::UI::Notifications::IToastNotification;
using ABI::Windows::UI::Notifications::IToastNotificationFactory;
using ABI::Windows::UI::Notifications::IToastNotificationManagerStatics;
using ABI::Windows::UI::Notifications::IToastNotifier;

constexpr wchar_t kAppId[] = L"Gui.NetworkMonitor.Cpp";

class HString {
public:
    HString() = default;
    explicit HString(const wchar_t* value) {
        WindowsCreateString(value, static_cast<UINT32>(wcslen(value)), &handle_);
    }
    explicit HString(const std::wstring& value) {
        WindowsCreateString(value.c_str(), static_cast<UINT32>(value.size()), &handle_);
    }
    ~HString() {
        if (handle_ != nullptr) {
            WindowsDeleteString(handle_);
        }
    }
    HString(const HString&) = delete;
    HString& operator=(const HString&) = delete;
    HSTRING get() const { return handle_; }

private:
    HSTRING handle_{nullptr};
};

std::wstring shortcut_path() {
    wchar_t programs_path[MAX_PATH]{};
    if (FAILED(SHGetFolderPathW(nullptr, CSIDL_PROGRAMS, nullptr, SHGFP_TYPE_CURRENT, programs_path))) {
        return {};
    }
    return std::wstring(programs_path) + L"\\Network Monitor C++.lnk";
}

std::wstring current_exe_path() {
    wchar_t buffer[MAX_PATH]{};
    const DWORD len = GetModuleFileNameW(nullptr, buffer, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) {
        return {};
    }
    return buffer;
}

HRESULT create_shortcut_if_missing() {
    const std::wstring path = shortcut_path();
    if (path.empty()) {
        return E_FAIL;
    }
    if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) {
        return S_OK;
    }

    const std::wstring exe = current_exe_path();
    if (exe.empty()) {
        return E_FAIL;
    }

    ComPtr<IShellLinkW> link;
    HRESULT hr = CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link));
    if (FAILED(hr)) {
        return hr;
    }

    link->SetPath(exe.c_str());
    link->SetWorkingDirectory(resolve_app_dir().c_str());
    link->SetIconLocation(icon_ico_path().c_str(), 0);

    ComPtr<IPropertyStore> store;
    hr = link.As(&store);
    if (FAILED(hr)) {
        return hr;
    }

    PROPVARIANT app_id;
    hr = InitPropVariantFromString(kAppId, &app_id);
    if (FAILED(hr)) {
        return hr;
    }
    hr = store->SetValue(PKEY_AppUserModel_ID, app_id);
    if (SUCCEEDED(hr)) {
        hr = store->Commit();
    }
    PropVariantClear(&app_id);
    if (FAILED(hr)) {
        return hr;
    }

    ComPtr<IPersistFile> file;
    hr = link.As(&file);
    if (FAILED(hr)) {
        return hr;
    }
    return file->Save(path.c_str(), TRUE);
}

}  // namespace

ToastManager::ToastManager() : app_id_(kAppId) {
    const HRESULT hr = RoInitialize(RO_INIT_SINGLETHREADED);
    initialized_ = SUCCEEDED(hr) || hr == S_FALSE || hr == RPC_E_CHANGED_MODE;
    if (initialized_) {
        ensure_shortcut();
    }
}

ToastManager::~ToastManager() {
    if (initialized_) {
        RoUninitialize();
    }
}

void ToastManager::show_transition(const PeerTransitionEvent& event) {
    if (!initialized_) {
        return;
    }

    const std::wstring title = escape_xml(
        L"[" + widen(event.peer.network_name) + L"] " + widen(event.peer.name) + L" " +
        std::wstring(event.online ? L"ficou online" : L"ficou offline"));
    const std::wstring message = escape_xml(L"IP: " + widen(event.peer.ip));
    const std::wstring xml_payload =
        L"<toast><visual><binding template=\"ToastGeneric\"><text>" + title + L"</text><text>" + message +
        L"</text></binding></visual></toast>";

    HString manager_name(RuntimeClass_Windows_UI_Notifications_ToastNotificationManager);
    HString app_id(app_id_);
    HString xml_name(RuntimeClass_Windows_Data_Xml_Dom_XmlDocument);
    HString toast_name(RuntimeClass_Windows_UI_Notifications_ToastNotification);
    HString xml_payload_hs(xml_payload);

    ComPtr<IToastNotificationManagerStatics> manager;
    ComPtr<IToastNotifier> notifier;
    ComPtr<IXmlDocument> xml;
    ComPtr<IXmlDocumentIO> xml_io;
    ComPtr<IToastNotificationFactory> factory;
    ComPtr<IToastNotification> toast;

    if (FAILED(RoGetActivationFactory(manager_name.get(), IID_PPV_ARGS(&manager)))) {
        return;
    }
    if (FAILED(manager->CreateToastNotifierWithId(app_id.get(), &notifier)) || notifier == nullptr) {
        return;
    }
    if (FAILED(RoActivateInstance(xml_name.get(), &xml)) || xml == nullptr) {
        return;
    }
    if (FAILED(xml.As(&xml_io)) || xml_io == nullptr) {
        return;
    }
    if (FAILED(xml_io->LoadXml(xml_payload_hs.get()))) {
        return;
    }
    if (FAILED(RoGetActivationFactory(toast_name.get(), IID_PPV_ARGS(&factory))) || factory == nullptr) {
        return;
    }
    if (FAILED(factory->CreateToastNotification(xml.Get(), &toast)) || toast == nullptr) {
        return;
    }
    notifier->Show(toast.Get());
}

void ToastManager::ensure_shortcut() {
    create_shortcut_if_missing();
}

}  // namespace nm
