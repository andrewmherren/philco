#!/usr/bin/env python3
# BlueZ pairing agent for the philco radio. Always-discoverable. Real phones
# negotiate Numeric Comparison against our DisplayOnly capability (not
# Passkey Entry -- that's only used when the peer is keyboard-only, which
# modern phones aren't), meaning BOTH sides must independently confirm the
# same code. If we auto-confirmed on our side, that would be no security at
# all: anyone's phone could tap "confirm" and pair. So RequestConfirmation
# below blocks and waits for an actual human to tap Pair/Cancel on
# philco-ui's touchscreen (relayed via MQTT) before telling BlueZ whether to
# proceed -- that's the actual security boundary, not the code itself.
import os
import threading

import dbus
import dbus.mainloop.glib
import dbus.service
import paho.mqtt.client as mqtt
from gi.repository import GLib

TOPIC_CODE = "philco/pairing/code"
TOPIC_STATE = "philco/pairing/state"
TOPIC_RESPONSE = "philco/pairing/response"
CONFIRMATION_TIMEOUT_SECONDS = 60

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()

agent_path = "/philco/agent"


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

mqtt_client = mqtt.Client(client_id="philco-radio-bt-agent")
if MQTT_USERNAME:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Filled in by RequestConfirmation while it's waiting for a response, read
# by on_message (which runs on paho's own background thread) when the user
# taps Pair/Cancel on philco-ui.
pending_confirmation = {"event": None, "response": None}


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected")
        client.subscribe(TOPIC_RESPONSE)
    else:
        print(f"MQTT connect refused, rc={rc} (0=ok, 4=bad user/pass, 5=not authorized)")


def on_disconnect(client, userdata, rc):
    print(f"MQTT disconnected, rc={rc}")


def on_message(client, userdata, msg):
    if msg.topic != TOPIC_RESPONSE:
        return
    pending_confirmation["response"] = msg.payload.decode().strip()
    event = pending_confirmation["event"]
    if event:
        event.set()


mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message


def mqtt_connect():
    try:
        mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"MQTT connect error (will keep retrying in background): {e}")


mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
mqtt_connect()


def publish_code(code):
    print(f"Publishing pairing code: {code}")
    mqtt_client.publish(TOPIC_CODE, code, retain=True)
    mqtt_client.publish(TOPIC_STATE, "active", retain=True)


def clear_code(reason):
    print(f"Clearing pairing code ({reason})")
    mqtt_client.publish(TOPIC_CODE, "", retain=True)
    mqtt_client.publish(TOPIC_STATE, "idle", retain=True)


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class Agent(dbus.service.Object):
    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        code = f"{passkey:06d}"
        print(f"DisplayPasskey for {device}: {code} (entered={entered})")
        publish_code(code)

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        print(f"DisplayPinCode for {device}: {pincode}")
        publish_code(pincode)

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        code = f"{passkey:06d}"
        print(f"RequestConfirmation for {device}: {code} -- waiting up to "
              f"{CONFIRMATION_TIMEOUT_SECONDS}s for a human to confirm on philco-ui")
        publish_code(code)

        event = threading.Event()
        pending_confirmation["event"] = event
        pending_confirmation["response"] = None

        got_response = event.wait(timeout=CONFIRMATION_TIMEOUT_SECONDS)
        response = pending_confirmation["response"]
        pending_confirmation["event"] = None

        clear_code("confirmation resolved")

        if got_response and response == "confirm":
            print(f"Pairing confirmed on philco-ui for {device}")
            return
        print(f"Pairing rejected for {device} (got_response={got_response}, response={response})")
        raise Rejected("Not confirmed on the radio's screen")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        clear_code("pairing cancelled")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        return


def on_properties_changed(interface, changed, invalidated, path=None):
    # Clear the on-screen code as soon as pairing actually succeeds, rather
    # than waiting for Cancel (which only fires on failure/timeout).
    if interface == "org.bluez.Device1" and changed.get("Paired") is True:
        clear_code("pairing succeeded")


bus.add_signal_receiver(
    on_properties_changed,
    dbus_interface="org.freedesktop.DBus.Properties",
    signal_name="PropertiesChanged",
    path_keyword="path",
)

bus_object = bus.get_object("org.bluez", "/org/bluez")
manager = dbus.Interface(bus_object, "org.bluez.AgentManager1")
agent = Agent(bus, agent_path)
manager.RegisterAgent(agent_path, "DisplayOnly")
manager.RequestDefaultAgent(agent_path)

loop = GLib.MainLoop()
loop.run()
