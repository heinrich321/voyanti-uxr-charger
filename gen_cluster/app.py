import time
import os
import json
import yaml
import atexit
import paho.mqtt.client as mqtt
from uxr_charger_module import UXRChargerModule
import threading
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(levelname)s - %(message)s",  # Format with timestamp
    datefmt="%Y-%m-%d %H:%M:%S"  # Date format
)

READ_DELAY = 0.05

# Load configuration from config.yaml
if os.path.exists('/data/options.json'):
    logging.info("Loading options.json")
    with open(r'/data/options.json') as file:
        config = json.load(file)
        logging.info("Config: " + json.dumps(config))
elif os.path.exists('uxr-dev\\config.yaml'):
    logging.info("Loading config.yaml")
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
module_address_list = config['module_address']
default_current_limit = config['default_current_limit']
default_voltage = config['default_voltage']

# Initialize the UXRChargerModule
module = UXRChargerModule(channel=config['port'])

group = 0x05

uxr_modules = {}

def keep_alive():
    # Turn on
    for address in module_address_list:
        module.get_input_power(address, group)
        time.sleep(READ_DELAY)

def turn_on():
    for i in range(0, 5):
        time.sleep(1)
        for address in module_address_list:
            module.power_on_off(0x00000000, address, group)
            time.sleep(READ_DELAY)

# Switch on chargers
turn_on()
# Wait 3 seconds for startup
time.sleep(3)

MAX_ATTEMPTS = 1500

# Function to read the serial number with retries
def get_serial_number_with_retries(module, address, group):
    for attempt in range(MAX_ATTEMPTS):
        serial_no = module.get_serial_number(address, group)
        
        if serial_no:  # If the serial number is successfully read
            return str(serial_no)
        
        # Log the attempt and wait before retrying
        logging.error(f"Attempt {attempt + 1} failed, retrying...")
        time.sleep(READ_DELAY)
    
    # If all attempts fail, return None or raise an exception
    logging.error(f"Failed to read serial number after {MAX_ATTEMPTS} attempts.")
    return None


# Loop through each address in the list and create an entry in the devices dictionary
for address in module_address_list:
    serial_no = get_serial_number_with_retries(module, address, group)
    if serial_no == None:
        raise ValueError("Failed to read serial number after 3 attempts.")
    time.sleep(READ_DELAY)
    rated_power = module.get_rated_output_power(address, group)
    time.sleep(READ_DELAY)
    rated_current = module.get_rated_output_current(address, group)
    time.sleep(READ_DELAY)
    uxr_modules[address] = {
        "rated_power": rated_power,
        "rated_current": rated_current,
        "serial_no": serial_no
    }
    time.sleep(READ_DELAY)

    logging.info(f"Address: {address} ")
    logging.info(f"Rated Output Power: {rated_power} W")
    logging.info(f"Rated Output Current: {rated_current} A")
    logging.info(f"Serial No: {serial_no}")
    # Set defaults
    module.set_current_limit(default_current_limit/rated_current, address, group)
    time.sleep(READ_DELAY)
    logging.info(f"Setting default voltage for {serial_no} to {default_voltage}V")
    module.set_output_voltage(default_voltage, address, group)

# MQTT Callbacks
mqtt_connected = False

lock = threading.Lock()  # Create a lock

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    logging.info("Connected to MQTT broker")
    mqtt_connected = True
    for address in uxr_modules:
        serial_no = uxr_modules[address]['serial_no']
        client.subscribe([
            (f"{MQTT_BASE_TOPIC}/{serial_no}/set/group_id", 0),
            (f"{MQTT_BASE_TOPIC}/{serial_no}/set/output_voltage", 0),
            (f"{MQTT_BASE_TOPIC}/{serial_no}/set/current_limit", 0),
            (f"{MQTT_BASE_TOPIC}/{serial_no}/set/current", 0),
            (f"{MQTT_BASE_TOPIC}/{serial_no}/set/power", 0)
        ])

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logging.error("Unexpected disconnection.")
    else:
        logging.error("Disconnected successfully.")
    global mqtt_connected
    logging.error("Disconnected from MQTT broker")
    mqtt_connected = False


def on_message(client, userdata, msg):
    with lock:
        topic = msg.topic
        for address in uxr_modules:
            serial_no = uxr_modules[address]['serial_no']
            if topic == f"{MQTT_BASE_TOPIC}/{serial_no}/set/altitude":
                payload = float(msg.payload.decode())
                module.set_altitude(payload, address, group)
            elif topic == f"{MQTT_BASE_TOPIC}/{serial_no}/set/group_id":
                payload = float(msg.payload.decode())
                module.set_group_id(int(payload), address)
            elif topic == f"{MQTT_BASE_TOPIC}/{serial_no}/set/output_voltage":
                payload = float(msg.payload.decode())
                logging.info(f"Setting output voltage for {serial_no} to {payload}")
                module.set_output_voltage(payload, address, group)
            elif topic == f"{MQTT_BASE_TOPIC}/{serial_no}/set/current_limit":
                payload = float(msg.payload.decode())
                percentage = payload / rated_current
                logging.info("Current limit set: {} for {}%".format(percentage, serial_no))
                module.set_current_limit(percentage, address, group)
            elif topic == f"{MQTT_BASE_TOPIC}/{serial_no}/set/current":
                payload = float(msg.payload.decode())
                module.set_output_current(payload, address, group)
            elif topic == f"{MQTT_BASE_TOPIC}/{serial_no}/set/power":
                payload = int(msg.payload.decode())
                if payload:
                    module.power_on_off(0x00000000, address, group)
                else:
                    module.power_on_off(0x00010000, address, group)
                power_topic = f"{MQTT_BASE_TOPIC}/{serial_no}/power"
                client.publish(power_topic, payload, retain=True)

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
    logging.error("Script exiting")
    for address in uxr_modules:
        serial_no = uxr_modules[address]['serial_no']
        client.publish(f"{MQTT_BASE_TOPIC}_{serial_no}/availability", "offline", retain=True)
    client.loop_stop()

atexit.register(exit_handler)

# HA Discovery Function
def ha_discovery(address):
    uxr_module = uxr_modules[address]
    serial_no = uxr_module['serial_no']
    if ha_discovery_enabled:
        logging.info("Publishing HA Discovery topics...")
        # Define device information
        device = {
            "manufacturer": "UXR",
            "model": "ChargerModule",
            "identifiers": [f"uxr_charger_{serial_no}"],
            "name": f"UXR Charger {serial_no}"
        }

        # Base availability topic
        availability_topic = f"{MQTT_BASE_TOPIC}_{serial_no}/availability"

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
                "unique_id": f"uxr_{serial_no}_{param.replace(' ', '_').lower()}",
                "state_topic": f"{MQTT_BASE_TOPIC}/{serial_no}/{param.replace(' ', '_').lower()}",
                "availability_topic": availability_topic,
                "device": device,
                "device_class": details.get("device_class"),
                "unit_of_measurement": details.get("unit"),
            }
            discovery_topic = f"{MQTT_HA_DISCOVERY_TOPIC}/sensor/uxr_{serial_no}/{param.replace(' ', '_').lower()}/config"
            client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)

        # Define settable parameters as MQTT number entities
        settable_parameters = {
            "Current Limit": {"min": 0, "max": rated_current, "step": 0.1, "unit": "A", "command_topic": f"{MQTT_BASE_TOPIC}/{serial_no}/set/current_limit"},
            "Output Voltage": {"min": 735, "max": 810, "step": 0.1, "unit": "V", "command_topic": f"{MQTT_BASE_TOPIC}/{serial_no}/set/output_voltage"},
            "Output Current": {"min": 0, "max": rated_current, "step": 0.1, "unit": "A", "command_topic": f"{MQTT_BASE_TOPIC}/{serial_no}/set/current"},
            "Altitude": {"min": 0, "max": 5000, "step": 100, "unit": "m", "command_topic": f"{MQTT_BASE_TOPIC}/{serial_no}/set/altitude"},
        }

        # Publish discovery messages for settable parameters
        for param, details in settable_parameters.items():
            discovery_payload = {
                "name": param,
                "unique_id": f"uxr_{serial_no}_{param.replace(' ', '_').lower()}",
                "command_topic": details["command_topic"],
                "min": details["min"],
                "max": details["max"],
                "step": details["step"],
                "unit_of_measurement": details["unit"],
                "availability_topic": availability_topic,
                "device": device
            }
            discovery_topic = f"{MQTT_HA_DISCOVERY_TOPIC}/number/uxr_{serial_no}/{param.replace(' ', '_').lower()}/config"
            client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)


        switch_name = "power"
        command_topic = f"{MQTT_BASE_TOPIC}/{serial_no}/set/{switch_name.lower()}"
        state_topic = f"{MQTT_BASE_TOPIC}/{serial_no}/{switch_name.lower()}"
        unique_id = f"uxr_{serial_no}_{switch_name.lower()}"

        discovery_payload = {
            "name": switch_name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "command_topic": command_topic,
            "payload_on": 1,
            "payload_off": 0,
            "state_on": 1,
            "state_off": 0,
            "availability_topic": availability_topic,
            "device": device
        }

        # Publish discovery message
        discovery_topic = f"{MQTT_HA_DISCOVERY_TOPIC}/switch/uxr_{serial_no}/{switch_name.lower()}/config"
        client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)

        # Optionally publish the initial state
        state_topic = f"{MQTT_BASE_TOPIC}/{serial_no}/{switch_name.lower()}"
        client.publish(state_topic, 1, retain=True)

        client.publish(availability_topic, "online", retain=True)

# Main loop to continuously read parameters
try:
    for address in uxr_modules:
        ha_discovery(address)
    while True:
        for address in uxr_modules:
            uxr_module = uxr_modules[address]
            serial_no = uxr_module['serial_no']
            logging.info("====================")
            logging.info(f"Serial: {serial_no}")
            logging.info(f"Address: {address}")
            alive = False
            # Use lock to ensure thread safety for each sensor reading and publishing
            with lock:
                keep_alive()
                voltage = module.get_module_voltage(address, group)
                if voltage is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/module_voltage", voltage, retain=True)
                    logging.info(f"module_voltage: {voltage}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                current = module.get_module_current(address, group)
                if current is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/module_current", current, retain=True)
                    logging.info(f"module_current: {current}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                current_limit = module.get_module_current_limit(address, group)
                if current_limit is not None:
                    current_limit = round(current_limit * rated_current, 2)
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/current_limit", current_limit, retain=True)
                    logging.info(f"current_limit: {current_limit}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                temp_dc_board = module.get_temperature_dc_board(address, group)
                if temp_dc_board is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/temperature_of_dc_board", temp_dc_board, retain=True)
                    logging.info(f"temperature_of_dc_board: {temp_dc_board}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                input_voltage = module.get_input_phase_voltage(address, group)
                if input_voltage is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/input_phase_voltage", input_voltage, retain=True)
                    logging.info(f"input_phase_voltage: {input_voltage}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                pfc0_voltage = module.get_pfc0_voltage(address, group)
                if pfc0_voltage is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/pfc0_voltage", pfc0_voltage, retain=True)
                    logging.info(f"pfc0_voltage: {pfc0_voltage}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                pfc1_voltage = module.get_pfc1_voltage(address, group)
                if pfc1_voltage is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/pfc1_voltage", pfc1_voltage, retain=True)
                    logging.info(f"pfc1_voltage: {pfc1_voltage}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                panel_temp = module.get_panel_board_temperature(address, group)
                if panel_temp is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/panel_board_temperature", panel_temp, retain=True)
                    logging.info(f"panel_board_temperature: {panel_temp}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                voltage_phase_a = module.get_voltage_phase_a(address, group)
                if voltage_phase_a is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/voltage_phase_a", voltage_phase_a, retain=True)
                    logging.info(f"voltage_phase_a: {voltage_phase_a}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                voltage_phase_b = module.get_voltage_phase_b(address, group)
                if voltage_phase_b is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/voltage_phase_b", voltage_phase_b, retain=True)
                    logging.info(f"voltage_phase_b: {voltage_phase_b}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                voltage_phase_c = module.get_voltage_phase_c(address, group)
                if voltage_phase_c is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/voltage_phase_c", voltage_phase_c, retain=True)
                    logging.info(f"voltage_phase_c: {voltage_phase_c}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                temp_pfc_board = module.get_temperature_pfc_board(address, group)
                if temp_pfc_board is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/temperature_of_pfc_board", temp_pfc_board, retain=True)
                    logging.info(f"temperature_of_pfc_board: {temp_pfc_board}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                input_power = module.get_input_power(address, group)
                if input_power is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/input_power", input_power, retain=True)
                    logging.info(f"input_power: {input_power}")
                    power = 1
                    if input_power > 0:
                        power = 1
                    else:
                        power = 0
                    power_topic = f"{MQTT_BASE_TOPIC}/{serial_no}/power"
                    client.publish(power_topic, power, retain=True)
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                altitude_value = module.get_current_altitude_value(address, group)
                if altitude_value is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/current_altitude", altitude_value, retain=True)
                    logging.info(f"altitude_value: {altitude_value}")
                    alive = True
            time.sleep(READ_DELAY)

            with lock:
                keep_alive()
                input_mode = module.get_input_working_mode(address, group)
                if input_mode is not None:
                    client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/input_working_mode", input_mode, retain=True)
                    logging.info(f"input_working_mode: {input_mode}")
                    alive = True
            time.sleep(READ_DELAY)


            client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/rated_current", rated_current, retain=True)
            client.publish(f"{MQTT_BASE_TOPIC}/{serial_no}/rated_power", rated_power, retain=True)
            if alive:
                client.publish(f"{MQTT_BASE_TOPIC}_{serial_no}/availability", "online", retain=True)
            else:
                client.publish(f"{MQTT_BASE_TOPIC}_{serial_no}/availability", "offline", retain=True)
except Exception as e:
    logging.error(f"An error occurred: {e}")
    exit_handler()
except KeyboardInterrupt:
    logging.error("Stopping script...")
    exit_handler()