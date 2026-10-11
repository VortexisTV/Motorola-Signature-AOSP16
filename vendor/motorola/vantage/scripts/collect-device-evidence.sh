#!/usr/bin/env bash
# Collect read-only evidence from a running phone (stock or this ROM) for TESTING.md.
#
#   ADB=/h/androidtools/platform-tools/adb.exe bash collect-device-evidence.sh <label> [outdir]
#
# <label> names the moment, e.g. boot, incall, camera. Only state is read (getprop, dumpsys,
# logcat -d, ls); nothing is written to the device. The output contains personal data (phone
# number, subscriber identifiers, logs): it goes to work/device-evidence/, which git ignores.
#
# In-call reference (stock or this ROM): the script never dials. Start it with WAIT_CALL=1,
# then place or answer a call yourself:
#
#   WAIT_CALL=1 ADB=... bash collect-device-evidence.sh incall
#
# It polls the call state (read-only) for up to WAIT_CALL_MINUTES (default 15), captures a few
# seconds after the call is active, and takes a second audio snapshot 15 s later, so switching
# to the speaker in between records both routes.
set -uo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash must not rewrite device paths such as /data/tombstones

ADB="${ADB:-adb}"
LABEL="${1:?usage: collect-device-evidence.sh <label> [outdir]}"
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
OUT="${2:-$ROOT/work/device-evidence}/$(date +%Y%m%d-%H%M%S)-$LABEL"

[ "$("$ADB" get-state 2>/dev/null | tr -d '\r')" = "device" ] || { echo "no device in adb state 'device'"; exit 1; }
mkdir -p "$OUT"

run() {  # run <file> <device shell command...>
  local name="$1"; shift
  "$ADB" shell "$@" > "$OUT/$name.txt" 2>&1 || echo "(exit status $? from: $*)" >> "$OUT/$name.txt"
}

call_active() { "$ADB" shell dumpsys telephony.registry 2>/dev/null | grep -q "mCallState=2"; }

if [ "${WAIT_CALL:-0}" != "0" ]; then
  echo "waiting for an active call; place or answer it on the phone (this script does not dial)"
  deadline=$(( $(date +%s) + ${WAIT_CALL_MINUTES:-15} * 60 ))
  until call_active; do
    [ "$(date +%s)" -lt "$deadline" ] || { echo "no active call within the time limit"; rmdir "$OUT" 2>/dev/null; exit 2; }
    sleep 2
  done
  echo "call active; capturing"
  sleep 4
fi

run getprop            getprop
run getenforce         getenforce
run mounts             cat /proc/mounts
run kernel-log         dmesg          # first-stage init messages; not readable on user builds
run telephony-registry dumpsys telephony.registry
run carrier-config     dumpsys carrier_config
run connectivity       dumpsys connectivity
run ims-service        dumpsys activity services org.codeaurora.ims
run phone-ims          "cmd phone ims get-ims-service -s 0 -c; cmd phone ims get-ims-service -s 0 -d"
run audio-policy       dumpsys media.audio_policy
run audio-flinger      dumpsys media.audio_flinger
run camera             dumpsys media.camera
run overlays           cmd overlay list
run packages           pm list packages -f -U
run tombstones         ls -l /data/tombstones
if [ "${WAIT_CALL:-0}" != "0" ]; then
  echo "second audio snapshot in 15 s (switch to the speaker now if you want both routes recorded)"
  sleep 15
  if call_active; then
    run audio-policy-second  dumpsys media.audio_policy
    run audio-flinger-second dumpsys media.audio_flinger
  else
    echo "call ended before the second snapshot"
  fi
fi
"$ADB" logcat -b all -d > "$OUT/logcat-all.txt" 2>&1

# Short extracts that answer the usual first questions.
grep -E "avc: +denied" "$OUT/logcat-all.txt" > "$OUT/avc-denials.txt" || true
grep -E "FATAL EXCEPTION|Fatal signal|Abort message|VantageImsNetwork|ImsResolver|handleImsRegistered|handleImsUnregistered" \
    "$OUT/logcat-all.txt" > "$OUT/highlights.txt" || true
grep -E "NetworkRequest.*Capabilities: [A-Z_&]*IMS|NetworkAgentInfo.*extra: ims" "$OUT/connectivity.txt" \
    > "$OUT/ims-network.txt" || true

echo "written: $OUT"
ls -l "$OUT" | awk '{print $5, $NF}' | tail -n +2
