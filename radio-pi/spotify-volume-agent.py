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
#
# Debounces rapid-fire knob movement (a smooth turn can generate many MQTT
# messages in quick succession) and retries transient failures -- found
# go-librespot's local API can itself become temporarily unresponsive
# (`Read timed out`) under a burst of rapid requests, silently dropping
# both volume-set and pause calls with no fallback. Debouncing reduces
# how often that burst happens in the first place; retrying covers
# whatever transient failures still occur.
import threading
import time
import os

import paho.mqtt.client as mqtt
import requests

TOPIC_SET = "philco/spotify/volume/set"
VOLUME_API_URL = "http://127.0.0.1:3678/player/volume"
STOP_API_URL = "http://127.0.0.1:3678/player/stop"
VOLUME_MIN = 0
VOLUME_MAX = 100
DEBOUNCE_SECONDS = 0.15
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5

# Must match server.js/station-agent.py's own off-threshold. Uses
# /player/stop (not /player/pause) as of 2026-07-31, per explicit user
# request: volume-off should fully stop Spotify, not just silence it. An
# earlier version of this comment warned that /player/stop disconnects
# the whole Spotify Connect session, requiring a phone to manually
# re-select "philco" as output again -- confirmed live this concern
# doesn't actually apply here:
# station-agent.py's reassert_current_region() (fired on the matching
# off->on transition) calls /player/play with an explicit uri, which
# works fine even after a full stop and is the same mechanism that
# already made the radio "take over" Spotify playback from another
# device before this change -- that takeover was never actually
# dependent on the session merely being paused vs fully stopped.
VOLUME_OFF_THRESHOLD = 2

last_volume = None
pending_volume = None
debounce_timer = None
state_lock = threading.Lock()


def post_with_retry(url, json_body, description):
    for attempt in range(RETRY_ATTEMPTS):
        try:
            requests.post(url, json=json_body, timeout=3)
            return True
        except requests.RequestException as e:
            if attempt == RETRY_ATTEMPTS - 1:
                print(f"Failed to {description} after {RETRY_ATTEMPTS} attempts: {e}")
            else:
                time.sleep(RETRY_BACKOFF_SECONDS)
    return False


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


def apply_pending_volume():
    global last_volume, pending_volume, debounce_timer
    with state_lock:
        volume = pending_volume
        debounce_timer = None
    if volume is None:
        return

    post_with_retry(
        VOLUME_API_URL, {"volume": volume, "relative": False}, f"set go-librespot volume to {volume}"
    )

    was_on = last_volume is not None and last_volume > VOLUME_OFF_THRESHOLD
    is_now_off = volume <= VOLUME_OFF_THRESHOLD
    if was_on and is_now_off:
        post_with_retry(STOP_API_URL, None, "stop go-librespot on volume-off")
    last_volume = volume


def on_message(client, userdata, msg):
    global pending_volume, debounce_timer
    try:
        volume = round(float(msg.payload.decode().strip()))
    except ValueError:
        print(f"Ignoring non-numeric volume payload: {msg.payload!r}")
        return
    volume = max(VOLUME_MIN, min(VOLUME_MAX, volume))

    with state_lock:
        pending_volume = volume
        if debounce_timer is not None:
            debounce_timer.cancel()
        debounce_timer = threading.Timer(DEBOUNCE_SECONDS, apply_pending_volume)
        debounce_timer.start()


mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
mqtt_client.loop_forever()
