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

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    print("Connected to MQTT broker")
    mqtt_connected = True
    client.subscribe([(f"{MQTT_BASE_TOPIC}/set/voltage", 0), (f"{MQTT_BASE_TOPIC}/set/current", 0)])

def on_disconnect(client, userdata, flags, rc):
    global mqtt_connected
    print("Disconnected from MQTT broker")
    mqtt_connected = False

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = float(msg.payload.decode())
    if topic == f"{MQTT_BASE_TOPIC}/set/voltage":
        print(f"Setting voltage to {payload} V")
        module.set_output_voltage(payload, address, group)
    elif topic == f"{MQTT_BASE_TOPIC}/set/current":
        print(f"Setting current limit to {payload} A")
        module.set_current_limit(payload, address, group)

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
            "Module Voltage": {"device_class": "voltage", "unit": "V", "value": None},
            "Module Current": {"device_class": "current", "unit": "A", "value": None},
            "Temperature of DC Board": {"device_class": "temperature", "unit": "°C", "value": None},
            "Input Phase Voltage": {"device_class": "voltage", "unit": "V", "value": None},
            "PFC0 Voltage": {"device_class": "voltage", "unit": "V", "value": None},
            "PFC1 Voltage": {"device_class": "voltage", "unit": "V", "value": None},
            "Panel Board Temperature": {"device_class": "temperature", "unit": "°C", "value": None},
            "Voltage Phase A": {"device_class": "voltage", "unit": "V", "value": None},
            "Voltage Phase B": {"device_class": "voltage", "unit": "V", "value": None},
            "Voltage Phase C": {"device_class": "voltage", "unit": "V", "value": None},
            "Temperature of PFC Board": {"device_class": "temperature", "unit": "°C", "value": None},
            "Input Power": {"device_class": "power", "unit": "W", "value": None},
            "Current Altitude": {"device_class": "none", "unit": "m", "value": None},
            "Input Working Mode": {"device_class": "none", "unit": None, "value": None},
            "Alarm Status": {"device_class": "none", "unit": None, "value": None},
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

            # Publish to HA discovery topic
            discovery_topic = f"{MQTT_HA_DISCOVERY_TOPIC}/sensor/uxr/{param.replace(' ', '_').lower()}/config"
            client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)

        # Publish initial availability status
        client.publish(availability_topic, "online", retain=True)

# Main loop to continuously read parameters
try:
    ha_discovery()
    while True:
        # Read and publish sensor data
        voltage = module.read_value(0x01, address, group)
        if voltage is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/module_voltage", voltage, retain=True)

        current = module.read_value(0x02, address, group)
        if current is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/module_current", current, retain=True)

        temp_dc_board = module.read_value(0x04, address, group)
        if temp_dc_board is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/temperature_of_dc_board", temp_dc_board, retain=True)

        input_voltage = module.read_value(0x05, address, group)
        if input_voltage is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/input_phase_voltage", input_voltage, retain=True)

        pfc0_voltage = module.read_value(0x08, address, group)
        if pfc0_voltage is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/pfc0_voltage", pfc0_voltage, retain=True)

        pfc1_voltage = module.read_value(0x0A, address, group)
        if pfc1_voltage is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/pfc1_voltage", pfc1_voltage, retain=True)

        panel_temp = module.read_value(0x0B, address, group)
        if panel_temp is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/panel_board_temperature", panel_temp, retain=True)

        voltage_phase_a = module.read_value(0x0C, address, group)
        if voltage_phase_a is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/voltage_phase_a", voltage_phase_a, retain=True)

        voltage_phase_b = module.read_value(0x0D, address, group)
        if voltage_phase_b is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/voltage_phase_b", voltage_phase_b, retain=True)

        voltage_phase_c = module.read_value(0x0E, address, group)
        if voltage_phase_c is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/voltage_phase_c", voltage_phase_c, retain=True)

        temp_pfc_board = module.read_value(0x10, address, group)
        if temp_pfc_board is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/temperature_of_pfc_board", temp_pfc_board, retain=True)

        input_power = module.read_value(0x48, address, group, is_float=False)
        if input_power is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/input_power", input_power, retain=True)

        altitude_value = module.read_value(0x4A, address, group, is_float=False)
        if altitude_value is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/current_altitude", altitude_value, retain=True)

        input_mode = module.read_value(0x4B, address, group, is_float=False)
        if input_mode is not None:
            client.publish(f"{MQTT_BASE_TOPIC}/input_working_mode", input_mode, retain=True)

        # alarm_status = module.get_alarm_status(address, group)
        # if alarm_status is not None:
        #     client.publish(f"{MQTT_BASE_TOPIC}/alarm_status", alarm_status, retain=True)

        # Wait before the next scan
        time.sleep(scan_interval)

except KeyboardInterrupt:
    print("Stopping script...")
    exit_handler()