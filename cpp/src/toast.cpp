#include "toast.hpp"

#include "paths.hpp"
#include "win32_helpers.hpp"

#include <windows.data.xml.dom.h>
#include <windows.ui.notifications.h>
#include <roapi.h>
#include <shlobj.h>
#include <propkey.h>
#include <propvarutil.h>

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

std::wstring shortcut_path() {
    wchar_t programs_path[MAX_PATH]{};
    SHGetFolderPathW(nullptr, CSIDL_PROGRAMS, nullptr, SHGFP_TYPE_CURRENT, programs_path);
    return std::wstring(programs_path) + L"\\Network Monitor C++.lnk";
}

HRESULT create_shortcut_if_missing() {
    const std::wstring path = shortcut_path();
    if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) {
        return S_OK;
    }

    ComPtr<IShellLinkW> link;
    HRESULT hr = CoCreateInstance(CLSID_ShellLink, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&link));
    if (FAILED(hr)) {
        return hr;
    }

    const auto exe_path = resolve_app_dir() / "cpp" / "build" / "bin" / "NetworkMonitorCpp.exe";
    const auto fallback = resolve_app_dir() / "NetworkMonitorCpp.exe";
    const auto actual_path = std::filesystem::exists(exe_path) ? exe_path : fallback;
    link->SetPath(actual_path.c_str());
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
    initialized_ = SUCCEEDED(RoInitialize(RO_INIT_MULTITHREADED)) || GetLastError() == S_FALSE;
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

    HSTRING manager_string{};
    HSTRING app_id_string{};
    HSTRING notification_string{};
    HSTRING xml_string{};
    ComPtr<IToastNotificationManagerStatics> manager;
    ComPtr<IToastNotifier> notifier;
    ComPtr<ABI::Windows::Data::Xml::Dom::IXmlDocument> xml;
    ComPtr<IXmlDocumentIO> xml_io;
    ComPtr<IToastNotificationFactory> factory;
    ComPtr<IToastNotification> toast;

    const std::wstring title = escape_xml(
        L"[" + widen(event.peer.network_name) + L"] " + widen(event.peer.name) + L" " +
        std::wstring(event.online ? L"ficou online" : L"ficou offline"));
    const std::wstring message = escape_xml(L"IP: " + widen(event.peer.ip));
    const std::wstring xml_payload =
        L"<toast><visual><binding template=\"ToastGeneric\"><text>" + title + L"</text><text>" + message +
        L"</text></binding></visual></toast>";

    WindowsCreateString(RuntimeClass_Windows_UI_Notifications_ToastNotificationManager,
                        static_cast<UINT32>(wcslen(RuntimeClass_Windows_UI_Notifications_ToastNotificationManager)),
                        &manager_string);
    RoGetActivationFactory(manager_string, IID_PPV_ARGS(&manager));
    WindowsCreateString(app_id_.c_str(), static_cast<UINT32>(app_id_.size()), &app_id_string);
    manager->CreateToastNotifierWithId(app_id_string, &notifier);

    WindowsCreateString(RuntimeClass_Windows_Data_Xml_Dom_XmlDocument,
                        static_cast<UINT32>(wcslen(RuntimeClass_Windows_Data_Xml_Dom_XmlDocument)), &xml_string);
    RoActivateInstance(xml_string, &xml);
    xml.As(&xml_io);

    WindowsCreateString(xml_payload.c_str(), static_cast<UINT32>(xml_payload.size()), &notification_string);
    xml_io->LoadXml(notification_string);

    HSTRING toast_class{};
    WindowsCreateString(RuntimeClass_Windows_UI_Notifications_ToastNotification,
                        static_cast<UINT32>(wcslen(RuntimeClass_Windows_UI_Notifications_ToastNotification)),
                        &toast_class);
    RoGetActivationFactory(toast_class, IID_PPV_ARGS(&factory));
    factory->CreateToastNotification(xml.Get(), &toast);
    notifier->Show(toast.Get());

    WindowsDeleteString(toast_class);
    WindowsDeleteString(notification_string);
    WindowsDeleteString(xml_string);
    WindowsDeleteString(app_id_string);
    WindowsDeleteString(manager_string);
}

void ToastManager::ensure_shortcut() {
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    create_shortcut_if_missing();
    CoUninitialize();
}

}  // namespace nm
