# Motorola Signature (vantage) integration layer: hand-maintained part.
# The list of stock prebuilts lives in the generated vantage-vendor.mk.

# System-side SELinux types the stock vendor policy (version 202504) is written against.
SYSTEM_EXT_PUBLIC_SEPOLICY_DIRS += vendor/motorola/vantage/sepolicy/public
SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS += vendor/motorola/vantage/sepolicy/private

# Telephony: bind the stock Qualcomm IMS service and restate framework values that stock
# ships in /product overlays (not mounted under a TrebleDroid system).
PRODUCT_PACKAGES += \
    VantageTelephonyOverlay \
    VantageFrameworkTelephonyOverlay \
    VantageCarrierConfigOverlay

# Telephony: hold the IMS network request. On stock the vendor CNE app does this with a
# permission it only has under Motorola's platform key (telephony/ims-network/README.md).
PRODUCT_PACKAGES += \
    VantageImsNetwork

# Telephony: tell the Qualcomm RIL that Android telephony is ready. Until then it keeps incoming
# SMS to itself; on stock Qualcomm's telephony service sends this (telephony/ril-ready/README.md).
PRODUCT_PACKAGES += \
    VantageRilReady

# Stock system-side properties that the vendor side and the framework read (properties.mk).
$(call inherit-product, vendor/motorola/vantage/properties.mk)

# Framework values that must not come from TrebleDroid's generic overlays on this device
# (WebView provider list: overlays/VantageFrameworkOverlay).
PRODUCT_PACKAGES += \
    VantageFrameworkOverlay

# Call audio: AOSP's audio parameter parser service hosts the stock implementation of
# IHalAdapterVendorExtension through a small loader library (audio/vendorext/README.md).
PRODUCT_PACKAGES += \
    android.hardware.audio.parameter_parser.example_service \
    libvantage_audiohalvendorext

# Camcorder profiles: point AOSP's libmedia at the profile file the stock libmedia reads
# (init/init.vantage.media.rc).
PRODUCT_PACKAGES += \
    init.vantage.media.rc

# Privileged-permission allowlists (identical to the stock grants).
PRODUCT_COPY_FILES += \
    vendor/motorola/vantage/telephony/permissions/privapp-permissions-vantage-telephony.xml:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/permissions/privapp-permissions-vantage-telephony.xml \
    vendor/motorola/vantage/camera/permissions/privapp-permissions-vantage-camera.xml:$(TARGET_COPY_OUT_PRODUCT)/etc/permissions/privapp-permissions-vantage-camera.xml
