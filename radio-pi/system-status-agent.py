#!/usr/bin/env python3
# Publishes health status for the radio's three audio sources (Spotify,
# Bluetooth, AirPlay) over MQTT, and accepts a "restart this source" command
# for each -- backing the touchscreen's System Status screen (mode-switch
# position 5 in App.jsx).
#
# Built after a real incident (2026-09): go-librespot ran for ~37 days
# straight and its Spotify Login5 token stopped renewing. The process
# still looked "alive" -- it kept reconnecting at the lower AP level, so
# systemctl status and a shallow log glance both looked fine -- but every
# actual play/volume request silently failed with "authenticating with
# login5: UNKNOWN_ERROR". Bluetooth kept working fine throughout (it never
# touches go-librespot), which is exactly what made this confusing to
# diagnose live. The spotify health check below deliberately re-creates
# that exact failure mode (a real authenticated write call, not just "is
# the process running") so this can't happen invisibly again, and the
# restart button gives a way to self-serve the fix from the cabinet itself
# without needing an SSH session.
import json
import os
import subprocess
import threading
import time

import dbus
import paho.mqtt.client as mqtt
import requests

TOPIC_VOLUME = "philco/ui/controls/volume"
TOPIC_AIRPLAY_ACTIVE = "philco/audio/airplay/active"
TOPIC_STATUS_PREFIX = "philco/system"  # + /<service>/status, /<service>/restart

PLAYER_STATUS_URL = "http://127.0.0.1:3678/status"
PLAYER_VOLUME_URL = "http://127.0.0.1:3678/player/volume"
API_TIMEOUT_SECONDS = 5

POLL_INTERVAL_SECONDS = 20

# Must match station-agent.py/bluetooth-agent.py/airplay-agent.py's own
# off-threshold and VOLUME_ADC_MAX -- all read the same raw knob position.
VOLUME_OFF_THRESHOLD = 2
VOLUME_ADC_MAX = 1023
STARTUP_SETTLE_SECONDS = 1.5  # time to wait for retained state after subscribing

ADAPTER_PATH = "/org/bluez/hci0"

SERVICES = ("spotify", "bluetooth", "airplay")
RESTART_ACTIONS = {
    "spotify": [["systemctl", "restart", "go-librespot.service"]],
    "bluetooth": [["systemctl", "restart", "bluealsa.service", "bluealsa-aplay.service"]],
    "airplay": [["systemctl", "restart", "shairport-sync.service"]],
}

last_raw_volume = None
last_airplay_active = None  # last "playing"/"stopped" seen on TOPIC_AIRPLAY_ACTIVE; None until first event


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


def normalized_volume(raw):
    return round((raw / VOLUME_ADC_MAX) * 100)


def volume_is_on():
    # None (unknown, e.g. before the retained state arrives) is treated as
    # "not confirmed on" everywhere this is used, so a service that's
    # legitimately off during startup doesn't get misreported as "error".
    if last_raw_volume is None:
        return False
    return normalized_volume(last_raw_volume) > VOLUME_OFF_THRESHOLD


def is_active(unit):
    result = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
    return result.stdout.strip() == "active"


def check_spotify():
    if not is_active("go-librespot.service"):
        return {"state": "down", "detail": "go-librespot.service not running"}

    try:
        status = requests.get(PLAYER_STATUS_URL, timeout=API_TIMEOUT_SECONDS).json()
    except requests.RequestException as e:
        return {"state": "down", "detail": f"local API unreachable: {e}"}

    current_volume = status.get("volume")
    if current_volume is None:
        return {"state": "error", "detail": "no volume reported by /status"}

    # A genuine no-op (sets volume to what it already is) that still needs
    # a working Login5 token -- this is the exact call that silently failed
    # during the 2026-09 incident, so it actually exercises the failure
    # mode rather than just confirming the process is alive.
    try:
        resp = requests.post(
            PLAYER_VOLUME_URL, json={"volume": current_volume, "relative": False}, timeout=API_TIMEOUT_SECONDS
        )
    except requests.RequestException as e:
        return {"state": "error", "detail": f"volume round-trip failed: {e}"}

    if resp.status_code != 200:
        return {"state": "error", "detail": f"volume round-trip returned HTTP {resp.status_code}"}

    track = status.get("track") or {}
    if status.get("paused") is False and track.get("name"):
        detail = f"playing: {track['name']}"
    elif track.get("name"):
        detail = f"paused: {track['name']}"
    else:
        detail = "idle"
    return {"state": "ok", "detail": detail}


def check_bluetooth():
    both_active = is_active("bluealsa.service") and is_active("bluealsa-aplay.service")
    if not both_active:
        return {"state": "error", "detail": "bluealsa/bluealsa-aplay not both running"}

    try:
        bus = dbus.SystemBus()
        adapter_props = dbus.Interface(
            bus.get_object("org.bluez", ADAPTER_PATH), "org.freedesktop.DBus.Properties"
        )
        powered = bool(adapter_props.Get("org.bluez.Adapter1", "Powered"))
    except dbus.DBusException as e:
        return {"state": "error", "detail": f"adapter query failed: {e}"}

    if not powered:
        if volume_is_on():
            return {"state": "error", "detail": "adapter powered off while volume is on"}
        return {"state": "off", "detail": "volume off"}

    try:
        manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        objects = manager.GetManagedObjects()
    except dbus.DBusException as e:
        return {"state": "ok", "detail": f"powered (device list unavailable: {e})"}

    for path, interfaces in objects.items():
        device = interfaces.get("org.bluez.Device1")
        if device and bool(device.get("Connected")):
            name = str(device.get("Alias") or device.get("Name") or path)
            return {"state": "ok", "detail": f"connected: {name}"}
    return {"state": "ok", "detail": "idle"}


def check_airplay():
    active = is_active("shairport-sync.service")
    if not active:
        if volume_is_on():
            return {"state": "error", "detail": "shairport-sync not running while volume is on"}
        return {"state": "off", "detail": "volume off"}

    if last_airplay_active == "playing":
        return {"state": "ok", "detail": "playing"}
    return {"state": "ok", "detail": "idle"}


CHECKS = {"spotify": check_spotify, "bluetooth": check_bluetooth, "airplay": check_airplay}


def publish_status(service):
    try:
        result = CHECKS[service]()
    except Exception as e:  # noqa: BLE001 -- a health check must never take the agent down
        result = {"state": "error", "detail": f"status check crashed: {e}"}
    mqtt_client.publish(f"{TOPIC_STATUS_PREFIX}/{service}/status", json.dumps(result), retain=True)


def poll_all():
    for service in SERVICES:
        publish_status(service)
    threading.Timer(POLL_INTERVAL_SECONDS, poll_all).start()


RESTART_RECHECK_DELAYS_SECONDS = [2, 2, 4, 4]  # ~12s total: gives a just-restarted service time to come back up


def restart_service(service):
    # airplay-agent.py owns shairport-sync.service's start/stop entirely,
    # gated on the volume knob, and only reacts to an actual on/off edge --
    # it has no ongoing "is it currently supposed to be running" loop. If
    # we force-started shairport-sync here while the knob is off, it would
    # keep running (and advertising over AirPlay) indefinitely, since
    # nothing would notice or correct it until some future edge. So:
    # restarting AirPlay only ever means something while it's expected to
    # be on; while off, the correct state already holds and there's
    # nothing to restart. (go-librespot and bluealsa/bluealsa-aplay run
    # unconditionally regardless of volume, so spotify/bluetooth need no
    # equivalent guard.)
    if service == "airplay" and not volume_is_on():
        publish_status(service)
        return

    for command in RESTART_ACTIONS[service]:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{' '.join(command)} failed: {result.stderr.strip()}")

    # A freshly-restarted service (especially go-librespot re-binding its
    # local API) isn't necessarily back up the instant `systemctl restart`
    # returns -- publishing immediately would report a false "down" right
    # after a successful restart. Retry until it reports something other
    # than "down", rather than a single immediate check.
    for delay in RESTART_RECHECK_DELAYS_SECONDS:
        time.sleep(delay)
        result = CHECKS[service]()
        if result["state"] != "down":
            break
    mqtt_client.publish(f"{TOPIC_STATUS_PREFIX}/{service}/status", json.dumps(result), retain=True)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected")
        subscriptions = [(TOPIC_VOLUME, 0), (TOPIC_AIRPLAY_ACTIVE, 0)]
        subscriptions += [(f"{TOPIC_STATUS_PREFIX}/{s}/restart", 0) for s in SERVICES]
        client.subscribe(subscriptions)
        threading.Timer(STARTUP_SETTLE_SECONDS, poll_all).start()
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def on_message(client, userdata, msg):
    global last_raw_volume, last_airplay_active

    if msg.topic == TOPIC_VOLUME:
        try:
            last_raw_volume = int(float(msg.payload.decode().strip()))
        except ValueError:
            print(f"Ignoring non-numeric volume payload: {msg.payload!r}")
        return

    if msg.topic == TOPIC_AIRPLAY_ACTIVE:
        last_airplay_active = msg.payload.decode().strip()
        return

    for service in SERVICES:
        if msg.topic == f"{TOPIC_STATUS_PREFIX}/{service}/restart":
            print(f"Restart requested for {service}")
            restart_service(service)
            return


env = load_env("/etc/philco-mqtt/.env")
MQTT_HOST = env.get("MQTT_HOST", "homeassistant.local")
MQTT_PORT = int(env.get("MQTT_PORT", "1883"))
MQTT_USERNAME = env.get("MQTT_USERNAME")
MQTT_PASSWORD = env.get("MQTT_PASSWORD")

mqtt_client = mqtt.Client(client_id="philco-radio-system-status-agent")
if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
mqtt_client.loop_forever()
