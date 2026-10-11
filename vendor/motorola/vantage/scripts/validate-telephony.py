#!/usr/bin/env python3
"""Static validation of the telephony integration (radio HALs, IMS, RIL audio bridge, carrier data).

    validate-telephony.py --map /system=DIR --map /system_ext=DIR --map /product=DIR \
        --map /vendor=DIR --map /odm=DIR --reports reports [--sim-mccmnc 313390] [--name NAME]

Uses the same --map convention as preflight.py. Checks configuration and file-level
preconditions only; registration, data, SMS, calls and audio are reported as UNKNOWN because
they can only be established on the device with a SIM and a network.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check_java_linkage import Platform  # noqa: E402
from motofw import apk, dex, fsmeta  # noqa: E402
from motofw.report import Report  # noqa: E402

AREA = "telephony"
RADIO_HALS = ["config", "data", "messaging", "modem", "network", "sim", "voice"]


def device_hals(platform):
    hals = {}
    for prefix in ("/vendor", "/odm"):
        for root in platform._roots(prefix):
            for doc in fsmeta.read_vintf_dir(root / "etc"):
                if doc["kind"] != "manifest":
                    continue
                for hal in doc["hals"]:
                    e = hals.setdefault(hal["name"], {"versions": set(), "instances": set()})
                    e["versions"].update(hal["versions"])
                    e["instances"].update(hal["fqnames"])
                    for i in hal["interfaces"]:
                        e["instances"].update(f"{i['name']}/{inst}" for inst in i["instances"])
    return hals


def image_apps(platform):
    out = {}
    for path, prefix in platform.apks(("/system", "/system_ext", "/product", "/vendor")):
        info = apk.inspect(str(path))
        if info.get("package"):
            out.setdefault(info["package"], (path, info, prefix))
    return out


def dex_classes(path):
    out = set()
    for d in dex.load(path):
        for i in range(d.n_class):
            import struct
            out.add(d.type(struct.unpack_from("<I", d.buf, d._o_class + i * 32)[0]))
    return out


def dex_strings(path):
    out = set()
    for d in dex.load(path):
        for i in range(d.n_str):
            try:
                out.add(d.string(i))
            except (ValueError, IndexError, UnicodeDecodeError):
                pass
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--sim-mccmnc", default="313390", help="MCC+MNC of the SIM to check carrier data for")
    ap.add_argument("--name", default="validate-telephony")
    ap.add_argument("--aosp-tree", help="source tree the image was built from (enables source-level checks)")
    args = ap.parse_args()
    platform = Platform(args.map)
    r = Report(f"Telephony validation: {args.name}", {"maps": " ".join(args.map), "sim": args.sim_mccmnc})
    hals = device_hals(platform)
    apps = image_apps(platform)

    # 1. Standard radio HALs
    missing, notes = [], []
    for short in RADIO_HALS:
        name = f"android.hardware.radio.{short}"
        hal = hals.get(name)
        if not hal:
            missing.append(name)
        else:
            notes.append(f"{name} V{','.join(sorted(hal['versions'])) or '1'}: {sorted(hal['instances'])}")
    if missing:
        r.fail("radio.hal.standard", "vendor does not declare required radio AIDL HALs", missing, AREA)
    else:
        r.passed("radio.hal.standard", f"vendor declares all {len(RADIO_HALS)} android.hardware.radio.* AIDL HALs",
                 notes, AREA)
    if "android.hardware.radio.ims" in hals:
        r.passed("radio.hal.aosp_ims", "vendor implements AOSP's android.hardware.radio.ims", area=AREA)
    else:
        r.warn("radio.hal.aosp_ims", "vendor does not implement android.hardware.radio.ims; IMS is only available "
               "through vendor.qti.hardware.radio.ims and Qualcomm's IMS service", area=AREA)

    # 2. Vendor daemons
    services = {}
    for root in platform._roots("/vendor"):
        for svc in fsmeta.read_init_dir(root / "etc"):
            services[svc["name"]] = (svc, root)
    bad, notes = [], []
    for name in ("vendor.qcrild", "vendor.qcrild2", "vendor.imsdaemon", "vendor.ims_rtp_daemon"):
        if name not in services:
            bad.append(f"{name}: no init service")
            continue
        svc, root = services[name]
        exe = root / svc["exec"].replace("/vendor/", "", 1)
        (notes if exe.exists() else bad).append(f"{name}: {svc['exec']} ({'present' if exe.exists() else 'MISSING'})")
    (r.fail if bad else r.passed)("radio.vendor_daemons", "vendor RIL/IMS daemons are defined and present"
                                  if not bad else "vendor RIL/IMS daemons incomplete", bad or notes, AREA)

    # 3. Qualcomm vendor interfaces and the system-side packages that implement their clients
    pairs = [
        ("vendor.qti.hardware.radio.ims", "vendor.qti.hardware.radio.ims.IImsRadio", "IMS radio (VoLTE/VoWiFi signalling)"),
        ("vendor.qti.hardware.radio.am", "vendor.qti.hardware.radio.am.IQcRilAudio", "RIL audio bridge (voice-session audio)"),
    ]
    strings_cache = {}
    for hal_name, descriptor, purpose in pairs:
        tid = f"qti.client:{hal_name.rsplit('.', 1)[-1]}"
        if hal_name not in hals:
            r.unknown(tid, f"vendor does not declare {hal_name}; no client needed", area=AREA)
            continue
        # A real AIDL client links the generated proxy class; a package that only mentions the
        # interface name in a string (e.g. a settings app listing HALs) is not a client.
        proxy = "L" + descriptor.replace(".", "/") + "$Stub$Proxy;"
        clients = []
        for pkg, (path, info, prefix) in apps.items():
            if prefix == "/vendor" or not info.get("dex_count"):
                continue
            if path not in strings_cache:
                strings_cache[path] = dex_classes(str(path))
            if proxy in strings_cache[path]:
                clients.append(f"{pkg} ({path})")
        inst = sorted(hals[hal_name]["instances"])
        if hal_name.endswith(".am") and len(clients) > 1:
            # The RIL keeps one request interface per slot: a second client would replace the first.
            r.fail("audio.bridge_single_owner", f"{len(clients)} packages register RIL audio callbacks; they would "
                   "overwrite each other's registration", clients, AREA)
        elif hal_name.endswith(".am") and clients:
            r.passed("audio.bridge_single_owner", "exactly one package in the image registers RIL audio callbacks",
                     clients, AREA)
        if clients:
            r.passed(tid, f"{purpose}: vendor serves {inst}; system-side client present", clients, AREA)
        else:
            r.fail(tid, f"{purpose}: vendor serves {inst} but no system-side package implements a client; "
                   "requests from the RIL would go unanswered", area=AREA)

    # 4. IMS service package
    ims = apps.get("org.codeaurora.ims")
    if not ims:
        r.fail("ims.package", "org.codeaurora.ims is not in the image", area=AREA)
    else:
        path, info, prefix = ims
        svc_ok = any("android.telephony.ims.ImsService" in s.get("actions", [])
                     and s.get("permission") == "android.permission.BIND_IMS_SERVICE" for s in info.get("services", []))
        libs = [l["name"] for l in info.get("uses_libraries", []) if l.get("required", True) is not False]
        unresolved = [l for l in libs if l not in platform.libraries or platform.host(platform.libraries[l]["file"]) is None]
        details = [f"path {path}", f"persistent={info.get('application', {}).get('persistent')}",
                   f"required libraries {libs}"]
        if not svc_ok:
            r.fail("ims.package", "org.codeaurora.ims does not expose an ImsService guarded by BIND_IMS_SERVICE",
                   details, AREA)
        elif unresolved:
            r.fail("ims.package", f"org.codeaurora.ims requires shared libraries missing from the image: {unresolved}",
                   details, AREA)
        else:
            r.passed("ims.package", "org.codeaurora.ims is installed with its ImsService and all required libraries",
                     details, AREA)

    # 5. Device IMS capability flags from the (stock) vendor overlay are not re-checked here;
    #    feature declarations in the image are.
    feats = set()
    for prefix in ("/system", "/system_ext", "/product", "/vendor"):
        for root in platform._roots(prefix):
            feats |= set(fsmeta.read_permission_xmls(root / "etc")["features"])
    need = ["android.hardware.telephony", "android.hardware.telephony.ims"]
    absent = [f for f in need if f not in feats]
    (r.warn if absent else r.passed)("features.telephony", f"feature declarations missing: {absent}" if absent
                                     else "android.hardware.telephony and .ims features are declared", area=AREA)

    # 6. APN database
    apn_file = platform.host("/product/etc/apns-conf.xml") or platform.host("/system/etc/apns-conf.xml")
    mcc, mnc = args.sim_mccmnc[:3], args.sim_mccmnc[3:]
    if apn_file is None:
        r.fail("carrier.apn", "no apns-conf.xml in the image", area=AREA)
    else:
        types = set()
        count = 0
        try:
            for el in ET.parse(apn_file).getroot().iter("apn"):
                count += 1
                if el.get("mcc") == mcc and el.get("mnc") == mnc:
                    types |= {t.strip() for t in (el.get("type") or "default").split(",")}
        except ET.ParseError as exc:
            r.fail("carrier.apn", f"{apn_file} is not well-formed XML: {exc}", area=AREA)
            types = None
        if types is not None:
            want = {"default", "ims", "mms"}
            note = [f"{apn_file}: {count} APNs; types for {mcc}/{mnc}: {sorted(types)}"]
            if want <= types:
                r.passed("carrier.apn", f"APN database has default, ims and mms APNs for {mcc}/{mnc}", note, AREA)
            elif types:
                r.warn("carrier.apn", f"APN database lacks {sorted(want - types)} for {mcc}/{mnc}", note, AREA)
            else:
                r.warn("carrier.apn", f"APN database has no entry for {mcc}/{mnc}", note, AREA)

    # 7. Carrier-config overlay keys must be real CarrierConfigManager keys of this framework
    overlay = apps.get("com.android.carrierconfig.overlay.vantage")
    fw = platform.host("/system/framework/framework.jar")
    src = HERE.parent / "telephony" / "carrier" / "VantageCarrierConfigOverlay" / "res" / "xml" / "vendor.xml"
    if not src.exists():
        r.unknown("carrier.config_keys", "carrier-config overlay source not found next to the scripts", area=AREA)
    elif fw is None:
        r.unknown("carrier.config_keys", "framework.jar not found in the image", area=AREA)
    else:
        known = dex_strings(str(fw))
        # Keys may also be defined by the telephony jar or by Qualcomm's IMS library (QtiCarrierConfigs).
        for extra in ("/system/framework/telephony-common.jar", "/product/framework/ims-ext-common.jar"):
            host = platform.host(extra)
            if host:
                known |= dex_strings(str(host))
        keys, blocks = [], 0
        for block in ET.parse(src).getroot().iter("carrier_config"):
            blocks += 1
            keys += [(block.get("mcc"), block.get("mnc"), el.get("name")) for el in block if el.get("name")]
        unknown = sorted({k for _, _, k in keys if k not in known})
        mine = [k for m, n, k in keys if m == mcc and n == mnc]
        note = [f"{blocks} carrier blocks, {len(keys)} keys; {len(mine)} for {mcc}/{mnc}"]
        if unknown:
            r.warn("carrier.config_keys", f"{len(unknown)} overlay keys are not string constants of this framework "
                   "(they would be ignored)", unknown, AREA)
        else:
            r.passed("carrier.config_keys", "every carrier-config overlay key exists in this framework", note, AREA)
        if "carrier_volte_available_bool" in mine:
            r.passed("carrier.volte_flag", f"carrier_volte_available_bool is set for {mcc}/{mnc}", area=AREA)
        else:
            r.warn("carrier.volte_flag", f"no carrier_volte_available_bool for {mcc}/{mnc}; VoLTE would depend on "
                   "AOSP CarrierConfig assets", area=AREA)
        if overlay is None:
            r.fail("carrier.config_overlay", "VantageCarrierConfigOverlay is not installed in the image", area=AREA)
        else:
            r.passed("carrier.config_overlay", f"carrier-config overlay installed ({overlay[0]})", area=AREA)

    # 8. Vendor apps that rely on the OEM platform certificate
    fw_res = platform.host("/system/framework/framework-res.apk")
    plat_cert = apk.signing_info(str(fw_res))["cert_sha256"] if fw_res else None
    oem_cert = None
    for root in platform._roots("/vendor"):
        mac = root / "etc" / "selinux" / "vendor_mac_permissions.xml"
        if mac.exists():
            import hashlib
            for m in re.finditer(r'<signer signature="([0-9a-fA-F]+)"\s*>(.*?)</signer>', mac.read_text(), re.S):
                if 'seinfo value="platform"' in m.group(2):
                    oem_cert = hashlib.sha256(bytes.fromhex(m.group(1))).hexdigest()
    affected = []
    for pkg, (path, info, prefix) in apps.items():
        if prefix == "/vendor" and oem_cert and info["signing"].get("cert_sha256") == oem_cert and oem_cert != plat_cert:
            sens = [p.split(".")[-1] for p in info.get("uses_permissions", [])
                    if re.search(r"PRIVILEGED|RESTRICTED_NETWORKS|MAINLINE|WRITE_SECURE|INTERACT_ACROSS|UPDATE_DEVICE", p)]
            if not sens and not info.get("sharedUserId"):
                continue  # resource overlays and apps that ask for nothing signature-protected
            affected.append(f"{pkg} ({path.name}) uid={info.get('sharedUserId')} needs {sens or 'no signature permissions'}")
    if affected:
        r.warn("vendor.oem_signed_apps", f"{len(affected)} vendor apps are signed with the OEM platform certificate; "
               "under this ROM they lose platform-signature permissions (TELEPHONY_PORT.md section 4.1)", affected, AREA)
    elif oem_cert == plat_cert:
        r.passed("vendor.oem_signed_apps", "image platform certificate equals the vendor's (stock system)", area=AREA)
    else:
        r.passed("vendor.oem_signed_apps", "no vendor app depends on the OEM platform certificate", area=AREA)

    # 8a. Somebody should hold the IMS network request. Telephony only creates its IMS data network
    #     while a request for the (restricted) IMS capability exists; on stock the vendor CNE app
    #     holds it through a platform-signature permission (telephony/ims-network/README.md).
    restricted = "android.permission.CONNECTIVITY_USE_RESTRICTED_NETWORKS"
    tid = "ims.network_request"
    own = apps.get("vantage.telephony.imsnetwork")
    cne = apps.get("com.qualcomm.qti.cne")
    cne_can = bool(cne and restricted in cne[1].get("uses_permissions", [])
                   and plat_cert and cne[1]["signing"].get("cert_sha256") == plat_cert)
    if own:
        path, info, prefix = own
        problems = []
        if info["signing"].get("cert_sha256") != plat_cert:
            problems.append("not signed with the image platform certificate")
        if restricted not in info.get("uses_permissions", []):
            problems.append(f"does not request {restricted}")
        if str(info.get("application", {}).get("persistent")).lower() not in ("true", "1", "-1"):
            problems.append("not persistent (would not run from boot)")
        if "/priv-app/" in str(path):
            problems.append("installed as a privileged app: needs a privapp allowlist entry instead")
        details = [f"path {path}", f"application {info.get('application', {})}"]
        if problems:
            r.fail(tid, "the IMS network requester cannot work: " + "; ".join(problems), details, AREA)
        else:
            r.passed(tid, "vantage.telephony.imsnetwork is platform-signed, persistent and may request "
                     "restricted networks (holds the IMS network request, as the vendor CNE app does on stock)",
                     details, AREA)
    elif cne_can:
        r.passed(tid, "com.qualcomm.qti.cne is signed with the image platform certificate and may request "
                 "the IMS network (stock arrangement)", [f"path {cne[0]}"], AREA)
    else:
        r.warn(tid, "no component in the image can request the IMS network: the stock requester "
               "com.qualcomm.qti.cne is not signed with this image's platform certificate. Telephony then "
               "has no IMS data network of its own (needed for WWAN/WLAN handover and application-side "
               "IMS traffic; effect on plain VoLTE calls unknown)", area=AREA)

    # 8b. Call-RX audio source must get a software output (TrebleDroid android-16.0.0_r1-td lost that
    #     statement; audioserver then aborts on every call, see TELEPHONY_PORT.md section 3)
    tid = "audio.call_rx_swoutput"
    apm = Path(args.aosp_tree or "") / "frameworks/av/services/audiopolicy/managerdefault/AudioPolicyManager.cpp"
    if not args.aosp_tree or not apm.is_file():
        r.unknown(tid, "source tree not given (--aosp-tree); the telephony-RX patch code was not checked", area=AREA)
    else:
        src = apm.read_text(encoding="utf-8", errors="replace")
        start = src.find("status_t AudioPolicyManager::createAudioPatchInternal(")
        end = src.find("status_t AudioPolicyManager::releaseAudioPatch(", start + 1)
        body = src[start:end] if 0 <= start < end else ""
        internal = body.partition('"raw patches"')[2].partition("create a software bridge")[0]
        asserting = "a swOutput shall always be associated" in src
        if not internal:
            r.unknown(tid, "createAudioPatchInternal no longer has the expected layout; review it by hand",
                      [str(apm)], AREA)
        elif "setSwOutput(" in internal:
            r.passed(tid, "createAudioPatchInternal attaches a software output to internal (call) sources",
                     [str(apm)], AREA)
        elif asserting:
            r.fail(tid, "internal (call) sources never get a software output and connectAudioSourceToSink "
                   "asserts on it: audioserver would abort on every call", [str(apm)], AREA)
        else:
            r.warn(tid, "internal (call) sources do not get a software output", [str(apm)], AREA)

    # 8c. The call-audio bridge must keep its response interface per slot, wait for the HAL and
    #     re-register when the RIL dies (patches/packages/apps/QcRilAm; TELEPHONY_PORT.md section 3)
    tid = "audio.bridge_recovery"
    kt = Path(args.aosp_tree or "") / "packages/apps/QcRilAm/src/me/phh/qcrilam/QcRilAmService.kt"
    if not args.aosp_tree or not kt.is_file():
        r.unknown(tid, "source tree not given (--aosp-tree); the call-audio bridge source was not checked", area=AREA)
    else:
        src = kt.read_text(encoding="utf-8", errors="replace")
        need = {"per-slot connection": "class AidlSlot", "wait for the declared HAL": "waitForDeclaredService",
                "death recipient": "linkToDeath", "audioserver state to the RIL": "setAudioServerStateCallback"}
        missing = [k for k, v in need.items() if v not in src]
        shared = re.search(r"^private var qcRilAudioResponse", src, re.M)
        if missing or shared:
            r.fail(tid, "the call-audio bridge is the unpatched TrebleDroid version: "
                   + ", ".join(missing + (["one response interface shared by all slots"] if shared else [])),
                   [str(kt)], AREA)
        else:
            r.passed(tid, "the call-audio bridge keeps a response interface per slot, waits for the HAL, "
                     "re-registers on RIL death and reports audioserver state", [str(kt)], AREA)

    # 9. Things no static check can establish
    for tid, text in (
        ("hw.registration", "SIM detection and network registration (LTE/NR)"),
        ("hw.data", "mobile data on the default APN"),
        ("hw.sms", "SMS send and receive"),
        ("hw.voice", "outgoing and incoming voice calls"),
        ("hw.ims_registration", "IMS registration / VoLTE with the carrier"),
        ("hw.call_audio", "microphone, earpiece, speaker and Bluetooth audio during a call"),
        ("hw.dual_sim", "dual-SIM behaviour"),
    ):
        r.unknown(tid, f"{text}: requires the device, a SIM and a network", area="hardware")

    path = r.write(args.reports, args.name)
    r.print_summary()
    print(f"report: {path}")
    return 1 if r.counts()["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
