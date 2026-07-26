#!/bin/bash
# Opens a bounded Bluetooth pairing window on this radio. Discoverable and
# pairable auto-revert to off after DiscoverableTimeout/PairableTimeout in
# /etc/bluetooth/main.conf (120s) expire -- BlueZ handles the revert itself,
# this script only needs to flip them on and make sure the pairing agent is
# actually running to accept the request when it comes in.
set -euo pipefail

systemctl is-active --quiet bt-agent || systemctl restart bt-agent

bluetoothctl <<BT
power on
discoverable on
pairable on
BT

echo "Pairing window open for 120s (PIN 1111 auto-accepted). Devices already paired can reconnect any time without this."
