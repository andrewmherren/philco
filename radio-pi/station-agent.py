#!/usr/bin/env python3
# Turns the station-tuning dial (philco-ui) into an old-radio-style dial:
# its 0-1023 raw range is split into 10 equal regions, each independently
# configured (see /etc/philco-station/regions.json) as either a specific
# Spotify URI or quiet background "static". Reuses the existing
# philco/ui/controls/station MQTT topic that api/server.js already
# publishes -- no server.js/mqtt-bridge.js/UI changes needed for this.
#
# Arbitration ("most recent change wins") needs no special logic here --
# moving the dial just makes this daemon attempt to open the shared ALSA
# device (via go-librespot's API or a `sox` subprocess), exactly like
# shairport-sync/go-librespot already contend for it today. Whichever
# most recently opened it holds it.
#
# IMPORTANT: `sox -t alsa default` opens the same default -> plug -> eq ->
# hw:0 chain go-librespot/shairport-sync use, which routes through the
# alsaequal LADSPA plugin -- the same one whose live gain state lives in
# $HOME/.alsaequal.bin (see eq-agent.py / AGENT_SCRATCHPAD.md). This
# service must run with HOME=/root (see station-agent.service) for sox to
# behave consistently with everything else in the audio chain.
import json
import os
import subprocess
import sys
import threading
import time

import paho.mqtt.client as mqtt
import requests

TOPIC_STATION = "philco/ui/controls/station"
TOPIC_VOLUME = "philco/ui/controls/volume"
TOPIC_REASSERT = "philco/station/reassert"
REGIONS_CONFIG_PATH = "/etc/philco-station/regions.json"
REGION_COUNT = 10

# The station dial's potentiometer does NOT span the full 0-1023 ADC
# range the way the volume knob's does -- confirmed via server.js's own
# serial log across a full physical sweep: raw values only ever ranged
# 12-574, which is why only 6 of 10 regions were reachable before this
# fix. A little headroom is added past the observed max/below the
# observed min in case of minor drift; this is a hardware calibration
# constant, not something that belongs in regions.json.
STATION_RAW_MIN = 0
STATION_RAW_MAX = 600
VOLUME_ADC_MAX = 1023
PLAYER_PLAY_URL = "http://127.0.0.1:3678/player/play"
PLAYER_PAUSE_URL = "http://127.0.0.1:3678/player/pause"
PLAYER_SHUFFLE_URL = "http://127.0.0.1:3678/player/shuffle_context"

# The volume knob has a physical off click-stop at one end of its travel.
# We track the knob's own last-known raw position (via the retained
# philco/ui/controls/volume topic -- see api/mqtt-bridge.js), not
# go-librespot's own reported volume: those can diverge, since something
# else (e.g. the Spotify app) may have changed go-librespot's volume more
# recently than the knob was last touched, and per the "most recent
# change wins" design that's legitimately the current volume -- but it
# does NOT tell you where the physical knob is sitting, which is what
# actually matters for "should we autoplay on startup."
VOLUME_OFF_THRESHOLD = 2  # out of 100 -- small margin past the click-stop
STARTUP_SETTLE_SECONDS = 1.5  # time to wait for retained state after subscribing
STATIC_ALSA_DEVICE = "default"
STATIC_VOLUME_DEFAULT = 0.05
STATIC_START_RETRY_DELAYS = [0.1, 0.2, 0.4, 0.8, 1.6]  # ~3.1s total settle/retry budget

# go-librespot's local API can itself become temporarily unresponsive
# under load (observed: a burst of rapid volume-set calls from quick knob
# movement caused it to briefly time out on *every* request, including
# unrelated ones from this daemon) -- retry play/shuffle/pause calls
# rather than silently giving up on the first failure. A longer timeout
# than the volume-agent's is used here since resolving a new Spotify
# context can genuinely need a round-trip to Spotify's own servers, not
# just a local operation.
PLAYER_REQUEST_TIMEOUT_SECONDS = 5
PLAYER_RETRY_ATTEMPTS = 3
PLAYER_RETRY_BACKOFF_SECONDS = 0.5


def post_with_retry(url, json_body, description):
    for attempt in range(PLAYER_RETRY_ATTEMPTS):
        try:
            requests.post(url, json=json_body, timeout=PLAYER_REQUEST_TIMEOUT_SECONDS)
            return True
        except requests.RequestException as e:
            if attempt == PLAYER_RETRY_ATTEMPTS - 1:
                print(f"Failed to {description} after {PLAYER_RETRY_ATTEMPTS} attempts: {e}")
            else:
                time.sleep(PLAYER_RETRY_BACKOFF_SECONDS)
    return False

current_index = None
static_proc = None
static_volume = STATIC_VOLUME_DEFAULT
last_raw_station = None
last_raw_volume = None
started = False


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


def load_regions_config(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except (OSError, ValueError) as e:
        sys.exit(f"Failed to read/parse {path}: {e}")

    regions = config.get("regions")
    if not isinstance(regions, list) or len(regions) != REGION_COUNT:
        found = len(regions) if isinstance(regions, list) else type(regions).__name__
        sys.exit(f"{path}: 'regions' must be a list of exactly {REGION_COUNT} entries, found {found}")

    for i, region in enumerate(regions):
        region_type = region.get("type")
        if region_type not in ("uri", "static"):
            sys.exit(f"{path}: region {i} has invalid or missing 'type' ({region_type!r}); must be 'uri' or 'static'")
        if region_type == "uri" and not region.get("uri"):
            sys.exit(f"{path}: region {i} is type 'uri' but has no 'uri' value")

    volume = config.get("static_volume")
    if not isinstance(volume, (int, float)):
        if volume is not None:
            print(f"{path}: ignoring invalid 'static_volume' ({volume!r}), using default {STATIC_VOLUME_DEFAULT}")
        volume = STATIC_VOLUME_DEFAULT

    return regions, volume


def find_default_index(regions):
    default_indices = [i for i, r in enumerate(regions) if r.get("default")]
    if len(default_indices) == 1:
        return default_indices[0]
    if len(default_indices) == 0:
        print('No region flagged "default": true -- falling back to index 0')
        return 0
    print(f"Multiple regions flagged default ({default_indices}) -- using {default_indices[0]}")
    return default_indices[0]


def region_index_for_raw(raw):
    clamped = max(STATION_RAW_MIN, min(STATION_RAW_MAX, raw))
    span = STATION_RAW_MAX - STATION_RAW_MIN + 1
    return max(0, min(REGION_COUNT - 1, (clamped - STATION_RAW_MIN) * REGION_COUNT // span))


def normalized_volume(raw):
    return round((raw / VOLUME_ADC_MAX) * 100)


def start_uri(region):
    # Shuffle must be enabled *before* play, not after -- go-librespot's
    # own docs note that enabling shuffle after play only shuffles the
    # upcoming queue and keeps playing the context's first track, whereas
    # enabling it first actually starts on a random track.
    post_with_retry(PLAYER_SHUFFLE_URL, {"shuffle_context": True}, f"enable shuffle for {region['uri']}")
    post_with_retry(PLAYER_PLAY_URL, {"uri": region["uri"], "paused": False}, f"start uri region {region['uri']}")


def stop_uri():
    # /player/pause, not /player/stop -- we want to hand off the ALSA
    # device, not tear down the whole Spotify Connect session.
    post_with_retry(PLAYER_PAUSE_URL, None, "pause go-librespot")


def start_static(region):
    global static_proc
    for delay in STATIC_START_RETRY_DELAYS:
        try:
            proc = subprocess.Popen(
                ["sox", "-q", "-n", "-t", "alsa", STATIC_ALSA_DEVICE,
                 "synth", "whitenoise", "vol", str(static_volume)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
        except OSError as e:
            print(f"Failed to launch sox: {e}")
            return
        time.sleep(delay)
        if proc.poll() is None:
            static_proc = proc
            return
        stderr = proc.stderr.read().decode(errors="replace").strip()
        print(f"sox exited immediately (device busy?), retrying in {delay}s: {stderr}")
    print("Giving up starting static after retries -- ALSA device may be stuck busy")


def stop_static():
    global static_proc
    if static_proc is None:
        return
    static_proc.terminate()
    try:
        static_proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        static_proc.kill()
        static_proc.wait()
    static_proc = None


BEHAVIORS = {
    "uri": {"start": start_uri, "stop": stop_uri},
    "static": {"start": start_static, "stop": stop_static},
}


def switch_to_region(new_index, regions):
    global current_index
    new_region = regions[new_index]
    old_region = regions[current_index] if current_index is not None else None

    same_type = old_region is not None and old_region["type"] == new_region["type"]
    same_content = same_type and (
        new_region["type"] == "static"
        or old_region.get("uri") == new_region.get("uri")
    )
    if same_content:
        current_index = new_index
        return

    if old_region is not None:
        BEHAVIORS[old_region["type"]]["stop"]()
    BEHAVIORS[new_region["type"]]["start"](new_region)
    current_index = new_index


def decide_startup_region():
    global started
    if started:
        return
    started = True
    if last_raw_station is not None:
        index = region_index_for_raw(last_raw_station)
        print(f"Dial's current position known from retained state (region {index}) -- starting there")
        switch_to_region(index, regions)
        return
    if last_raw_volume is not None and normalized_volume(last_raw_volume) > VOLUME_OFF_THRESHOLD:
        print(f"No known dial position -- starting default region {default_index} ({regions[default_index]['type']})")
        switch_to_region(default_index, regions)
    else:
        print("No known dial position, and volume is unknown or at/near its off click-stop -- staying stopped/idle")


def reassert_current_region():
    # Fired when volume crosses from off to on (see server.js). A plain
    # republish of the station/mode topics doesn't help here: if the dial
    # hasn't moved, the region index is unchanged, and on_message's own
    # "new_index == current_index" check would just no-op it. This forces
    # a fresh start of whatever region is/should be current, regardless.
    global current_index
    if current_index is not None:
        index = current_index
        current_index = None  # makes switch_to_region treat this as a fresh start, not a no-op
        switch_to_region(index, regions)
        return
    if last_raw_station is not None:
        switch_to_region(region_index_for_raw(last_raw_station), regions)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected")
        client.subscribe([(TOPIC_STATION, 0), (TOPIC_VOLUME, 0), (TOPIC_REASSERT, 0)])
        threading.Timer(STARTUP_SETTLE_SECONDS, decide_startup_region).start()
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def on_message(client, userdata, msg):
    global last_raw_station, last_raw_volume

    if msg.topic == TOPIC_REASSERT:
        print("Reassert triggered (volume came back on) -- re-applying current region")
        reassert_current_region()
        return

    try:
        raw = int(float(msg.payload.decode().strip()))
    except ValueError:
        print(f"Ignoring non-numeric payload on {msg.topic}: {msg.payload!r}")
        return

    if msg.topic == TOPIC_VOLUME:
        last_raw_volume = raw
        return

    last_raw_station = raw
    if not started:
        return  # decide_startup_region handles the first region once the settle window elapses
    new_index = region_index_for_raw(raw)
    if new_index == current_index:
        return
    switch_to_region(new_index, regions)


regions, static_volume = load_regions_config(REGIONS_CONFIG_PATH)
default_index = find_default_index(regions)

env = load_env("/etc/philco-mqtt/.env")
MQTT_HOST = env.get("MQTT_HOST", "homeassistant.local")
MQTT_PORT = int(env.get("MQTT_PORT", "1883"))
MQTT_USERNAME = env.get("MQTT_USERNAME")
MQTT_PASSWORD = env.get("MQTT_PASSWORD")

mqtt_client = mqtt.Client(client_id="philco-radio-station-agent")
if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
mqtt_client.loop_forever()
