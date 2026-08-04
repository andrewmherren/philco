#!/usr/bin/env python3
# Turns the station-tuning dial (philco-ui) into an old-radio-style dial:
# its 0-1023 raw range is split into N equal regions (N = however many
# entries are in /etc/philco-station/regions.json -- not a fixed count,
# so shrinking each region's width just means listing more of them),
# each independently configured as either a specific Spotify URI or quiet
# background "static". Reuses the existing
# philco/ui/controls/station MQTT topic that api/server.js already
# publishes -- no server.js/mqtt-bridge.js/UI changes needed for this.
#
# Arbitration ("most recent change wins") needs no special logic here --
# moving the dial just makes this daemon attempt to open the shared ALSA
# device (via go-librespot's API or a `sox` subprocess). Whichever most
# recently opened it holds it.
#
# IMPORTANT: `sox -t alsa default` opens the same default -> plug -> eq ->
# hw:0 chain go-librespot uses, which routes through the alsaequal LADSPA
# plugin -- the same one whose live gain state lives in
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
# N-way "last one active wins" arbitration with bluetooth-agent.py and
# airplay-agent.py over the shared ALSA device -- see AGENT_SCRATCHPAD.md.
# philco/audio/<source>/active (source: spotify, bluetooth, airplay) is a
# plain announcement (event, not retained, no reply expected) published
# by whichever agent owns that source the moment it starts actually
# producing audio through the shared device. Every agent subscribes to
# the *other* two sources' topics and reacts by stopping/pausing itself
# -- nothing needs to know anything about who else exists beyond these
# topic names, so adding a fourth source later is one more subscription,
# not a new pairwise protocol.
TOPIC_SPOTIFY_ACTIVE = "philco/audio/spotify/active"
TOPIC_BLUETOOTH_ACTIVE = "philco/audio/bluetooth/active"
TOPIC_AIRPLAY_ACTIVE = "philco/audio/airplay/active"
REGIONS_CONFIG_PATH = "/etc/philco-station/regions.json"

# The station dial's potentiometer does NOT span the full 0-1023 ADC
# range the way the volume knob's does -- confirmed via server.js's own
# serial log across a full physical sweep: raw values only ever ranged
# 12-574, which used to mean only 6 of the (then-fixed) 10 regions were
# reachable before this was fixed. A little headroom is added past the
# observed max/below the observed min in case of minor drift; this is a
# hardware calibration constant, not something that belongs in
# regions.json, and is independent of however many regions there are --
# region_index_for_raw() below divides this same physical span by
# len(regions), whatever that is, so adding/removing regions in the
# config just changes how wide each one is, not this range.
STATION_RAW_MIN = 0
STATION_RAW_MAX = 600
VOLUME_ADC_MAX = 1023
PLAYER_PLAY_URL = "http://127.0.0.1:3678/player/play"
PLAYER_PAUSE_URL = "http://127.0.0.1:3678/player/pause"
PLAYER_SHUFFLE_URL = "http://127.0.0.1:3678/player/shuffle_context"
PLAYER_NEXT_URL = "http://127.0.0.1:3678/player/next"

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

# server.js publishes philco/station/reassert on every raw serial sample
# that crosses the off/on threshold, with no debounce of its own -- a
# single continuous knob turn can cross that threshold several times in
# a few ADC-noise-sized counts, each firing its own reassert. Debounced
# here (not by moving the threshold) since the threshold itself was
# confirmed not to be the problem -- see AGENT_SCRATCHPAD.md.
REASSERT_DEBOUNCE_SECONDS = 1.0

# switch_to_region() runs synchronously inside on_message, which executes
# on paho's own loop_forever() thread -- and for a "uri" region it blocks
# on HTTP calls to go-librespot (post_with_retry: up to 3 attempts x 5s
# timeout each). A fast dial sweep crosses many region boundaries within
# milliseconds of each other; while on_message is blocked handling the
# first crossing, every subsequent station message just queues up in
# paho's receive buffer, then gets delivered one at a time afterward --
# replaying every region the dial passed through in sequence, audible as
# several stations cycling by even after the dial has already stopped
# moving. Debouncing so only the dial's *final* settled position is ever
# acted on -- see AGENT_SCRATCHPAD.md.
#
# IMPORTANT: debouncing alone isn't enough. threading.Timer spawns a new
# thread on every firing -- if one firing is still blocked inside
# switch_to_region's slow HTTP/sox calls when a later firing's timer also
# elapses, both run concurrently, racing to mutate current_index and grab
# the ALSA device. Confirmed in practice (sox vs go-librespot "device
# busy" errors, and a sweep landing on the wrong final region because
# whichever thread happened to *finish* last won, not whichever request
# was actually most recent). Fixed with playback_lock below: every firing
# re-reads the latest known value only after acquiring the lock, so a
# superseded firing just sees "nothing left to do" instead of racing.
STATION_DEBOUNCE_SECONDS = 0.2

# Debounced the same way, so turning the volume all the way off reliably
# stops whatever's currently playing -- including static, which nothing
# previously stopped at all (spotify-volume-agent.py's own volume-off
# handling only ever paused go-librespot; a static region has no
# go-librespot involvement, so it just kept playing indefinitely).
VOLUME_OFF_DEBOUNCE_SECONDS = 0.5

# Same debounce-plus-lock shape again, for the "another source became
# active" direction of the arbitration (from either bluetooth-agent.py or
# airplay-agent.py -- both funnel through the same debounce/handler).
EXTERNAL_TAKEOVER_DEBOUNCE_SECONDS = 0.2

# Serializes all actual playback-mutating work (station switches,
# reassert, volume-off stop) onto one at a time -- see the comment above
# STATION_DEBOUNCE_SECONDS for why this is required, not just defensive.
playback_lock = threading.Lock()


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
last_volume_on = None  # tracks the last-applied on/off state, for edge detection
reassert_timer = None
station_timer = None
volume_off_timer = None
external_takeover_timer = None
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

    # Region count is whatever's in the config, not a fixed number -- the
    # dial's full physical sweep (STATION_RAW_MIN/MAX) always gets divided
    # evenly across however many regions are listed, so narrowing each
    # region just means adding more entries here. Still a hard crash on a
    # missing/empty list, same "no safe substitute for which physical
    # position plays what" reasoning as the type/uri checks below.
    regions = config.get("regions")
    if not isinstance(regions, list) or len(regions) == 0:
        found = len(regions) if isinstance(regions, list) else type(regions).__name__
        sys.exit(f"{path}: 'regions' must be a non-empty list, found {found}")

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
    region_count = len(regions)
    clamped = max(STATION_RAW_MIN, min(STATION_RAW_MAX, raw))
    span = STATION_RAW_MAX - STATION_RAW_MIN + 1
    return max(0, min(region_count - 1, (clamped - STATION_RAW_MIN) * region_count // span))


def normalized_volume(raw):
    return round((raw / VOLUME_ADC_MAX) * 100)


def start_uri(region):
    # go-librespot's own docs say to enable shuffle *before* play (enabling
    # it after only reshuffles the upcoming queue, keeping the context's
    # current/first track). That works fine when go-librespot already has
    # a track loaded -- but confirmed via live testing AND three real
    # power-on events' own go-librespot logs (all three landed on the
    # exact same track, "Habits", for this region's artist context) that
    # on a genuinely cold/idle player (nothing loaded since go-librespot
    # last went idle), a shuffle_context call made *before* the first play
    # silently doesn't take effect at all -- /status confirms
    # shuffle_context reverts to false right after. Once a track is loaded
    # (even paused, even unshuffled), a subsequent shuffle_context call
    # reliably sticks. So: load paused first (silent, no audible anchor
    # track), enable shuffle now that the player is warm, then skip
    # forward via /player/next to actually land on a shuffled track --
    # confirmed live that /player/next also resumes playback on its own,
    # so paused:true here never becomes audible. See AGENT_SCRATCHPAD.md.
    post_with_retry(PLAYER_PLAY_URL, {"uri": region["uri"], "paused": True}, f"load uri region {region['uri']}")
    post_with_retry(PLAYER_SHUFFLE_URL, {"shuffle_context": True}, f"enable shuffle for {region['uri']}")
    post_with_retry(PLAYER_NEXT_URL, None, f"skip to shuffled track for {region['uri']}")


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


def publish_spotify_active():
    # Announced every time this agent is about to grab the shared ALSA
    # device for Spotify/static, regardless of whether Bluetooth/AirPlay
    # are actually active right now -- each of those agents subscribes to
    # this and no-ops it themselves if they're not. Keeps this agent from
    # needing any Bluetooth/AirPlay-side state of its own.
    # See AGENT_SCRATCHPAD.md.
    mqtt_client.publish(TOPIC_SPOTIFY_ACTIVE, "playing")


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
    publish_spotify_active()
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
        client.subscribe([
            (TOPIC_STATION, 0), (TOPIC_VOLUME, 0), (TOPIC_REASSERT, 0),
            (TOPIC_BLUETOOTH_ACTIVE, 0), (TOPIC_AIRPLAY_ACTIVE, 0),
        ])
        threading.Timer(STARTUP_SETTLE_SECONDS, decide_startup_region).start()
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def do_reassert():
    global reassert_timer
    reassert_timer = None
    with playback_lock:
        print("Reassert triggered (volume came back on) -- re-applying current region")
        reassert_current_region()


def evaluate_station_switch():
    # Fires STATION_DEBOUNCE_SECONDS after the last station message.
    # Acquires playback_lock before doing anything: if another firing (or
    # a reassert/volume-off) is still mid-switch, this blocks until it's
    # done, then re-reads last_raw_station/current_index FRESH -- not
    # whatever value scheduled this particular firing -- so a firing that
    # was superseded while waiting just finds nothing left to do instead
    # of racing to act on stale data.
    global station_timer
    station_timer = None
    with playback_lock:
        if last_raw_station is None:
            return
        new_index = region_index_for_raw(last_raw_station)
        if new_index == current_index:
            return
        switch_to_region(new_index, regions)


def evaluate_volume_off():
    global volume_off_timer, last_volume_on
    volume_off_timer = None
    if last_raw_volume is None:
        return
    is_on = normalized_volume(last_raw_volume) > VOLUME_OFF_THRESHOLD
    with playback_lock:
        if not is_on and last_volume_on and current_index is not None:
            print("Volume settled at off -- stopping current region playback")
            BEHAVIORS[regions[current_index]["type"]]["stop"]()
        last_volume_on = is_on


def evaluate_external_takeover():
    # Fires EXTERNAL_TAKEOVER_DEBOUNCE_SECONDS after bluetooth-agent.py or
    # airplay-agent.py reports its source started actually playing audio.
    # Only reacts to "playing", not "stopped" -- per explicit request, a
    # source taking over pauses Spotify/static, but that source going
    # quiet doesn't automatically resume anything (no request to do so,
    # and it'd be surprising if e.g. a phone briefly stalling mid-track
    # suddenly kicked Spotify back on).
    global external_takeover_timer
    external_takeover_timer = None
    with playback_lock:
        if current_index is not None:
            print("Another source started playing -- pausing current Spotify/static region")
            BEHAVIORS[regions[current_index]["type"]]["stop"]()


def on_message(client, userdata, msg):
    global last_raw_station, last_raw_volume, reassert_timer, station_timer, volume_off_timer, external_takeover_timer

    if msg.topic in (TOPIC_BLUETOOTH_ACTIVE, TOPIC_AIRPLAY_ACTIVE):
        if msg.payload.decode().strip() != "playing":
            return
        if external_takeover_timer is not None:
            external_takeover_timer.cancel()
        external_takeover_timer = threading.Timer(EXTERNAL_TAKEOVER_DEBOUNCE_SECONDS, evaluate_external_takeover)
        external_takeover_timer.start()
        return

    if msg.topic == TOPIC_REASSERT:
        # Debounced, unlike the rest of on_message -- server.js publishes
        # this on every raw serial sample with no debounce/hysteresis of
        # its own (unlike spotify-volume-agent.py's knob handling), so a
        # single continuous turn-on can produce several rapid off/on/off
        # edges right as the reading crosses the threshold (ADC jitter of
        # just a few counts at that exact boundary), each publishing its
        # own reassert. Undebounced, each one restarted the station with
        # a fresh shuffle -- audible as 2-4 rapid track skips right after
        # turning the radio on, even though nothing was touched after the
        # knob settled. Collapsing rapid-fire reasserts into the last one
        # (mirroring spotify-volume-agent.py's own DEBOUNCE_SECONDS
        # pattern) fixes this without touching the on/off threshold
        # itself, which was confirmed (via raw serial log review) not to
        # be the actual problem. See AGENT_SCRATCHPAD.md.
        if reassert_timer is not None:
            reassert_timer.cancel()
        reassert_timer = threading.Timer(REASSERT_DEBOUNCE_SECONDS, do_reassert)
        reassert_timer.start()
        return

    try:
        raw = int(float(msg.payload.decode().strip()))
    except ValueError:
        print(f"Ignoring non-numeric payload on {msg.topic}: {msg.payload!r}")
        return

    if msg.topic == TOPIC_VOLUME:
        last_raw_volume = raw
        if volume_off_timer is not None:
            volume_off_timer.cancel()
        volume_off_timer = threading.Timer(VOLUME_OFF_DEBOUNCE_SECONDS, evaluate_volume_off)
        volume_off_timer.start()
        return

    last_raw_station = raw
    if not started:
        return  # decide_startup_region handles the first region once the settle window elapses
    if station_timer is not None:
        station_timer.cancel()
    station_timer = threading.Timer(STATION_DEBOUNCE_SECONDS, evaluate_station_switch)
    station_timer.start()


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
