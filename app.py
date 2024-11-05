import time
import os
import json
import yaml
import atexit
import paho.mqtt.client as mqtt
from uxr_charger_module import UXRChargerModule

# Load configuration from config.yaml
if os.path.exists('/data/options.json'):
    print("Loading options.json")
    with open(r'/data/options.json') as file:
        config = json.load(file)
        print("Config: " + json.dumps(config))
elif os.path.exists('uxr-dev\\config.yaml'):
    print("Loading config.yaml")
    with open(r'uxr-dev\\config.yaml') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)['options']
else:
    sys.exit("No config file found")

# Configuration settings
MQTT_BROKER = config['mqtt_host']
MQTT_PORT = config['mqtt_port']
MQTT_BASE_TOPIC = config['mqtt_base_topic']
MQTT_HA_DISCOVERY_TOPIC = config['mqtt_ha_discovery_topic']
mqtt_user = config['mqtt_user']
mqtt_password = config['mqtt_password']
scan_interval = config['scan_interval']
ha_discovery_enabled = config['mqtt_ha_discovery']

# Initialize the UXRChargerModule
module = UXRChargerModule(channel=config['port'])
address = 0x03
group = 0x05

# Static parameters to read once
rated_power = module.get_rated_output_power(address, group)
rated_current = module.get_rated_output_current(address, group)
print(f"Rated Output Power: {rated_power} W")
print(f"Rated Output Current: {rated_current} A")

# MQTT Callbacks
mqtt_connected = False

lock = threading.Lock()  # Create a lock

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    print("Connected to MQTT broker")
    mqtt_connected = True
    client.subscribe([
        (f"{MQTT_BASE_TOPIC}/set/group_id", 0),
        (f"{MQTT_BASE_TOPIC}/set/output_voltage", 0),
        (f"{MQTT_BASE_TOPIC}/set/current_limit", 0),
        (f"{MQTT_BASE_TOPIC}/set/current", 0)
    ])

def on_disconnect(client, userdata, flags, rc):
    global mqtt_connected
    print("Disconnected from MQTT broker")
    mqtt_connected = False


def on_message(client, userdata, msg):
    with lock:
        topic = msg.topic
        payload = float(msg.payload.decode())
        if topic == f"{MQTT_BASE_TOPIC}/set/altitude":
            module.set_altitude(payload, address, group)
        elif topic == f"{MQTT_BASE_TOPIC}/set/group_id":
            module.set_group_id(int(payload), address)
        elif topic == f"{MQTT_BASE_TOPIC}/set/output_voltage":
            module.set_output_voltage(payload, address, group)
        elif topic == f"{MQTT_BASE_TOPIC}/set/current_limit":
            percentage = payload / rated_current
            print("Current limit set: {}%".format(percentage))
            module.set_current_limit(percentage, address, group)
        elif topic == f"{MQTT_BASE_TOPIC}/set/current":
            module.set_output_current(payload, address, group)

# Initialize MQTT client
client = mqtt.Client()
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.username_pw_set(username=mqtt_user, password=mqtt_password)
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# Clean up on exit
def exit_handler():
    print("Script exiting")
    client.publish(f"{MQTT_BASE_TOPIC}/availability", "offline", retain=True)
    client.loop_stop()

atexit.register(exit_handler)

# HA Discovery Function
def ha_discovery():
    if ha_discovery_enabled:
        print("Publishing HA Discovery topics...")
        # Define device information
        device = {
            "manufacturer": "UXR",
            "model": "ChargerModule",
            "identifiers": ["uxr_charger"],
            "name": "UXR Charger"
        }

        # Base availability topic
        availability_topic = f"{MQTT_BASE_TOPIC}/availability"

        # Define all sensor parameters and publish discovery messages
        parameters = {
            "Module Voltage": {"device_class": "voltage", "unit": "V"},
            "Module Current": {"device_class": "current", "unit": "A"},
            "Rated Current": {"device_class": "current", "unit": "A"},
            "Rated Power": {"device_class": "current", "unit": "W"},
            "Current Limit": {"device_class": "current", "unit": "A"},
            "Temperature of DC Board": {"device_class": "temperature", "unit": "°C"},
            "Input Phase Voltage": {"device_class": "voltage", "unit": "V"},
            "PFC0 Voltage": {"device_class": "voltage", "unit": "V"},
            "PFC1 Voltage": {"device_class": "voltage", "unit": "V"},
            "Panel Board Temperature": {"device_class": "temperature", "unit": "°C"},
            "Voltage Phase A": {"device_class": "voltage", "unit": "V"},
            "Voltage Phase B": {"device_class": "voltage", "unit": "V"},
            "Voltage Phase C": {"device_class": "voltage", "unit": "V"},
            "Temperature of PFC Board": {"device_class": "temperature", "unit": "°C"},
            "Input Power": {"device_class": "power", "unit": "W"},
            "Current Altitude": {"device_class": "none", "unit": "m"},
            "Input Working Mode": {"device_class": "none", "unit": None},
            "Alarm Status": {"device_class": "none", "unit": None}
        }

        for param, details in parameters.items():
            discovery_payload = {
                "name": param,
                "unique_id": f"uxr_{param.replace(' ', '_').lower()}",
                "state_topic": f"{MQTT_BASE_TOPIC}/{param.replace(' ', '_').lower()}",
                "availability_topic": availability_topic,
                "device": device,
                "device_class": details.get("device_class"),
                "unit_of_measurement": details.get("unit"),
            }
            discovery_topic = f"{MQTT_HA_DISCOVERY_TOPIC}/sensor/uxr/{param.replace(' ', '_').lower()}/config"
            client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)

        # Define settable parameters as MQTT number entities
        settable_parameters = {
            "Current Limit": {"min": 0, "max": rated_current, "step": 0.1, "unit": "A", "command_topic": f"{MQTT_BASE_TOPIC}/set/current_limit"},
            "Output Voltage": {"min": 0, "max": 500, "step": 0.1, "unit": "V", "command_topic": f"{MQTT_BASE_TOPIC}/set/output_voltage"},
            "Output Current": {"min": 0, "max": rated_current, "step": 0.1, "unit": "A", "command_topic": f"{MQTT_BASE_TOPIC}/set/current"},
            "Altitude": {"min": 1000, "max": 5000, "step": 100, "unit": "m", "command_topic": f"{MQTT_BASE_TOPIC}/set/altitude"}
        }

        # Publish discovery messages for settable parameters
        for param, details in settable_parameters.items():
            discovery_payload = {
                "name": param,
                "unique_id": f"uxr_{param.replace(' ', '_').lower()}",
                "command_topic": details["command_topic"],
                "min": details["min"],
                "max": details["max"],
                "step": details["step"],
                "unit_of_measurement": details["unit"],
                "availability_topic": availability_topic,
                "device": device
            }
            discovery_topic = f"{MQTT_HA_DISCOVERY_TOPIC}/number/uxr/{param.replace(' ', '_').lower()}/config"
            client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)

        client.publish(availability_topic, "online", retain=True)

# Main loop to continuously read parameters
try:
    ha_discovery()
    while True:
        # Use lock to ensure thread safety for each sensor reading and publishing
        with lock:
            voltage = module.get_module_voltage(address, group)
            if voltage is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/module_voltage", voltage, retain=True)
        time.sleep(0.2)

        with lock:
            current = module.get_module_current(address, group)
            if current is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/module_current", current, retain=True)
        time.sleep(0.2)

        with lock:
            current_limit = module.get_module_current_limit(address, group)
            if current_limit is not None:
                current_limit = current_limit * rated_current
                client.publish(f"{MQTT_BASE_TOPIC}/current_limit", current_limit, retain=True)
                print("Current limit get: {}%".format(current_limit))
        time.sleep(0.2)

        with lock:
            temp_dc_board = module.get_temperature_dc_board(address, group)
            if temp_dc_board is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/temperature_of_dc_board", temp_dc_board, retain=True)
        time.sleep(0.2)

        with lock:
            input_voltage = module.get_input_phase_voltage(address, group)
            if input_voltage is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/input_phase_voltage", input_voltage, retain=True)
        time.sleep(0.2)

        with lock:
            pfc0_voltage = module.get_pfc0_voltage(address, group)
            if pfc0_voltage is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/pfc0_voltage", pfc0_voltage, retain=True)
        time.sleep(0.2)

        with lock:
            pfc1_voltage = module.get_pfc1_voltage(address, group)
            if pfc1_voltage is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/pfc1_voltage", pfc1_voltage, retain=True)
        time.sleep(0.2)

        with lock:
            panel_temp = module.get_panel_board_temperature(address, group)
            if panel_temp is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/panel_board_temperature", panel_temp, retain=True)
        time.sleep(0.2)

        with lock:
            voltage_phase_a = module.get_voltage_phase_a(address, group)
            if voltage_phase_a is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/voltage_phase_a", voltage_phase_a, retain=True)
        time.sleep(0.2)

        with lock:
            voltage_phase_b = module.get_voltage_phase_b(address, group)
            if voltage_phase_b is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/voltage_phase_b", voltage_phase_b, retain=True)
        time.sleep(0.2)

        with lock:
            voltage_phase_c = module.get_voltage_phase_c(address, group)
            if voltage_phase_c is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/voltage_phase_c", voltage_phase_c, retain=True)
        time.sleep(0.2)

        with lock:
            temp_pfc_board = module.get_temperature_pfc_board(address, group)
            if temp_pfc_board is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/temperature_of_pfc_board", temp_pfc_board, retain=True)
        time.sleep(0.2)

        with lock:
            input_power = module.get_input_power(address, group)
            if input_power is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/input_power", input_power, retain=True)
        time.sleep(0.2)

        with lock:
            altitude_value = module.get_current_altitude_value(address, group)
            if altitude_value is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/current_altitude", altitude_value, retain=True)
        time.sleep(0.2)

        with lock:
            input_mode = module.get_input_working_mode(address, group)
            if input_mode is not None:
                client.publish(f"{MQTT_BASE_TOPIC}/input_working_mode", input_mode, retain=True)
        time.sleep(0.2)

        client.publish(f"{MQTT_BASE_TOPIC}/rated_current", rated_current, retain=True)
        client.publish(f"{MQTT_BASE_TOPIC}/rated_power", rated_power, retain=True)

except KeyboardInterrupt:
    print("Stopping script...")
    exit_handler()