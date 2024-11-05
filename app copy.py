import paho.mqtt.client as mqtt
import time
import yaml
import os
import json
import json
import atexit
import sys
import random
import time
from uxr_charger_module import UXRChargerModule

def generate_uuid():
    # Generate random parts of the UUID
    random_part = random.getrandbits(64)
    timestamp = int(time.time() * 1000)  # Get current timestamp in milliseconds
    node = random.getrandbits(48)  # Simulating a network node (MAC address)
    
    # Combine them into UUID format
    uuid_str = f'{timestamp:08x}-{random_part >> 32:04x}-{random_part & 0xFFFF:04x}-{node >> 24:04x}-{node & 0xFFFFFF:06x}'
    return uuid_str

print("Starting up...")

config = {}
script_version = ""

if os.path.exists('/data/options.json'):
    print("Loading options.json")
    with open(r'/data/options.json') as file:
        config = json.load(file)
        print("Config: " + json.dumps(config))

elif os.path.exists('kehua-dev\\config.yaml'):
    print("Loading config.yaml")
    with open(r'kehua-dev\\config.yaml') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)['options']
        
else:
    sys.exit("No config file found")  


scan_interval = config['scan_interval']
port = config['port']
ha_discovery_enabled = config['mqtt_ha_discovery']
code_running = True
kehua_client_connected = False
mqtt_connected = False
print_initial = True
debug_output = config['debug_output']
disc_payload = {}
repub_discovery = 0

kehua_model = None

def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Connected with result code {reason_code}")
    client.will_set(config['mqtt_base_topic'] + "/availability","offline", qos=0, retain=False)
    global mqtt_connected
    mqtt_connected = True

def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    print("MQTT disconnected with result code "+str(reason_code))
    global mqtt_connected
    mqtt_connected = False


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "uxr-{}".format(generate_uuid()))
client.on_connect = on_connect
client.on_disconnect = on_disconnect
#client.on_message = on_message

client.username_pw_set(username=config['mqtt_user'], password=config['mqtt_password'])
client.connect(config['mqtt_host'], config['mqtt_port'], 60)
client.loop_start()
time.sleep(2)

def exit_handler():
    print("Script exiting")
    client.publish(config['mqtt_base_topic'] + "/availability","offline")
    return

atexit.register(exit_handler)

def uxr_connect():
    try:
        print("trying to connect %s" % modbus_ip)
        kehua_client = KehuaClient(modbus_ip, port=modbus_port)
        connected = kehua_client.connect()
        print("Kehua connected")
        return kehua_client, connected
    except IOError as msg:
        print("Kehua error connecting: %s" % msg)
        return False

def ha_discovery(data):
    global ha_discovery_enabled

    if ha_discovery_enabled:
        
        print("Publishing HA Discovery topic...")

        # Define the device information
        device = {
            "manufacturer": "Kehua",
            "model": kehua_model,
            "identifiers": ["kehua_" + kehua_model],
            "name": kehua_model
        }

        # Define the base availability topic for the device
        availability_topic = config['mqtt_base_topic'] + "/availability"

        # Publish a discovery message for each parameter in data
        for parameter, details in data.items():
            # Construct discovery payload for each sensor
            disc_payload = {
                "name": parameter,
                "unique_id": "kehua_" + parameter.replace(" ", "_").lower(),
                "state_topic": f"{config['mqtt_base_topic']}/{parameter.replace(' ', '_').lower()}",
                "availability_topic": availability_topic,
                "device": device
            }

            # Special configuration for text-based fields
            if parameter in ["Device Model", "Hardware Version", "Software Version", "HMI Version", "Manufacturer Info"]:
                disc_payload["value_template"] = "{{ value }}"
                # Explicitly ensure these fields are treated as text
                disc_payload.pop("unit_of_measurement", None)  # Remove unit if it exists
                disc_payload.pop("device_class", None)  # Remove device_class if it exists
                disc_payload.pop("state_class", None)  # Ensure no state_class is set
            
            # Cumulative metrics like Total Charge and Total Discharge
            elif parameter in ["Total Charge", "Total Discharge"]:
                disc_payload["state_class"] = "total_increasing"
                disc_payload["device_class"] = "energy"
                disc_payload["unit_of_measurement"] = "kWh"  # Assuming energy in kWh
            
            # Add device_class and unit_of_measurement based on parameter name for standard types
            elif "temperature" in parameter.lower():
                disc_payload["device_class"] = "temperature"
                disc_payload["unit_of_measurement"] = "°C"
            elif "voltage" in parameter.lower():
                disc_payload["device_class"] = "voltage"
                disc_payload["unit_of_measurement"] = "V"
            elif "current" in parameter.lower():
                disc_payload["device_class"] = "current"
                disc_payload["unit_of_measurement"] = "A"
            elif "power factor" in parameter.lower():
                disc_payload["device_class"] = "power_factor"
                disc_payload.pop("unit_of_measurement", None)  # Remove unit for Power Factor
            elif "apparent power" in parameter.lower():
                disc_payload["device_class"] = "apparent_power"
                disc_payload["unit_of_measurement"] = "kVA"  # Correct unit for apparent power
            elif "reactive power" in parameter.lower():
                disc_payload["device_class"] = "reactive_power"
                disc_payload["unit_of_measurement"] = "kVar"  # Correct unit for reactive power
            elif "active power" in parameter.lower():
                disc_payload["device_class"] = "power"
                disc_payload["unit_of_measurement"] = "kW"
            elif "frequency" in parameter.lower():
                disc_payload["device_class"] = "frequency"
                disc_payload["unit_of_measurement"] = "Hz"

            # Publish the discovery payload to the MQTT discovery topic
            discovery_topic = f"{config['mqtt_ha_discovery_topic']}/sensor/kehua/{parameter.replace(' ', '_').lower()}/config"
            print(f"Publishing discovery message for {parameter}: {disc_payload}")
            client.publish(discovery_topic, json.dumps(disc_payload), qos=0, retain=True)
            
            # Publish the initial value of the parameter as a plain string for text fields
            state_topic = disc_payload["state_topic"]
            client.publish(state_topic, str(details["value"]), qos=0, retain=True)

    else:
        print("HA Discovery Disabled")
        
def publish_state_data(data):
    for parameter, details in data.items():
        # Construct the state topic
        state_topic = f"{config['mqtt_base_topic']}/{parameter.replace(' ', '_').lower()}"
        
        # Extract the value from details
        value = details["value"]
        
        # Special handling for known text fields to ensure they are published as plain strings
        if parameter in ["Device Model", "Hardware Version", "Software Version", "HMI Version", "Manufacturer Info"]:
            # Ensure the value is a plain string
            value = str(value)
            client.publish(state_topic, value, qos=0, retain=True)
            continue  # Skip to the next item after publishing the text field
        
        # Handle arrays for other fields (e.g., Daily Charge, Daily Discharge)
        if isinstance(value, list):
            # Select the most relevant element, assuming the second element here
            value = value[1] if len(value) > 1 else value[0]
        
        # Round larger values to integer if they are over a certain threshold
        if isinstance(value, float) and abs(value) > 500:
            value = round(value)  # Remove decimals for larger values
        
        # Publish the final value as JSON for numerical values
        client.publish(state_topic, json.dumps(value), qos=0, retain=True)

print("Connecting to Kehua...")
kehua_client, kehua_client_connected = kehua_connect()

client.publish(config['mqtt_base_topic'] + "/availability","offline")
print_initial = True

try:
    kehua_model = kehua_client.read_model()
except:
    print("Error retrieving model")
    quit()
    


while code_running == True:

    if kehua_client_connected == True:
        if mqtt_connected == True:
            # READ DATA

            data = kehua_client.read_registers()

            if print_initial:
                ha_discovery(data)

            publish_state_data(data)
                
            client.publish(config['mqtt_base_topic'] + "/availability","online")

            print_initial = False
            time.sleep(scan_interval)

            repub_discovery += 1
            if repub_discovery*scan_interval > 3600:
                repub_discovery = 0
                print_initial = True
        
        else: #MQTT not connected
            client.loop_stop()
            print("MQTT disconnected, trying to reconnect...")
            client.connect(config['mqtt_host'], config['mqtt_port'], 60)
            client.loop_start()
            time.sleep(5)
            print_initial = True
    else: #BMS not connected
        print("Client disconnected, trying to reconnect...")
        kehua_client, kehua_client_connected = kehua_connect()
        client.publish(config['mqtt_base_topic'] + "/availability","offline")
        time.sleep(5)
        print_initial = True

client.loop_stop()
