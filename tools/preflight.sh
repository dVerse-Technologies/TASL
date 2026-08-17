#!/usr/bin/env bash
# =============================================================================
#  TASL preflight check - macOS (event day machine)
#
#  Run this BEFORE plugging in ESP32s, and again as the first thing you do
#  after joining the venue router.
#
#      bash tools/preflight.sh
#
#  It only reads state. It changes nothing - it prints the commands you need
#  if something is wrong.
# =============================================================================

PORT=8000
problems=()

# Colours, but only when writing to a real terminal.
if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; D=$'\033[90m'; N=$'\033[0m'
else
  R=""; G=""; Y=""; C=""; D=""; N=""
fi

echo
echo "${C}==================== TASL PREFLIGHT (macOS) ====================${N}"
echo

# ------------------------------------------------------------------ 1. IP ---
echo "1. This Mac's IP address"

# The interface carrying the default route is the one that matters. Guessing
# "en0" breaks on Macs with dongles, Thunderbolt bridges or USB Ethernet.
IFACE=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
LAN_IP=""

if [ -n "$IFACE" ]; then
  LAN_IP=$(ipconfig getifaddr "$IFACE" 2>/dev/null)
fi

if [ -n "$LAN_IP" ]; then
  SVC=$(networksetup -listallhardwareports 2>/dev/null \
        | awk -v d="$IFACE" '/Hardware Port/{p=$0} $2==d{print p}' \
        | sed 's/Hardware Port: //')
  echo "   ${G}${LAN_IP}${N}   ${IFACE}  (${SVC:-unknown})   ${G}<-- use this in the firmware${N}"
else
  echo "   ${R}Could not determine a LAN IP.${N}"
  problems+=("No IP address on the default route - is Wi-Fi connected?")
fi

# Show the others for context, so a Thunderbolt bridge address doesn't confuse.
for i in $(ifconfig -l); do
  [ "$i" = "$IFACE" ] && continue
  ip=$(ipconfig getifaddr "$i" 2>/dev/null)
  [ -n "$ip" ] && echo "   ${D}${ip}   ${i}  (not the LAN route - ignore)${N}"
done

# ------------------------------------------------------------ 2. firewall ---
echo
echo "2. Firewall"

FW="/usr/libexec/ApplicationFirewall/socketfilterfw"
if [ -x "$FW" ]; then
  STATE=$("$FW" --getglobalstate 2>/dev/null)
  if echo "$STATE" | grep -qi "disabled"; then
    echo "   ${G}OFF - nothing blocking incoming connections.${N}"
  else
    echo "   ${Y}ON${N} - macOS firewall is per-application, not per-port."
    echo "   ${D}Python must be allowed to accept incoming connections.${N}"

    BLOCKALL=$("$FW" --getblockall 2>/dev/null)
    if echo "$BLOCKALL" | grep -qi "on"; then
      echo "   ${R}BLOCK ALL INCOMING is ON - nodes cannot reach the server.${N}"
      problems+=("Firewall 'Block all incoming connections' is ON. Turn it off.")
    fi

    PY=$(command -v python3)
    if [ -n "$PY" ]; then
      REAL=$(python3 -c 'import sys; print(sys.executable)' 2>/dev/null)
      if "$FW" --getappblocked "$REAL" 2>/dev/null | grep -qi "blocked"; then
        echo "   ${R}python3 is BLOCKED from incoming connections.${N}"
        problems+=("python3 is blocked by the firewall.")
      else
        echo "   ${D}python3: $REAL${N}"
      fi
    fi
    echo "   ${D}If a dialog appears when you start the server, click ALLOW.${N}"
  fi
else
  echo "   ${D}(socketfilterfw not found - unusual, skipping)${N}"
fi

# ----------------------------------------------------------- 3. Wi-Fi band --
echo
echo "3. Wi-Fi"

# The old 'airport' binary was removed in macOS 14.4, so parse system_profiler.
AIR=$(system_profiler SPAirPortDataType 2>/dev/null)
if [ -n "$AIR" ]; then
  SSID=$(echo "$AIR" | awk '/Current Network Information:/{getline; gsub(/^[ \t]+|:$/,""); print; exit}')
  CHAN=$(echo "$AIR" | awk '/Current Network Information:/,/Status:/' | awk -F': ' '/Channel:/{print $2; exit}')
  echo "   SSID    : ${SSID:-unknown}"
  echo "   Channel : ${CHAN:-unknown}"
  case "$CHAN" in
    *5GHz*|*"5 GHz"*)
      echo "   ${Y}NOTE: this Mac is on 5 GHz. ESP32s are 2.4 GHz only.${N}"
      echo "   ${D}That is usually fine if both bands share one subnet, but joining${N}"
      echo "   ${D}the 2.4 GHz SSID removes any doubt.${N}"
      ;;
    *2GHz*|*2.4*)
      echo "   ${G}2.4 GHz - same band as the nodes.${N}"
      ;;
  esac
else
  echo "   ${D}(not on Wi-Fi, or airport data unavailable)${N}"
fi

# -------------------------------------------------------------- 4. python ---
echo
echo "4. Python"
if command -v python3 >/dev/null 2>&1; then
  echo "   ${G}$(python3 --version 2>&1)${N}"
  if python3 -c "import fastapi, uvicorn, pydantic" >/dev/null 2>&1; then
    echo "   ${G}fastapi / uvicorn / pydantic installed${N}"
  else
    echo "   ${R}dependencies missing${N}"
    problems+=("Python dependencies not installed. Run: python3 -m pip install -r requirements.txt")
  fi
else
  echo "   ${R}python3 not found${N}"
  problems+=("Python 3 is not installed. Install from python.org or 'brew install python'.")
fi

# -------------------------------------------------------------- 5. server ---
echo
echo "5. Dashboard server"
if curl -s -m 2 "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
  echo "   ${G}RUNNING on port $PORT${N}"
else
  echo "   ${Y}NOT RUNNING - start it with 'python3 run_server.py'${N}"
fi

# -------------------------------------------------------------- summary -----
echo
echo "${C}================================================================${N}"
if [ ${#problems[@]} -eq 0 ]; then
  echo " ${G}READY. Nodes should be able to reach this Mac.${N}"
  if [ -n "$LAN_IP" ]; then
    echo
    echo " Confirm the firmware's SERVER_IP is:  ${G}${LAN_IP}${N}"
    echo " ${D}If it is not, every node will silently fail to report.${N}"
  fi
else
  echo " ${R}${#problems[@]} PROBLEM(S) TO FIX:${N}"
  for p in "${problems[@]}"; do echo "   ${R}- $p${N}"; done
fi
echo
