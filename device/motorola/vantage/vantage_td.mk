# Motorola Signature (codename vantage, SM8845 "canoe")
#
# TrebleDroid AOSP 16 system image (arm64, A/B, vanilla, no su) plus the vantage
# integration layer. PRODUCT_DEVICE stays tdgsi_arm64_ab so this product shares the board
# configuration and the output directory of the unmodified baseline (treble_arm64_bvN):
# building it after the baseline is an incremental build, and every difference between the
# two images is attributable to vendor/motorola/vantage.

# The integration layer is inherited first on purpose: for PRODUCT_COPY_FILES the first entry
# for a destination wins, and AOSP (aosp_product.mk) also installs /product/etc/apns-conf.xml.
$(call inherit-product, vendor/motorola/vantage/vantage-vendor.mk)
$(call inherit-product, vendor/motorola/vantage/vantage.mk)

$(call inherit-product, device/phh/treble/treble_arm64_bvN.mk)

PRODUCT_NAME := vantage_td

# What the phone calls itself on stock. The stock vendor and Motorola Camera read these
# (vendor/motorola/vantage/properties.mk, section "Device identity").
PRODUCT_BRAND := motorola
PRODUCT_MANUFACTURER := motorola
PRODUCT_MODEL := motorola signature

PRODUCT_DEVICE := tdgsi_arm64_ab
