#!/usr/bin/env python3
# Bridges the physical volume knob (philco-ui) to go-librespot's own
# volume, over MQTT. Deliberately one-directional and Spotify-only:
# - Knob -> here -> POST http://127.0.0.1:3678/player/volume. Applied
#   directly to go-librespot's internal volume, which pre-multiplies its
#   own audio samples in software by default (external_volume: false,
#   the go-librespot default) -- so this is the actual effective Spotify
#   volume, not a separate stage that needs reconciling with anything.
# - The Spotify app's own volume control reaches go-librespot directly
#   via the Connect protocol -- no bridging needed for that direction,
#   and no "who wins" logic needed either: both inputs just write the
#   same single piece of state in go-librespot, so whichever changed it
#   last is already what's in effect. See AGENT_SCRATCHPAD.md for why
#   this turned out much simpler than first planned.
# AirPlay/Bluetooth volume is deliberately left untouched -- their own
# protocol-level remote volume stays in charge, independent of this.
import os

import paho.mqtt.client as mqtt
import requests

TOPIC_SET = "philco/spotify/volume/set"
VOLUME_API_URL = "http://127.0.0.1:3678/player/volume"
VOLUME_MIN = 0
VOLUME_MAX = 100


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

mqtt_client = mqtt.Client(client_id="philco-radio-spotify-volume-agent")
if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected")
        client.subscribe(TOPIC_SET)
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def on_message(client, userdata, msg):
    try:
        volume = round(float(msg.payload.decode().strip()))
    except ValueError:
        print(f"Ignoring non-numeric volume payload: {msg.payload!r}")
        return
    volume = max(VOLUME_MIN, min(VOLUME_MAX, volume))

    try:
        requests.post(VOLUME_API_URL, json={"volume": volume, "relative": False}, timeout=2)
    except requests.RequestException as e:
        print(f"Failed to set go-librespot volume to {volume}: {e}")


mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
mqtt_client.loop_forever()
