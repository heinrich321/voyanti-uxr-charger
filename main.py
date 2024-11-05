import time
import paho.mqtt.client as mqtt
from uxr_charger_module import UXRChargerModule

# Initialize the UXRChargerModule
module = UXRChargerModule(channel='/dev/ttyACM0')
address = 0x03
group = 0x05

# Static parameters to read once
rated_power = module.get_rated_output_power(address, group)
rated_current = module.get_rated_output_current(address, group)
print(f"Rated Output Power: {rated_power} W")
print(f"Rated Output Current: {rated_current} A")

# Main loop to continuously read all dynamic parameters
try:
    while True:
        # Read and print module voltage
        voltage = module.read_value(0x01, address, group)
        if voltage is not None:
            print(f"Module Voltage: {voltage} V")
        time.sleep(0.2)

        # Read and print module current
        current = module.read_value(0x02, address, group)
        if current is not None:
            print(f"Module Current: {current} A")
        time.sleep(0.2)

        # Read and print temperature of DC board
        temp_dc_board = module.read_value(0x04, address, group)
        if temp_dc_board is not None:
            print(f"Temperature of DC Board: {temp_dc_board} °C")
        time.sleep(0.2)

        # Read and print input phase voltage
        input_voltage = module.read_value(0x05, address, group)
        if input_voltage is not None:
            print(f"Input Phase Voltage: {input_voltage} V")
        time.sleep(0.2)

        # Read and print PFC0 voltage
        pfc0_voltage = module.read_value(0x08, address, group)
        if pfc0_voltage is not None:
            print(f"PFC0 Voltage: {pfc0_voltage} V")
        time.sleep(0.2)

        # Read and print PFC1 voltage
        pfc1_voltage = module.read_value(0x0A, address, group)
        if pfc1_voltage is not None:
            print(f"PFC1 Voltage: {pfc1_voltage} V")
        time.sleep(0.2)

        # Read and print ambient temperature of panel board
        panel_temp = module.read_value(0x0B, address, group)
        if panel_temp is not None:
            print(f"Panel Board Temperature: {panel_temp} °C")
        time.sleep(0.2)

        # Read and print phase A voltage
        voltage_phase_a = module.read_value(0x0C, address, group)
        if voltage_phase_a is not None:
            print(f"Voltage Phase A: {voltage_phase_a} V")
        time.sleep(0.2)

        # Read and print phase B voltage
        voltage_phase_b = module.read_value(0x0D, address, group)
        if voltage_phase_b is not None:
            print(f"Voltage Phase B: {voltage_phase_b} V")
        time.sleep(0.2)

        # Read and print phase C voltage
        voltage_phase_c = module.read_value(0x0E, address, group)
        if voltage_phase_c is not None:
            print(f"Voltage Phase C: {voltage_phase_c} V")
        time.sleep(0.2)

        # Read and print temperature of PFC board
        temp_pfc_board = module.read_value(0x10, address, group)
        if temp_pfc_board is not None:
            print(f"Temperature of PFC Board: {temp_pfc_board} °C")
        time.sleep(0.2)

        # Read and print input power
        input_power = module.read_value(0x48, address, group, is_float=False)
        if input_power is not None:
            print(f"Input Power: {input_power} W")
        time.sleep(0.2)

        # Read and print current altitude value
        altitude_value = module.read_value(0x4A, address, group, is_float=False)
        if altitude_value is not None:
            print(f"Current Altitude: {altitude_value} m")
        time.sleep(0.2)

        # Read and print input working mode
        input_mode = module.read_value(0x4B, address, group, is_float=False)
        if input_mode is not None:
            print(f"Input Working Mode: {input_mode}")
        time.sleep(0.2)

        # Read and print alarm status
        alarm_status = module.get_alarm_status(address, group)
        if alarm_status is not None:
            print(f"Alarm Status: {alarm_status}")
        time.sleep(0.2)

        # Read and print alarm status
        serial = module.get_serial_number(address, group)
        if serial is not None:
            print(f"Serial No: {serial}")
        time.sleep(0.2)

except KeyboardInterrupt:
    print("Stopping...")