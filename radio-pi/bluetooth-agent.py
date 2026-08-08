#!/usr/bin/env python3
# Gates Bluetooth (A2DP) on the radio Pi to the physical volume knob
# (philco-ui): the adapter is powered off -- undiscoverable, unpairable,
# unconnectable -- whenever the knob is off, and powered back on
# (discoverable + pairable) as soon as it's on. Powering the adapter off
# is also what disconnects any currently-connected phone: BlueZ drops all
# active connections as a side effect of Powered->False, so there's no
# need to enumerate and disconnect devices individually.
#
# Pairing is deliberately zero-friction, per explicit request: registers
# a NoInputNoOutput agent, which negotiates BlueZ/SSP "Just Works"
# pairing -- no code shown, no confirmation needed on either side. The
# actual security boundary is physical: a phone can only find/pair with
# the radio while someone has the volume knob on. AuthorizeService also
# auto-accepts, so profile connections (A2DP, AVRCP) proceed immediately
# once paired, and newly-paired devices are auto-trusted so every future
# reconnection (while the adapter is on) needs no agent interaction at
# all -- not just the first pairing.
#
# Audio itself never touches this process -- bluealsa/bluealsa-aplay
# (see bluealsa-aplay.service override) handle piping A2DP audio into
# the shared ALSA `default` device on their own, entirely independent of
# whether the adapter happens to be discoverable/pairable right now.
#
# Also arbitrates the shared ALSA device with station-agent.py (Spotify/
# static) and airplay-agent.py, per explicit request -- "last one active
# wins," N-way: watches every connected device's org.bluez.MediaPlayer1
# for its Status actually becoming "playing" (not just "connected" -- a
# phone can be connected without playing anything) and publishes that as
# philco/audio/bluetooth/active, which every other source-owning agent
# subscribes to and reacts to by pausing/stopping itself. The reverse
# direction (some other source becoming active) is handled by subscribing
# to *their* philco/audio/<source>/active topics and, on either, sending
# an actual AVRCP pause to whatever's currently playing over Bluetooth --
# so the phone's own player visibly pauses too, not just silently loses
# the ALSA device. See AGENT_SCRATCHPAD.md.
import os
import threading

import dbus
import dbus.mainloop.glib
import dbus.service
import paho.mqtt.client as mqtt
from gi.repository import GLib

TOPIC_VOLUME = "philco/ui/controls/volume"
# N-way arbitration topics -- see the matching comment in station-agent.py.
TOPIC_SPOTIFY_ACTIVE = "philco/audio/spotify/active"
TOPIC_BLUETOOTH_ACTIVE = "philco/audio/bluetooth/active"
TOPIC_AIRPLAY_ACTIVE = "philco/audio/airplay/active"
ADAPTER_PATH = "/org/bluez/hci0"
AGENT_PATH = "/philco/btagent"
MEDIA_PLAYER_IFACE = "org.bluez.MediaPlayer1"

# Must match station-agent.py/spotify-volume-agent.py's own off-threshold
# and VOLUME_ADC_MAX -- all three read the same raw knob position.
VOLUME_OFF_THRESHOLD = 2  # out of 100 -- small margin past the click-stop
VOLUME_ADC_MAX = 1023
STARTUP_SETTLE_SECONDS = 1.5  # time to wait for retained state after subscribing
VOLUME_DEBOUNCE_SECONDS = 0.5  # matches station-agent.py's VOLUME_OFF_DEBOUNCE_SECONDS

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()

adapter_obj = bus.get_object("org.bluez", ADAPTER_PATH)
adapter_props = dbus.Interface(adapter_obj, "org.freedesktop.DBus.Properties")

last_raw_volume = None
last_applied_on = None  # tracks the last-applied adapter on/off state
volume_timer = None
started = False

# Paths of every org.bluez.MediaPlayer1 currently reporting Status ==
# "playing" -- a set, not a single value, so multiple simultaneously-
# connected/playing sources (unlikely, but possible) degrade gracefully
# instead of one silently overwriting tracking of the other.
playing_player_paths = set()


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


def set_adapter_property(name, value):
    try:
        adapter_props.Set("org.bluez.Adapter1", name, value)
    except dbus.DBusException as e:
        print(f"Failed to set Adapter1.{name}={value}: {e}")


def bluetooth_on():
    print("Volume on -- powering on Bluetooth adapter, discoverable + pairable")
    set_adapter_property("Powered", dbus.Boolean(True))
    set_adapter_property("Discoverable", dbus.Boolean(True))
    set_adapter_property("Pairable", dbus.Boolean(True))


def bluetooth_off():
    # Discoverable/Pairable are moot once powered off, but set them first
    # anyway so the adapter isn't left silently advertising if a future
    # change ever makes powering off conditional. Powered->False is what
    # actually disconnects any connected phone.
    print("Volume off -- disconnecting and powering off Bluetooth adapter")
    set_adapter_property("Discoverable", dbus.Boolean(False))
    set_adapter_property("Pairable", dbus.Boolean(False))
    set_adapter_property("Powered", dbus.Boolean(False))


def evaluate_volume():
    global volume_timer, last_applied_on
    volume_timer = None
    if last_raw_volume is None:
        return
    is_on = normalized_volume(last_raw_volume) > VOLUME_OFF_THRESHOLD
    if is_on != last_applied_on:
        (bluetooth_on if is_on else bluetooth_off)()
        last_applied_on = is_on


def decide_startup_state():
    global started, last_applied_on
    if started:
        return
    started = True
    if last_raw_volume is not None and normalized_volume(last_raw_volume) > VOLUME_OFF_THRESHOLD:
        print("Volume already known to be on at startup -- powering on Bluetooth")
        bluetooth_on()
        last_applied_on = True
    else:
        print("Volume unknown or off at startup -- leaving Bluetooth off")
        last_applied_on = False


def publish_playback_state(is_playing):
    print(f"Bluetooth playback {'started' if is_playing else 'stopped'}")
    mqtt_client.publish(TOPIC_BLUETOOTH_ACTIVE, "playing" if is_playing else "stopped")


def update_playback_state(path, status):
    # Tracks a set rather than reacting to every individual status change
    # directly, so only an actual idle<->playing edge (not e.g.
    # playing->paused->playing on the same device, or a second device
    # changing status while one's already playing) publishes anything.
    was_playing = bool(playing_player_paths)
    if status == "playing":
        playing_player_paths.add(path)
    else:
        playing_player_paths.discard(path)
    is_playing = bool(playing_player_paths)
    if is_playing != was_playing:
        publish_playback_state(is_playing)


def pause_bluetooth_playback():
    if not playing_player_paths:
        print("Bluetooth pause requested but nothing is currently playing -- no-op")
        return
    for path in playing_player_paths:
        try:
            player = dbus.Interface(bus.get_object("org.bluez", path), MEDIA_PLAYER_IFACE)
            player.Pause()
            print(f"Sent AVRCP pause to {path}")
        except dbus.DBusException as e:
            print(f"Failed to pause {path}: {e}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected")
        client.subscribe([(TOPIC_VOLUME, 0), (TOPIC_SPOTIFY_ACTIVE, 0), (TOPIC_AIRPLAY_ACTIVE, 0)])
        threading.Timer(STARTUP_SETTLE_SECONDS, decide_startup_state).start()
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def on_message(client, userdata, msg):
    global last_raw_volume, volume_timer

    if msg.topic in (TOPIC_SPOTIFY_ACTIVE, TOPIC_AIRPLAY_ACTIVE):
        if msg.payload.decode().strip() == "playing":
            pause_bluetooth_playback()
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

mqtt_client = mqtt.Client(client_id="philco-radio-bluetooth-agent")
if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message

mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
mqtt_client.loop_start()  # own thread -- must not block the GLib main loop below


# --- Pairing agent: NoInputNoOutput (Just Works, zero interaction) ---

class Agent(dbus.service.Object):
    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        print(f"Auto-authorizing pairing for {device}")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        # BlueZ shouldn't call this for a NoInputNoOutput agent (Just
        # Works doesn't need confirmation from either side) -- accepting
        # unconditionally here is just a safety net, not the real
        # mechanism, matching this agent's whole "no codes, no
        # confirmation" design.
        print(f"Auto-confirming pairing for {device}")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        # Auto-accept every profile (A2DP, AVRCP, ...) -- physical
        # presence at the volume knob is the security boundary, not a
        # per-service prompt.
        return


def trust_device(device_path):
    try:
        device_obj = bus.get_object("org.bluez", device_path)
        device_props = dbus.Interface(device_obj, "org.freedesktop.DBus.Properties")
        device_props.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
        print(f"Trusted {device_path} -- future reconnects need no pairing/agent step")
    except dbus.DBusException as e:
        print(f"Failed to trust {device_path}: {e}")


def on_properties_changed(interface, changed, invalidated, path=None):
    if interface == "org.bluez.Device1" and changed.get("Paired") is True:
        trust_device(path)
    elif interface == MEDIA_PLAYER_IFACE and "Status" in changed:
        update_playback_state(path, str(changed["Status"]))


bus.add_signal_receiver(
    on_properties_changed,
    dbus_interface="org.freedesktop.DBus.Properties",
    signal_name="PropertiesChanged",
    path_keyword="path",
)


def on_interfaces_added(path, interfaces):
    # Covers a MediaPlayer1 that's already "playing" the instant it
    # appears (fast auto-play apps) -- PropertiesChanged above only fires
    # on a later transition, not the object's initial property values.
    media_player = interfaces.get(MEDIA_PLAYER_IFACE)
    if media_player is not None and "Status" in media_player:
        update_playback_state(path, str(media_player["Status"]))


def on_interfaces_removed(path, interfaces):
    # Covers a phone disconnecting/going out of range without a clean
    # "paused" transition first -- without this, playing_player_paths
    # could get stuck non-empty forever, leaving Spotify/static paused
    # with nothing actually playing over Bluetooth anymore.
    if MEDIA_PLAYER_IFACE in interfaces:
        update_playback_state(path, "removed")


bus.add_signal_receiver(
    on_interfaces_added,
    dbus_interface="org.freedesktop.DBus.ObjectManager",
    signal_name="InterfacesAdded",
    bus_name="org.bluez",
)
bus.add_signal_receiver(
    on_interfaces_removed,
    dbus_interface="org.freedesktop.DBus.ObjectManager",
    signal_name="InterfacesRemoved",
    bus_name="org.bluez",
)

agent = Agent(bus, AGENT_PATH)
manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
manager.RequestDefaultAgent(AGENT_PATH)
print("Bluetooth pairing agent registered (NoInputNoOutput)")

GLib.MainLoop().run()
