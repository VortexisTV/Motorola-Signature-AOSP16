#!/usr/bin/env bash
# Record one test session on the phone and analyse it, so that each manual action has to be
# done only once.
#
#   ADB=/h/androidtools/platform-tools/adb.exe bash device-session.sh [minutes]
#
# Read-only towards the phone: properties, dumpsys and logcat are read. It never dials, sends,
# installs, reboots or changes a setting. What it does:
#   1. waits until the phone has finished booting;
#   2. saves the boot log and takes a full snapshot (collect-device-evidence.sh);
#   3. keeps recording all log buffers and watches the call state and the foreground app;
#      when a call becomes active it saves the audio routing twice (a few seconds in, and
#      15 s later), when Motorola Camera is in front it saves the camera service state;
#   4. on Enter (or after [minutes], default 30) takes a final snapshot and writes
#      report.md / report.json with analyze_device_evidence.py.
# The output contains personal data and goes to work/device-evidence/, which git ignores.
set -uo pipefail
export MSYS_NO_PATHCONV=1

ADB="${ADB:-adb}"
MINUTES="${1:-30}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
OUT="${OUT_DIR:-$ROOT/work/device-evidence}/$(date +%Y%m%d-%H%M%S)-session"
PY="${PYTHON:-python}"; command -v "$PY" > /dev/null 2>&1 || PY=python3
mkdir -p "$OUT/snapshots"

dsh() { "$ADB" shell "$@" 2> /dev/null | tr -d '\r'; }
event() { echo "$(date +%H:%M:%S) $*" | tee -a "$OUT/events.txt"; }
save() { "$ADB" shell "$2" > "$OUT/$1.txt" 2>&1; }

echo "waiting for the phone (adb) ..."
"$ADB" wait-for-device
# Started on stock with a DSU guest installed and not yet booted: wait for the guest, so that the
# recording begins with its first log lines (start this script, then tap Restart on the phone).
if [ "$(dsh gsi_tool status | head -n 1)" = "installed" ]; then
  echo "stock is running and a guest is installed: tap Restart in the DSU notification now"
  t0=$(date +%s)
  until [ "$(dsh gsi_tool status | head -n 1)" = "running" ]; do
    [ $(( $(date +%s) - t0 )) -lt 900 ] || { event "the guest did not appear within 15 minutes; recording what is running"; break; }
    sleep 2
  done
fi
# Stream the log from the first moment adb answers. The buffers of a booting system rotate
# within a minute; services that only talk at start-up (camera provider, RIL audio bridge)
# were missing from the first two recordings because the dump was taken after boot.
"$ADB" logcat -b all -v threadtime > "$OUT/logcat-early.txt" 2>&1 &
EARLYPID=$!
t0=$(date +%s)
until [ "$(dsh getprop sys.boot_completed)" = "1" ]; do
  [ $(( $(date +%s) - t0 )) -lt 600 ] || { event "boot did not complete within 10 minutes"; break; }
  sleep 3
done
event "boot_completed=$(dsh getprop sys.boot_completed) after waiting $(( $(date +%s) - t0 )) s; build $(dsh getprop ro.build.fingerprint)"

"$ADB" logcat -b all -d > "$OUT/logcat-boot.txt" 2>&1
"$ADB" logcat -b all -v threadtime -T 1 > "$OUT/logcat-live.txt" 2>&1 &
LOGPID=$!
trap 'kill $LOGPID $EARLYPID 2> /dev/null' EXIT
ADB="$ADB" bash "$HERE/collect-device-evidence.sh" start "$OUT/snapshots" > /dev/null
event "start snapshot taken"

# First report, before any manual action: boot, crashes, SELinux, SIM, registration, IMS, bridge.
REF="$(ls -d "$ROOT"/work/device-evidence/*-stock-idle 2> /dev/null | tail -n 1)"
echo
echo "---- state right after boot (nothing has been exercised yet) ----"
if env -u MSYS_NO_PATHCONV "$PY" -X utf8 "$HERE/analyze_device_evidence.py" "$OUT" ${REF:+--reference "$REF"}; then
  cp "$OUT/report.md" "$OUT/report-boot.md"
else
  cp "$OUT/report.md" "$OUT/report-boot.md" 2> /dev/null
  echo
  echo "There are FAIL lines above. They are worth reading before spending time on calls:"
  echo "a crash loop or a missing IMS service will not be fixed by testing further."
fi
echo "------------------------------------------------------------------"

cat << MSG

Recording. Do each of these ONCE, in this order, then press Enter here:
  1. Wi-Fi off; open a web page (mobile data)
  2. send one SMS to the second phone, have it reply
  3. call the second phone, answer there; after about 5 s switch to the speaker;
     keep the call up for 25 s in total; say something both ways; hang up
  4. have the second phone call this one; answer; 10 s; hang up
  5. open Motorola Camera; take one photo with each lens; record 10 s of video
(press Enter when done; stops by itself after $MINUTES minutes)

MSG

deadline=$(( $(date +%s) + MINUTES * 60 ))
prev=0; calls=0; shot_a=0; shot_b=0; cams=0; cam_prev=0; tick=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  if [ -t 0 ]; then read -r -t 2 _ && break; else sleep 2; fi
  tick=$(( tick + 1 ))
  cs=$(dsh dumpsys telephony.registry | grep -o "mCallState=[0-9]" | sort -u | tail -n 1 | cut -d= -f2)
  cs=${cs:-0}
  if [ "$cs" != "$prev" ]; then
    case "$cs" in
      1) event "call state RINGING" ;;
      2) calls=$(( calls + 1 )); shot_a=$(( tick + 2 )); shot_b=$(( tick + 9 )); event "call $calls ACTIVE (off-hook)" ;;
      0) event "call ended"; shot_a=0; shot_b=0 ;;
    esac
    prev=$cs
  fi
  for which in a b; do
    due=$shot_a; [ $which = b ] && due=$shot_b
    if [ "$due" != 0 ] && [ "$tick" -ge "$due" ] && [ "$cs" = 2 ]; then
      save "incall-$calls-$which-audio-policy" "dumpsys media.audio_policy"
      save "incall-$calls-$which-audio-flinger" "dumpsys media.audio_flinger"
      save "incall-$calls-$which-telephony-registry" "dumpsys telephony.registry"
      event "in-call snapshot $calls-$which saved"
      [ $which = a ] && shot_a=0 || shot_b=0
    fi
  done
  if [ $(( tick % 3 )) = 0 ]; then
    cam=0; dsh dumpsys activity activities | grep -m 1 -E "ResumedActivity|topResumedActivity" | grep -q "com.motorola.camera5" && cam=1
    if [ $cam = 1 ] && [ $cam_prev = 0 ]; then
      cams=$(( cams + 1 )); sleep 3
      save "camera-open-$cams" "dumpsys media.camera"
      event "Motorola Camera in front: camera snapshot $cams saved"
    fi
    cam_prev=$cam
  fi
done

event "stopping"
kill $LOGPID $EARLYPID 2> /dev/null
ADB="$ADB" bash "$HERE/collect-device-evidence.sh" end "$OUT/snapshots" > /dev/null
# Git Bash must translate the paths for a Windows Python; the adb calls above must not.
env -u MSYS_NO_PATHCONV "$PY" -X utf8 "$HERE/analyze_device_evidence.py" "$OUT" ${REF:+--reference "$REF"}
echo "session directory: $OUT"
