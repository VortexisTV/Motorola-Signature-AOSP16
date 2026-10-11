/*
 * Entry point that frameworks/av/services/audioparameterparser looks up in the library named
 * by ro.audio.ihaladaptervendorextension_libname.
 *
 * The stock library (libaudiohalvendorextn.so, loaded by Motorola's audioserver on stock)
 * exports registerInterface(), which creates the Qualcomm implementation and adds it to the
 * service manager as android.media.audio.IHalAdapterVendorExtension/default. This file only
 * bridges the two entry point names; it contains no parameter logic of its own.
 *
 * If anything fails before the stock code has registered itself, a non-zero status is
 * returned and the AOSP service registers its built-in parser instead, so audioserver never
 * waits for a service that does not come (vendor parameters are then ignored, as without
 * this library).
 */
#define LOG_TAG "VantageAudioVendorExt"

#include <dlfcn.h>

#include <android/binder_manager.h>
#include <android/binder_status.h>
#include <log/log.h>

namespace {
constexpr char kStockLibrary[] = "libaudiohalvendorextn.so";
constexpr char kStockEntryPoint[] = "registerInterface";
constexpr char kServiceName[] = "android.media.audio.IHalAdapterVendorExtension/default";
}  // namespace

extern "C" int createIHalAdapterVendorExtension() {
    void* handle = dlopen(kStockLibrary, RTLD_NOW);
    if (handle == nullptr) {
        ALOGE("cannot load %s: %s", kStockLibrary, dlerror());
        return STATUS_BAD_VALUE;
    }
    auto registerInterface = reinterpret_cast<void (*)()>(dlsym(handle, kStockEntryPoint));
    if (registerInterface == nullptr) {
        ALOGE("%s has no %s: %s", kStockLibrary, kStockEntryPoint, dlerror());
        return STATUS_BAD_VALUE;
    }
    registerInterface();
    AIBinder* registered = AServiceManager_checkService(kServiceName);
    if (registered == nullptr) {
        ALOGE("%s returned without registering %s", kStockEntryPoint, kServiceName);
        return STATUS_BAD_VALUE;
    }
    AIBinder_decStrong(registered);
    ALOGI("stock vendor extension registered as %s", kServiceName);
    return STATUS_OK;
}
