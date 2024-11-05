import time
import paho.mqtt.client as mqtt
from uxr_charger_module import UXRChargerModule

# MQTT Configuration
MQTT_BROKER = "your_mqtt_broker_address"
MQTT_PORT = 1883
MQTT_TOPICS = [("set/voltage", 0), ("set/current", 0)]  # Topics to subscribe to

# Initialize the UXRChargerModule
module = UXRChargerModule(channel='/dev/ttyACM0')
address = 0x03
group = 0x05

# Static parameters to read once
rated_power = module.get_rated_output_power(address, group)
rated_current = module.get_rated_output_current(address, group)
print(f"Rated Output Power: {rated_power} W")
print(f"Rated Output Current: {rated_current} A")

# MQTT Callbacks
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker")
    client.subscribe(MQTT_TOPICS)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = float(msg.payload.decode())
    if topic == "set/voltage":
        print(f"Setting voltage to {payload} V")
        module.set_voltage(payload, address, group)
    elif topic == "set/current":
        print(f"Setting current limit to {payload} A")
        module.set_current_limit(payload, address, group)

# Initialize MQTT client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Start the MQTT loop in a separate thread
client.loop_start()

# Main loop to continuously read dynamic parameters
try:
    while True:
        # Read and print dynamic parameters
        voltage = module.read_value(0x01, address, group)
        if voltage is not None:
            print(f"Module Voltage: {voltage} V")
        time.sleep(0.2)

        current = module.read_value(0x02, address, group)
        if current is not None:
            print(f"Module Current: {current} A")
        time.sleep(0.2)

        # Add more reads as necessary
except KeyboardInterrupt:
    print("Stopping...")
    client.loop_stop()