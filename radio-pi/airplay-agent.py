#!/usr/bin/env python3
# Gates AirPlay on the radio Pi to the physical volume knob (philco-ui),
# same rule as bluetooth-agent.py: only advertised/connectable while the
# knob is on, and any active session is dropped the instant it's turned
# off. Unlike Bluetooth, there's no separate "powered/discoverable" state
# to toggle -- shairport-sync only advertises via mDNS and accepts
# connections while its process is actually running, so this agent's
# entire job is starting/stopping shairport-sync.service. Stopping it
# both removes the mDNS advertisement and forcibly drops any active
# AirPlay session (there's no graceful "just disconnect the client"
# command in shairport-sync, so a stop/restart is also how this agent
# forces a source that lost the arbitration below to let go).
#
# shairport-sync.service ships disabled from this agent's point of view
# (see AGENT_SCRATCHPAD.md -- disabled at the systemd level so it never
# starts on its own at boot regardless of volume state) -- this agent is
# the only thing that starts or stops it.
#
# Also participates in the same N-way "last one active wins" arbitration
# as station-agent.py/bluetooth-agent.py over the shared ALSA device (see
# the topic comment in station-agent.py): restarts shairport-sync.service
# (dropping any current session) whenever Spotify/static or Bluetooth
# announces it just became active. The reverse direction -- telling the
# others when AirPlay itself starts playing -- isn't done from here at
# all: shairport-sync's own run_this_before_play_begins/
# run_this_after_play_ends hooks (see /etc/shairport-sync.conf) call a
# narrowly-sudo'd helper script directly, since they run as the
# unprivileged shairport-sync user and this agent has no way to be
# notified by them other than over MQTT, which needs credentials that
# user deliberately doesn't have. See AGENT_SCRATCHPAD.md.
import os
import subprocess
import threading

import paho.mqtt.client as mqtt

TOPIC_VOLUME = "philco/ui/controls/volume"
# N-way arbitration topics -- see the matching comment in station-agent.py.
TOPIC_SPOTIFY_ACTIVE = "philco/audio/spotify/active"
TOPIC_BLUETOOTH_ACTIVE = "philco/audio/bluetooth/active"
SERVICE_NAME = "shairport-sync.service"

# Must match station-agent.py/bluetooth-agent.py's own off-threshold and
# VOLUME_ADC_MAX -- all three read the same raw knob position.
VOLUME_OFF_THRESHOLD = 2  # out of 100 -- small margin past the click-stop
VOLUME_ADC_MAX = 1023
STARTUP_SETTLE_SECONDS = 1.5  # time to wait for retained state after subscribing
VOLUME_DEBOUNCE_SECONDS = 0.5  # matches bluetooth-agent.py's VOLUME_DEBOUNCE_SECONDS

last_raw_volume = None
last_applied_on = None  # tracks the last-applied service on/off state
volume_timer = None
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


def normalized_volume(raw):
    return round((raw / VOLUME_ADC_MAX) * 100)


def systemctl(action):
    result = subprocess.run(
        ["systemctl", action, SERVICE_NAME], capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"systemctl {action} {SERVICE_NAME} failed: {result.stderr.strip()}")


def airplay_on():
    print("Volume on -- starting AirPlay (shairport-sync)")
    systemctl("start")


def airplay_off():
    print("Volume off -- stopping AirPlay (shairport-sync), dropping any active session")
    systemctl("stop")


def evaluate_volume():
    global volume_timer, last_applied_on
    volume_timer = None
    if last_raw_volume is None:
        return
    is_on = normalized_volume(last_raw_volume) > VOLUME_OFF_THRESHOLD
    if is_on != last_applied_on:
        (airplay_on if is_on else airplay_off)()
        last_applied_on = is_on


def decide_startup_state():
    global started, last_applied_on
    if started:
        return
    started = True
    if last_raw_volume is not None and normalized_volume(last_raw_volume) > VOLUME_OFF_THRESHOLD:
        print("Volume already known to be on at startup -- starting AirPlay")
        airplay_on()
        last_applied_on = True
    else:
        print("Volume unknown or off at startup -- leaving AirPlay off")
        last_applied_on = False


def take_over_from_airplay():
    # Only meaningful if AirPlay is actually supposed to be on right now
    # -- guards against a stray/late arbitration message restarting the
    # service while the volume knob is off (it should stay off).
    if not last_applied_on:
        return
    print("Another source became active -- restarting AirPlay to drop any current session")
    systemctl("restart")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected")
        client.subscribe([(TOPIC_VOLUME, 0), (TOPIC_SPOTIFY_ACTIVE, 0), (TOPIC_BLUETOOTH_ACTIVE, 0)])
        threading.Timer(STARTUP_SETTLE_SECONDS, decide_startup_state).start()
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def on_message(client, userdata, msg):
    global last_raw_volume, volume_timer

    if msg.topic in (TOPIC_SPOTIFY_ACTIVE, TOPIC_BLUETOOTH_ACTIVE):
        if msg.payload.decode().strip() == "playing":
            take_over_from_airplay()
        return

    try:
        last_raw_volume = int(float(msg.payload.decode().strip()))
    except ValueError:
        print(f"Ignoring non-numeric volume payload: {msg.payload!r}")
        return
    if not started:
        return  # decide_startup_state handles the first application once the settle window elapses
    if volume_timer is not None:
        volume_timer.cancel()
    volume_timer = threading.Timer(VOLUME_DEBOUNCE_SECONDS, evaluate_volume)
    volume_timer.start()


env = load_env("/etc/philco-mqtt/.env")
MQTT_HOST = env.get("MQTT_HOST", "homeassistant.local")
MQTT_PORT = int(env.get("MQTT_PORT", "1883"))
MQTT_USERNAME = env.get("MQTT_USERNAME")
MQTT_PASSWORD = env.get("MQTT_PASSWORD")

mqtt_client = mqtt.Client(client_id="philco-radio-airplay-agent")
if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
mqtt_client.loop_forever()
