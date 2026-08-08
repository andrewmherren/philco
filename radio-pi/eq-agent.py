#!/usr/bin/env python3
# MQTT-controlled ALSA EQ agent for the philco radio. Applies band-gain
# changes to the `equal` LADSPA plugin (see /etc/asound.conf) via amixer,
# and keeps them in a local state file so the radio's EQ settings survive
# independently of MQTT broker/network availability at boot -- same
# "must be self-sufficient after a year untouched" reasoning as the rest
# of this Pi's setup. Uses connect_async()+loop_forever(retry_first_
# connection=True) so it keeps retrying the initial connection if the
# broker isn't up yet at boot.
#
# Also periodically re-applies the stored state (see REAPPLY_INTERVAL_
# SECONDS below) as a safety net -- a user reported EQ settings appearing
# reset after a Pi reboot; state.json and the boot-time apply both looked
# correct on inspection, so the periodic re-apply exists to bound how
# long any such drift (from this or an unconfirmed cause) can last,
# rather than relying on a single one-shot apply at startup being final.
#
# IMPORTANT: alsaequal's LADSPA host keeps its live band-gain state in a
# file at $HOME/.alsaequal.bin -- NOT in the ALSA config or anywhere
# global. That means this agent only actually controls what go-librespot
# hears if both processes resolve the same $HOME. This is deliberately
# arranged on the radio Pi: go-librespot.service and this unit both run
# as root with HOME=/root. See AGENT_SCRATCHPAD.md for the full story.
import json
import os
import subprocess
import threading

import paho.mqtt.client as mqtt

TOPIC_SET_PREFIX = "philco/eq/set"
TOPIC_STATE_PREFIX = "philco/eq/state"
STATE_FILE = "/var/lib/philco-eq/state.json"
AMIXER_DEVICE = "eq"

# Belt-and-suspenders: periodically re-apply the stored state in case
# something outside our control (e.g. alsaequal's shared gain-state file
# possibly being touched by the first real PCM open after boot) resets
# the live values independently of this agent. Cheap no-op if nothing
# changed; bounds how long any such reset could last to one interval.
REAPPLY_INTERVAL_SECONDS = 60

# numid order confirmed via `amixer -D eq controls` after installing
# libasound2-plugin-equal 0.6-8 -- do not reorder without reconfirming,
# alsaequal doesn't guarantee numid stability across package versions.
BAND_NUMID = {
    "31": 1,
    "63": 2,
    "125": 3,
    "250": 4,
    "500": 5,
    "1k": 6,
    "2k": 7,
    "4k": 8,
    "8k": 9,
    "16k": 10,
}
GAIN_MIN = 0
GAIN_MAX = 100
GAIN_DEFAULT = 66  # confirmed flat/0dB position via `amixer -D eq contents`


def load_env(path):
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key] = value
    return env


env = load_env("/etc/philco-mqtt/.env")
MQTT_HOST = env.get("MQTT_HOST", "homeassistant.local")
MQTT_PORT = int(env.get("MQTT_PORT", "1883"))
MQTT_USERNAME = env.get("MQTT_USERNAME")
MQTT_PASSWORD = env.get("MQTT_PASSWORD")

mqtt_client = mqtt.Client(client_id="philco-radio-eq-agent")
if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {band: data.get(band, GAIN_DEFAULT) for band in BAND_NUMID}
        except (ValueError, OSError) as e:
            print(f"Failed to read {STATE_FILE}, falling back to flat: {e}")
    return {band: GAIN_DEFAULT for band in BAND_NUMID}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f)
    os.replace(tmp_path, STATE_FILE)


def apply_band(band, gain):
    numid = BAND_NUMID[band]
    subprocess.run(
        ["amixer", "-D", AMIXER_DEVICE, "cset", f"numid={numid}", f"{gain},{gain}"],
        check=True,
        capture_output=True,
    )


state = load_state()


def apply_all_state():
    for band, gain in state.items():
        try:
            apply_band(band, gain)
        except subprocess.CalledProcessError as e:
            print(f"Failed to apply band {band}={gain}: {e.stderr.decode().strip()}")


def periodic_reapply():
    apply_all_state()
    threading.Timer(REAPPLY_INTERVAL_SECONDS, periodic_reapply).start()


print("Applying stored EQ state before connecting to MQTT")
apply_all_state()
threading.Timer(REAPPLY_INTERVAL_SECONDS, periodic_reapply).start()


def publish_all_state():
    for band, gain in state.items():
        mqtt_client.publish(f"{TOPIC_STATE_PREFIX}/{band}", str(gain), retain=True)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected")
        client.subscribe(f"{TOPIC_SET_PREFIX}/+")
        publish_all_state()
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def on_message(client, userdata, msg):
    band = msg.topic.rsplit("/", 1)[-1]
    if band not in BAND_NUMID:
        return
    try:
        gain = round(float(msg.payload.decode().strip()))
    except ValueError:
        print(f"Ignoring non-numeric payload for band {band}: {msg.payload!r}")
        return
    gain = max(GAIN_MIN, min(GAIN_MAX, gain))

    try:
        apply_band(band, gain)
    except subprocess.CalledProcessError as e:
        print(f"Failed to apply band {band}={gain}: {e.stderr.decode().strip()}")
        return

    state[band] = gain
    save_state(state)
    client.publish(f"{TOPIC_STATE_PREFIX}/{band}", str(gain), retain=True)


mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
mqtt_client.loop_forever()
