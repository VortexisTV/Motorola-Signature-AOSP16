#!/usr/bin/env python3
"""Turn a device capture into one consolidated PASS / FAIL / WARNING / UNKNOWN report.

    analyze_device_evidence.py CAPTURE_DIR [--reference STOCK_CAPTURE_DIR]

CAPTURE_DIR is either one snapshot written by collect-device-evidence.sh or a session directory
written by device-session.sh (snapshots, live log, automatic in-call and camera snapshots).
Everything is read from files; the phone is not contacted. Output: report.md and report.json in
CAPTURE_DIR, plus a summary on the console.

A PASS here is evidence from the running device, which is what the static validators cannot
give. It still only covers what was exercised while the capture ran: no call observed means the
call checks stay UNKNOWN, not PASS.
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

CRITICAL = ("audioserver", "system_server", "com.android.phone", "org.codeaurora.ims", "me.phh.qcrilam",
            "vantage.telephony.imsnetwork", "cameraserver", "com.motorola.camera5", "surfaceflinger",
            "qcrilNrd", "imsdaemon", "ims_rtp_daemon", "vendor.qti.camera.provider", "zygote64")
WATCH_DOMAINS = ("vendor_qtelephony", "moto_camera_app", "system_app", "platform_app", "radio", "rild",
                 "audioserver", "cameraserver", "hal_audio_default", "hal_camera_default", "priv_app",
                 "vendor_qtidataservices_app", "system_server", "init", "vendor_init", "zygote")
AVC = re.compile(r"avc:\s+denied\s+\{ ([^}]+) \}.*?scontext=u:r:([^:]+):\S+ tcontext=u:(?:object_r|r):([^:]+):\S+ "
                 r"tclass=(\S+)(?: permissive=(\d))?")


class Capture:
    def __init__(self, root):
        self.root = Path(root)
        snaps = sorted(p for p in (self.root / "snapshots").glob("*") if p.is_dir()) if (self.root / "snapshots").is_dir() else []
        self.snapshots = snaps or [self.root]
        self.last = self.snapshots[-1]
        self.is_session = bool(snaps)
        logs = [self.root / "logcat-early.txt", self.root / "logcat-boot.txt", self.root / "logcat-live.txt"] if self.is_session else []
        logs += [s / "logcat-all.txt" for s in (self.snapshots[-1:] if self.is_session else self.snapshots)]
        self.log_files = [p for p in logs if p.is_file()]
        self._lines = None

    def text(self, name, snap=None):
        p = (snap or self.last) / f"{name}.txt"
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""

    def lines(self):
        if self._lines is None:
            seen, out = set(), []
            for f in self.log_files:
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line not in seen:   # the boot dump and the live log overlap
                        seen.add(line)
                        out.append(line)
            self._lines = out
        return self._lines

    def grep(self, pattern, limit=None):
        rx = re.compile(pattern)
        out = [l for l in self.lines() if rx.search(l)]
        return out if limit is None else out[:limit]

    def prop(self, key):
        m = re.search(r"^\[" + re.escape(key) + r"\]: \[(.*)\]\s*$", self.text("getprop"), re.M)
        return m.group(1) if m else None

    def files(self, pattern):
        return sorted(self.root.glob(pattern))


class Report:
    ORDER = {"FAIL": 0, "WARNING": 1, "UNKNOWN": 2, "PASS": 3, "INFO": 4}

    def __init__(self):
        self.items = []

    def add(self, status, area, check, summary, evidence=()):
        self.items.append({"status": status, "area": area, "check": check, "summary": summary,
                           "evidence": [str(e)[:300] for e in list(evidence)[:12]]})

    def counts(self):
        c = collections.Counter(i["status"] for i in self.items)
        return {k: c.get(k, 0) for k in ("PASS", "FAIL", "WARNING", "UNKNOWN")}

    def write(self, root, header):
        (root / "report.json").write_text(json.dumps({"header": header, "counts": self.counts(), "items": self.items},
                                                     indent=1) + chr(10), encoding="utf-8")
        md = ["# Device evidence report", ""] + [f"- {k}: {v}" for k, v in header.items()]
        c = self.counts()
        md += ["", f"**PASS {c['PASS']} / FAIL {c['FAIL']} / WARNING {c['WARNING']} / UNKNOWN {c['UNKNOWN']}**", "",
               "| Status | Area | Check | Finding |", "|---|---|---|---|"]
        for i in sorted(self.items, key=lambda i: (self.ORDER[i["status"]], i["area"])):
            md.append(f"| {i['status']} | {i['area']} | `{i['check']}` | {i['summary']} |")
        md += ["", "## Evidence", ""]
        for i in sorted(self.items, key=lambda i: (self.ORDER[i["status"]], i["area"])):
            if i["evidence"]:
                md += [f"### {i['status']}: `{i['check']}`", "", "```"] + i["evidence"] + ["```", ""]
        (root / "report.md").write_text(chr(10).join(md) + chr(10), encoding="utf-8")


def check_identity_boot(c, r):
    if not c.text("getprop"):
        r.add("UNKNOWN", "boot", "state", "no property dump in this capture: boot state, SELinux mode and identity unknown")
        return
    name, fp = c.prop("ro.product.name"), c.prop("ro.system.build.fingerprint") or c.prop("ro.build.fingerprint")
    ours = bool(name and "vantage_td" in name) or bool(fp and "vantage_td" in fp)
    r.add("PASS" if ours else "WARNING", "boot", "identity",
          f"capture is from this ROM ({fp})" if ours else f"capture is NOT from this ROM: {fp}")
    if c.prop("ro.gsid.image_running") == "1":
        r.add("INFO", "boot", "dsu", "running as a DSU guest (stock is untouched; a reboot returns to it)")
    done = c.prop("sys.boot_completed") == "1"
    r.add("PASS" if done else "FAIL", "boot", "boot_completed", "sys.boot_completed=1" if done else "boot did not complete")
    enf = c.text("getenforce").strip()
    r.add("PASS" if enf == "Enforcing" else "FAIL", "boot", "selinux_mode", f"getenforce: {enf or 'no output'}")
    starts = c.prop("sys.system_server.start_count")
    if starts:
        r.add("PASS" if starts == "1" else "FAIL", "boot", "system_server_restarts",
              "system_server started once" if starts == "1" else f"system_server was started {starts} times")
    bad = re.findall(r"^\[(init\.svc\.[^\]]+)\]: \[(restarting|stopping)\]", c.text("getprop"), re.M)
    r.add("FAIL" if bad else "PASS", "boot", "init_services",
          f"{len(bad)} init services are restarting" if bad else "no init service is in a restart loop",
          [f"{k}={v}" for k, v in bad])
    if c.grep(r"Vendor interface is incompatible", 1):
        r.add("INFO", "boot", "vintf_notice", "the log says 'Vendor interface is incompatible': expected, the vendor asks "
              "for two Qualcomm framework HALs (Wi-Fi display, telemetry) this ROM does not ship")


def check_crashes(c, r):
    procs = collections.Counter()
    samples = {}
    for line in c.grep(r"Fatal signal|FATAL EXCEPTION|^.{0,60}Process: \S+, PID|>>> \S+ <<<"):
        m = (re.search(r"pid \d+ \(([^)]+)\)\s*$", line) or re.search(r"Process: (\S+), PID", line)
             or re.search(r">>> (\S+) <<<", line))
        if m:
            name = m.group(1).rsplit("/", 1)[-1]
            procs[name] += 1
            samples.setdefault(name, line.strip())
    cam = "com.motorola.camera5"
    if 0 < procs.get(cam, 0) <= len(c.grep(KNOWN_CAMERA_RECEIVER)):
        del procs[cam]   # reported on its own as camera.package_changed_receiver
    aborts = c.grep(r"Abort message", 6)
    crit = {p: n for p, n in procs.items() if any(k in p for k in CRITICAL)}
    other = {p: n for p, n in procs.items() if p not in crit}
    if crit:
        r.add("FAIL", "crashes", "critical_processes", "crashes in: " + ", ".join(f"{p} x{n}" for p, n in sorted(crit.items())),
              [samples[p] for p in crit] + aborts)
    else:
        r.add("PASS", "crashes", "critical_processes", "no crash of audioserver, system_server, phone, IMS, the audio bridge, "
              "cameraserver or the camera app in the captured logs")
    if other:
        r.add("WARNING", "crashes", "other_processes", "crashes in: " + ", ".join(f"{p} x{n}" for p, n in sorted(other.items())),
              [samples[p] for p in other])
    if c.grep(r"a swOutput shall always be associated", 1):
        r.add("FAIL", "audio", "known_apm_abort", "the audio policy abort of the old GSI is back "
              "(TELEPHONY_PORT.md section 3): the frameworks/av source lacks setSwOutput for internal sources")
    tomb = [l for l in c.text("tombstones").splitlines() if "tombstone_" in l]
    if tomb:
        r.add("INFO", "crashes", "tombstones", f"{len(tomb)} tombstone files on the device (may predate this boot)", tomb[:6])


def check_selinux(c, r):
    groups, permissive, permissive_domains = collections.Counter(), 0, collections.Counter()
    for line in c.lines():
        m = AVC.search(line)
        if m:
            perms, src, tgt, cls, perm = m.groups()
            groups[(src, tgt, cls, perms.strip())] += 1
            permissive += perm == "1"
            if perm == "1":
                permissive_domains[src] += 1
    # TrebleDroid declares its helper domain phhsu_daemon permissive (it runs rw-system.sh at boot).
    # That is a property of the base this ROM is built on, known and reported, not a new failure.
    other = {d: n for d, n in permissive_domains.items() if d != "phhsu_daemon"}
    if other:
        r.add("FAIL", "selinux", "permissive_denials", "denials were logged with permissive=1 for: "
              + ", ".join(f"{d} x{n}" for d, n in sorted(other.items())) + ": a domain is not enforcing")
    elif permissive:
        r.add("WARNING", "selinux", "permissive_domain", f"{permissive} denials with permissive=1, all from phhsu_daemon: "
              "TrebleDroid ships that one domain permissive; everything else is enforcing")
    # Vendor-internal debug noise that the stock vendor produces under any system (seen on stock
    # and on the earlier GSI): diag router sockets and *_dbg_prop reads.
    noise = {k for k in groups if k[1] == "vendor_diag-router" or k[1].endswith("_dbg_prop")}
    rel = {k: n for k, n in groups.items() if k not in noise and (k[0] in WATCH_DOMAINS or k[1] in WATCH_DOMAINS)}

    def fmt(item):
        (src, tgt, cls, perms), n = item
        return f"{n:5d}x  {src} -> {tgt}:{cls} {{ {perms} }}"

    if rel:
        r.add("WARNING", "selinux", "denials_relevant", f"{sum(rel.values())} denials in {len(rel)} rules involve telephony, audio, "
              f"camera or core domains ({sum(groups.values())} denials in total)",
              [fmt(i) for i in sorted(rel.items(), key=lambda kv: -kv[1])[:25]])
    else:
        r.add("PASS", "selinux", "denials_relevant", f"no denial involves telephony, audio, camera or core domains "
              f"({sum(groups.values())} denials in total)", [fmt(i) for i in sorted(groups.items(), key=lambda kv: -kv[1])[:8]])


def check_radio(c, r):
    if not c.text("getprop") or not c.text("telephony-registry"):
        r.add("UNKNOWN", "radio", "state", "no property or telephony dump in this capture")
        return
    sim, oper, net = c.prop("gsm.sim.state") or "", c.prop("gsm.operator.numeric") or "", c.prop("gsm.network.type") or ""
    if "LOADED" in sim:
        r.add("PASS", "radio", "sim", f"SIM loaded (gsm.sim.state={sim})")
    else:
        r.add("WARNING" if "ABSENT" in sim else "FAIL", "radio", "sim", f"no loaded SIM (gsm.sim.state={sim or 'unset'})")
    reg = re.findall(r"Phone Id=(\d).*?mServiceState=\{mVoiceRegState=\d\((\w+)\), mDataRegState=\d\((\w+)\)",
                     c.text("telephony-registry"), re.S)
    ok = [p for p, v, d in reg if d == "IN_SERVICE"]
    r.add("PASS" if ok else "FAIL", "radio", "registration",
          (f"data registration IN_SERVICE on phone {','.join(ok)}; operator {oper}; type {net}") if ok
          else f"no phone is registered for data (operator '{oper}', type '{net}')",
          [f"phone {p}: voice {v}, data {d}" for p, v, d in reg])
    conn = c.text("connectivity")
    agents = re.findall(r"NetworkAgentInfo\{network\{(\d+)\}.*?ni\{(\w+)(?:\[(\w*)\])? (\w+) extra: ([^}]*)\}(.*)", conn)
    cell = [a for a in agents if a[1] == "MOBILE" and a[3] == "CONNECTED" and a[4].strip() != "ims"]
    wifi = [a for a in agents if a[1] == "WIFI" and a[3] == "CONNECTED"]
    if cell:
        val = "validated" if "IS_VALIDATED" in cell[0][5] else "not validated"
        r.add("PASS" if val == "validated" else "WARNING", "radio", "mobile_data",
              f"mobile data network up ({cell[0][2] or 'cellular'}, apn {cell[0][4].strip()}, {val})")
    else:
        r.add("UNKNOWN" if wifi else "FAIL", "radio", "mobile_data",
              "no mobile data network in the dump" + (" (Wi-Fi is connected: switch it off for this check)" if wifi else ""))
    ims_agent = [a for a in agents if a[4].strip() == "ims" and a[3] == "CONNECTED"]
    req = re.search(r"REQUEST[^\n]*Capabilities: [A-Z_&]*IMS[^\n]*RequestorPkg: ([\w.]+)", conn)
    r.add("PASS" if req and req.group(1) == "vantage.telephony.imsnetwork" else "WARNING", "ims", "network_request",
          f"IMS network requested by {req.group(1)}" if req else "nobody holds an IMS network request")
    r.add("PASS" if ims_agent else "WARNING", "ims", "network",
          f"IMS data network connected (transport {ims_agent[0][2] or 'cellular'})" if ims_agent else "no IMS data network")


def check_ims(c, r):
    if (c.last / "phone-ims.txt").is_file():
        bound = c.text("phone-ims").strip().splitlines()
        svc = bound[0].strip() if bound else ""
        r.add("PASS" if svc == "org.codeaurora.ims" else "FAIL", "ims", "mmtel_package",
              f"telephony's MMTel package is {svc}" if svc else "telephony has no MMTel package configured", bound[:3])
        rec = "ServiceRecord" in c.text("ims-service")
        r.add("PASS" if rec else "FAIL", "ims", "service_bound",
              "org.codeaurora.ims/.ImsService is bound" if rec else "the Qualcomm ImsService is not running")
    else:
        r.add("UNKNOWN", "ims", "service_bound", "no IMS service dump in this capture")
    ev = c.grep(r"handleImsRegistered|handleImsUnregistered")
    if not ev:
        r.add("UNKNOWN", "ims", "registration", "no IMS registration event in the captured logs (radio buffer may have rotated)")
    elif "handleImsRegistered" in ev[-1]:
        r.add("PASS", "ims", "registration", f"IMS registered ({sum('handleImsRegistered' in e for e in ev)} register, "
              f"{sum('handleImsUnregistered' in e for e in ev)} unregister events)", ev[-3:])
    else:
        r.add("FAIL", "ims", "registration", "the last IMS event is an unregistration", ev[-4:])


def check_audio_bridge(c, r):
    ok = c.grep(r"QcRilAm-Service.*request interface registered")
    bad = c.grep(r"QcRilAm-Service.*(registration failed|Could not get AIDL|did not appear|sending the response failed|"
                 r"no response interface|setError failed)")
    died = c.grep(r"QcRilAm-Service.*(died, registering again|audioserver is down)")
    slots = sorted(set(re.findall(r"IQcRilAudio/(slot\d)", " ".join(ok))))
    if ok and not bad:
        r.add("PASS", "audio", "ril_audio_bridge", f"the call-audio bridge registered with the RIL for {', '.join(slots)}", ok[-2:])
    elif bad:
        r.add("FAIL", "audio", "ril_audio_bridge", "the call-audio bridge reported errors", bad[-6:])
    else:
        r.add("UNKNOWN", "audio", "ril_audio_bridge", "no registration line from the call-audio bridge in the captured logs "
              "(it logs at boot; capture soon after boot)")
    if died:
        r.add("WARNING", "audio", "bridge_recovery", f"the RIL or audioserver went away {len(died)} times; the bridge recovered "
              "if a later registration line follows", died[-4:] + ok[-2:])
    apm = c.grep(r"no output available for internal patch sink|failed to start Telephony [RT]x AudioSource|"
                 r"patch panel could not connect device patch")
    if apm:
        r.add("FAIL", "audio", "call_patch_errors", "the audio policy manager could not set up a telephony patch", apm[-6:])


def patches(dump):
    """(source device, sink device) pairs of the device-to-device patches in an audio policy dump."""
    return re.findall(r"\[src\s+\d+\] Device Port ID: \d+; \{(AUDIO_DEVICE_IN_\w+)[^\n]*\n\s*"
                      r"\[sink\s+\d+\] Device Port ID: \d+; \{(AUDIO_DEVICE_OUT_\w+)", dump)


def check_calls(c, r):
    active = c.grep(r"CallTracker.*processCallStateChange.*state=ACTIVE|CallTracker.*fg= ?ACTIVE")
    dumps = [(p.name, p.read_text(encoding="utf-8", errors="replace")) for p in c.files("incall-*-audio-policy.txt")]
    for snap in c.snapshots:
        for name in ("audio-policy", "audio-policy-second"):
            text = c.text(name, snap)
            if text and (snap / "audio-policy-second.txt").is_file():
                dumps.append((f"{snap.name}/{name}.txt", text))
    if not active and not dumps:
        r.add("UNKNOWN", "calls", "call_observed", "no active call in this capture: call signalling and call audio were not exercised")
        return
    r.add("PASS" if active else "UNKNOWN", "calls", "call_observed",
          f"a call reached ACTIVE ({len(active)} state lines)" if active else "in-call snapshots exist but no ACTIVE line in the log",
          active[-2:])
    params = c.grep(r"setParameters.*call_state=2")
    r.add("PASS" if params else "FAIL", "audio", "ril_voice_parameters",
          "the RIL's voice-session parameters (call_state=2, vsid) reached audioserver" if params
          else "no call_state=2 parameter reached audioserver: the RIL audio bridge did not deliver the voice session", params[-2:])
    hal = c.grep(r"AHAL_Telephony\w*:.*(updateCalls|startCall|setDevices|VoiceStart|start_voice)", 8)
    if hal:
        r.add("INFO", "audio", "hal_voice_session", "vendor audio HAL telephony lines", hal)
    if not dumps:
        r.add("UNKNOWN", "audio", "call_patches", "no in-call audio policy snapshot was taken")
        return
    rx_all, tx_all, notes = False, False, []
    for name, text in dumps:
        pairs = patches(text)
        rx = [p for p in pairs if p[0] == "AUDIO_DEVICE_IN_TELEPHONY_RX"]
        tx = [p for p in pairs if p[1] == "AUDIO_DEVICE_OUT_TELEPHONY_TX"]
        src = re.search(r"Audio sources \((\d+)\)", text)
        notes.append(f"{name}: RX {rx or 'none'}; TX {tx or 'none'}; audio sources {src.group(1) if src else '?'}")
        rx_all, tx_all = rx_all or bool(rx), tx_all or bool(tx)
    status = "PASS" if rx_all and tx_all else "FAIL"
    r.add(status, "audio", "call_patches",
          "the audio policy manager created both telephony patches (downlink to the output device, microphone to uplink)"
          if status == "PASS" else f"telephony patch missing during the call (downlink: {rx_all}, uplink: {tx_all})", notes)
    r.add("UNKNOWN", "audio", "call_audible", "whether both parties could hear each other: only the tester can say")


def check_sms(c, r):
    sent = c.grep(r"SMSDispatcher.*(onSent|send complete|sendSms)|SmsDispatchersController.*sendText")
    failed = c.grep(r"SMS send failed|SMSDispatcher.*(onSendError|Sms send error|RESULT_ERROR)")
    recv = c.grep(r"InboundSmsHandler.*(Delivering SMS|dispatchSmsDeliveryIntent|processMessagePart)")
    if failed:
        r.add("FAIL", "sms", "send", "an SMS send failure is in the log", failed[-4:])
    elif sent:
        r.add("PASS", "sms", "send", f"SMS send activity without a failure line ({len(sent)} lines)", sent[-2:])
    else:
        r.add("UNKNOWN", "sms", "send", "no outgoing SMS in this capture")
    r.add("PASS" if recv else "UNKNOWN", "sms", "receive",
          f"an incoming SMS was delivered ({len(recv)} lines)" if recv else "no incoming SMS in this capture", recv[-2:])


def check_ril_ready(c, r):
    """Fourth session (2026-10-11): the RIL holds incoming SMS until it is told that telephony is ready."""
    if not is_ours(c):
        return
    sent = c.grep(r"VantageRilReady: slot [0-9]+: told the RIL that telephony is ready")
    answers = c.grep(r"VantageRilReady: slot [0-9]+: the RIL answered request [0-9]+ with error")
    rejected = [a for a in answers if "(accepted)" not in a]
    installed = "=vantage.telephony.rilready " in c.text("packages")
    if sent:
        slots = ", ".join(sorted({re.search(r"slot ([0-9]+)", l).group(1) for l in sent}))
        if rejected:
            r.add("FAIL", "sms", "ril_ready", "the RIL rejected the telephony-ready request: incoming SMS stay in the RIL",
                  rejected[:3])
        else:
            r.add("PASS", "sms", "ril_ready", f"the RIL was told that telephony is ready (slot {slots}); "
                  + (f"it accepted {len(answers)} request(s)" if answers else "no answer line in the captured log"),
                  sent[:2] + answers[:2])
    elif installed:
        # The sender logs a few lines at boot into the main buffer, which the vendor's logging
        # fills within minutes. Their absence proves nothing; a delivered SMS does, because the
        # RIL releases none before the signal.
        delivered = c.grep(r"UNSOL_INCOMING_IMS_SMS|InboundSmsHandler.*Delivering SMS", 2)
        started = c.grep(r"Start proc [0-9]+:vantage[.]telephony[.]rilready", 1)
        if delivered:
            r.add("PASS", "sms", "ril_ready", "an incoming SMS was delivered, which the RIL only does after the "
                  "telephony-ready signal; the sender's own lines are no longer in the captured log", started + delivered)
        else:
            r.add("UNKNOWN", "sms", "ril_ready", "the telephony-ready sender is installed"
                  + (" and was started at boot" if started else "") + ", but its log lines are not in this capture "
                  "(the main log buffer had rotated) and no SMS arrived: have one sent to the phone", started)
    elif c.text("packages"):
        r.add("FAIL", "sms", "ril_ready", "this image has no telephony-ready sender (it came with revision 4): the Qualcomm "
              "RIL keeps every incoming SMS to itself (telephony/ril-ready/README.md)")


def check_camera(c, r, ref):
    dump = c.text("camera")
    m = re.search(r"Number of camera devices: (\d+)", dump)
    facing = collections.Counter(re.findall(r"^\s+Facing: (\w+)", dump, re.M))
    if not m:
        r.add("UNKNOWN", "camera", "devices", "no camera service dump")
    else:
        n = int(m.group(1))
        want = None
        if ref:
            rm = re.search(r"Number of camera devices: (\d+)", ref.text("camera"))
            want = int(rm.group(1)) if rm else None
        status = "FAIL" if n == 0 else ("WARNING" if want is not None and n != want else "PASS")
        r.add(status, "camera", "devices", f"camera service lists {n} devices ({dict(facing)})"
              + (f"; stock listed {want}" if want is not None else ""))
    stub = c.grep(r"RuntimeException: Stub!", 4)
    if stub:
        # The app catches these itself (it logs the exception and carries on); they mark features that
        # depend on Motorola's framework, not a crash.
        r.add("WARNING", "camera", "motorola_stub_call", "the camera app called a Motorola framework class that this ROM "
              "only has as the app's own stub (CAMERA_PORT.md section 3); the app caught it", stub)
    opened = [p.name for p in c.files("camera-open-*.txt") if "is open" in p.read_text(encoding="utf-8", errors="replace")]
    connects = c.grep(r"CameraService.*CONNECT device.*com\.motorola\.camera5|CameraService: .*connect.*camera5")
    if opened or connects:
        r.add("PASS", "camera", "app_opened_camera", "Motorola Camera opened a camera device", opened[:3] + connects[-2:])
    else:
        r.add("UNKNOWN", "camera", "app_opened_camera", "the camera app was not used during this capture")
    errs = c.grep(r"CameraService.*(Error|rejected|failed)|CamX.*\[ERROR\].*(Sensor|probe)", 6)
    if errs and (opened or connects):
        r.add("WARNING", "camera", "service_errors", "camera service or HAL error lines while the app was in use", errs)


def is_ours(c):
    name, fp = c.prop("ro.product.name"), c.prop("ro.system.build.fingerprint") or c.prop("ro.build.fingerprint")
    return bool(name and "vantage_td" in name) or bool(fp and "vantage_td" in fp)


def check_composition(c, r):
    """Does the running guest use the image's own /system_ext and /product, and what did
    first-stage init say about the security patch level?  Only meaningful on this ROM."""
    if not is_ours(c):
        return
    kernel = [l for s in c.snapshots for l in c.text("kernel-log", s).splitlines()] + c.lines()
    skip = sorted({l[l.index("Skip mounting"):] for l in kernel if "Skip mounting mountpoint" in l})
    mounts = c.text("mounts")
    if not mounts:
        r.add("UNKNOWN", "boot", "partition_composition", "no /proc/mounts in this capture")
    else:
        rows = [l.split() for l in mounts.splitlines() if len(l.split()) >= 3]
        spots = ("/system_ext", "/product", "/system/system_ext", "/system/product")
        over = [f"{row[0]} on {row[1]} ({row[2]})" for row in rows if row[1] in spots]
        root = [f"{row[0]} on {row[1]} ({row[2]})" for row in rows if row[1] in ("/", "/system")]
        r.add("FAIL" if over else "PASS", "boot", "partition_composition",
              "a separate filesystem is mounted over the image's system_ext/product: " + ", ".join(over) if over else
              "nothing is mounted on /system_ext or /product: both come from the booted system image", root + skip)
    allowed = [l for l in kernel if "Allowing rollbacked standalone image" in l]
    detected = [l for l in kernel if "Image rollback detected" in l]
    if allowed:
        r.add("INFO", "boot", "spl_rollback", "first-stage init compared the security patch levels, reported the image as "
              "older and allowed it because the bootloader is unlocked (expected)", detected[:2] + allowed[:1])
    elif detected:
        r.add("WARNING", "boot", "spl_rollback", "first-stage init reported an image rollback without the 'allowing' line",
              detected[:3])
    else:
        r.add("INFO", "boot", "spl_rollback", "no first-stage init message about the security patch level in the captured "
              "kernel log (not readable, or already rotated out): not observed either way")
    listing = c.text("overlays")
    if listing:
        enabled, target = collections.defaultdict(set), None
        for line in listing.splitlines():
            if line and line[0] not in "[-":
                target = line.strip()
            elif line.startswith("[x] ") and target:
                enabled[target].add(line[4:].strip())
        want = {"com.android.phone": "com.android.phone.overlay.vantage", "android": "android.overlay.vantage.telephony",
                "com.android.carrierconfig": "com.android.carrierconfig.overlay.vantage"}
        missing = [o for t, o in want.items() if o not in enabled[t]]
        rivals = sorted(o for o in enabled["com.android.phone"]
                        if o.startswith("me.phh.treble.overlay.") and o.endswith("ims_telephony") and "cafims" not in o)
        r.add("FAIL" if missing or rivals else "PASS", "boot", "overlays_active",
              ("not enabled: " + ", ".join(missing) + ". " if missing else "") +
              ("a TrebleDroid IMS overlay for another vendor is enabled: " + ", ".join(rivals) if rivals else "")
              if missing or rivals else "this ROM's three overlays are enabled and no other vendor's IMS overlay is",
              sorted(enabled["com.android.phone"]))


def check_first_boot_findings(c, r):
    """Failures seen on the first DSU boot (2026-10-10); each is recognised by its own log line."""
    if not is_ours(c):
        return
    raf = c.grep(r"setAllowedNetworkTypes: modemRafBitMask")
    if raf:
        last = raf[-1]
        sent = last.split("filteredRaf = ")[-1].strip() if "filteredRaf = " in last else ""
        ok = "LTE" in sent or "NR" in sent
        r.add("PASS" if ok else "FAIL", "radio", "allowed_network_types",
              f"the modem is allowed to use {sent}" if ok else
              f"the modem is restricted to {sent}: no LTE/NR, so no service on an LTE/NR-only network "
              "(ro.telephony.default_network missing, or a 2G/3G network type chosen in Settings)", raf[-1:])
    dev = c.prop("ro.product.device")
    if dev:
        r.add("PASS" if dev == "vantage" else "FAIL", "boot", "device_identity",
              f"ro.product.device={dev}, ro.product.name={c.prop('ro.product.name')}, model {c.prop('ro.product.model')}; "
              f"the vendor derived ro.vendor.product.device={c.prop('ro.vendor.product.device')}" +
              ("" if dev == "vantage" else ": not the stock identity the vendor and Motorola Camera expect"))
    web = c.grep(r"No WebView installed|Could not find a loadable WebView package", 3)
    if web:
        r.add("FAIL", "boot", "webview", "no usable WebView provider (apps that embed web content cannot start)", web)
    cfg = c.grep(r"JsonConfig: Parse json file\(config_device\) for .* failed", 2)
    if cfg:
        r.add("FAIL", "camera", "device_config", "Motorola Camera found no configuration for this device name and refuses to run", cfg)
    ext_ok = c.grep(r"VantageAudioVendorExt: stock vendor extension registered", 1)
    ext_bad = c.grep(r"VantageAudioVendorExt: (cannot load|.* has no |.* returned without registering)|"
                     r"Audio_ParameterParser: (Failed|failed)", 4)
    if ext_bad:
        r.add("FAIL", "audio", "vendor_extension", "the audio vendor-parameter extension did not register: call parameters "
              "(vsid, call_state) will not reach the audio HAL", ext_bad)
    elif ext_ok:
        r.add("PASS", "audio", "vendor_extension", "the stock audio vendor-parameter extension is registered", ext_ok)
    stuck = c.grep(r"QcRilAm-Service.*setRequestInterface has not returned", 2)
    calling = c.grep(r"QcRilAm-Service.*calling setRequestInterface")
    done = c.grep(r"QcRilAm-Service.*request interface registered")
    if stuck or (calling and not done):
        r.add("FAIL", "audio", "bridge_blocked", "the call-audio bridge is waiting inside the RIL's setRequestInterface call "
              f"({len(calling)} attempts, {len(done)} completed): the RIL cannot route call audio requests", (stuck or calling)[:3])


KNOWN_CAMERA_RECEIVER = r"Unable to start receiver com[.]motorola[.]camera[.]PackageChangeReceiver: java[.]lang[.]UnsupportedOperationException"


def check_third_boot_findings(c, r):
    """Failures seen in the third DSU session (2026-10-10); each is recognised by its own log line."""
    if not is_ours(c):
        return
    # The ProfileSelector warning alone is harmless (the app then takes the closest profile, seen on
    # the second boot); the failure is the exception when the camera has no profile at all.
    prof = c.grep(r"MediaRecorderData[.]mVideoFrameSize", 3)
    mine, vendor = c.prop("ro.media.xml_variant.profiles"), c.prop("ro.media.xml_variant.codecs")
    state = f"ro.media.xml_variant.profiles={mine or 'unset'}, vendor variant {vendor or 'unset'}"
    if prof:
        r.add("FAIL", "camera", "video_profiles", "Motorola Camera found no camcorder profile for its camera in video mode "
              f"and stops there ({state}; unset means libmedia read media_profiles_V1_0.xml, which knows 2 cameras)", prof)
    elif vendor:
        ok = mine == vendor
        r.add("PASS" if ok else "FAIL", "camera", "video_profiles",
              f"camcorder profiles come from the file stock reads ({state})" if ok else
              f"libmedia does not read the profile file stock reads ({state})")
    lut = c.grep(r"attempted to close file descriptor [0-9]+, expected to be unowned|LutShader::lutShader", 4)
    if lut:
        r.add("FAIL", "display", "screenshot_lut", "surfaceflinger aborted while taking a screenshot or task snapshot of an HDR "
              "layer (android-16.0.0_r2 closes the layer LUT descriptor twice; patches/frameworks/native)", lut)
    xtra = c.grep(r"XTRA Failed to register w QCC-V", 2)
    if xtra:
        r.add("FAIL", "location", "xtra_daemon", "the GNSS XTRA daemon gave up waiting for Qualcomm's QCC service and exits: "
              "it can read the vendor-framework flag, which only the camera HAL should see", xtra)
    if c.text("getprop"):
        flag = c.prop("ro.vendor.qti.va_aosp.support")
        r.add("PASS" if flag == "1" else "WARNING", "camera", "vendor_framework_flag",
              "ro.vendor.qti.va_aosp.support=1 (from revision 3 only the camera HAL and the shell can read it)" if flag == "1" else
              "ro.vendor.qti.va_aosp.support is not in the property dump: not set (the camera HAL then loads its 2-camera "
              "GSI configuration), or an image before revision 3, where the shell could not read it; camera.devices decides")
    recv = c.grep(KNOWN_CAMERA_RECEIVER, 2)
    if recv:
        r.add("WARNING", "camera", "package_changed_receiver", "known and not fixed: about 30 s after boot the TrebleDroid app "
              "announces the IMS package with an empty component list, Motorola Camera's receiver does not expect an empty "
              "list, and the idle camera process is killed once; the app starts normally afterwards", recv)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture")
    ap.add_argument("--reference", help="a capture taken on stock, used for comparisons (camera device count)")
    args = ap.parse_args()
    c = Capture(args.capture)
    ref = Capture(args.reference) if args.reference else None
    r = Report()
    for check in (check_identity_boot, check_composition, check_first_boot_findings, check_third_boot_findings, check_crashes, check_selinux, check_radio, check_ims, check_audio_bridge,
                  check_calls, check_sms, check_ril_ready):
        check(c, r)
    check_camera(c, r, ref)
    header = {"capture": str(c.root), "kind": "session" if c.is_session else "snapshot",
              "build": c.prop("ro.system.build.fingerprint") or c.prop("ro.build.fingerprint") or "unknown",
              "vendor": c.prop("ro.vendor.build.fingerprint") or "unknown", "log lines": len(c.lines())}
    r.write(c.root, header)
    counts = r.counts()
    print(f"PASS {counts['PASS']}  FAIL {counts['FAIL']}  WARNING {counts['WARNING']}  UNKNOWN {counts['UNKNOWN']}")
    for i in sorted(r.items, key=lambda i: Report.ORDER[i["status"]]):
        if i["status"] in ("FAIL", "WARNING", "UNKNOWN"):
            print(f"  [{i['status']:7s}] {i['area']}.{i['check']}: {i['summary'][:170]}")
    print(f"report: {c.root / 'report.md'}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
