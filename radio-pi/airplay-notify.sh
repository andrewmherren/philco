#!/bin/bash
# Invoked via sudo by shairport-sync's run_this_before_play_begins /
# run_this_after_play_ends hooks (see /etc/shairport-sync.conf), which
# run as the unprivileged shairport-sync user and so have no access to
# MQTT credentials (/etc/philco-mqtt/.env is root-only, deliberately not
# opened up to shairport-sync's own user the way /root/.alsaequal.bin
# was via ACL for EQ access -- these are different kinds of secrets).
# This narrowly-scoped root-owned script is the only bridge between the
# two. See /etc/sudoers.d/philco-airplay for the exact grant (this
# script, these two exact arguments, nothing else) and AGENT_SCRATCHPAD.md
# for the full picture.
set -euo pipefail

STATE="$1"  # "playing" or "stopped"

set -a
source /etc/philco-mqtt/.env
set +a

mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
  -t philco/audio/airplay/active -m "$STATE"
