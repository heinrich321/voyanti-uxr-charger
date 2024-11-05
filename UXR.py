import struct
import can
import time

class UXRChargerModule:
    source_address = 0xF0
    protno = 0x060

    def __init__(self, channel, bitrate=125000):
        self.bus = can.interface.Bus(channel=channel, interface='slcan', bitrate=bitrate)

    def flush_buffer(self):
        """Flush any existing messages in the CAN buffer."""
        while True:
            message = self.bus.recv(timeout=0.1)
            if message is None:
                break

    def generate_can_arbitration_id(self, protno=0x060, ptp=1, dstaddr=0x00, srcaddr=0x00, group=0):
        if not (0 <= protno <= 0x1FF):
            raise ValueError("PROTNO must be a 9-bit value in the range 0-0x1FF.")
        if not (0 <= ptp <= 1):
            raise ValueError("PTP must be either 0 or 1.")
        if not (0 <= dstaddr <= 0xFF):
            raise ValueError("DSTADDR must be an 8-bit value in the range 0-0xFF.")
        if not (0 <= srcaddr <= 0xFF):
            raise ValueError("SRCADDR must be an 8-bit value in the range 0-0xFF.")
        if not (0 <= group <= 7):
            raise ValueError("GROUP must be a 3-bit value in the range 0-7.")
        
        arbitration_id = (protno << 20) | (ptp << 19) | (dstaddr << 11) | (srcaddr << 3) | group
        return arbitration_id

    def send_frame(self, arbitration_id, data):
        self.flush_buffer()
        frame = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)
        self.bus.send(frame)

    def receive_frame(self):
        message = self.bus.recv()
        if message:
            return message.arbitration_id, message.data
        return None, None

    def float_to_bytes(self, value):
        return struct.pack('>f', value)

    def bytes_to_float(self, value_bytes):
        return struct.unpack('>f', value_bytes)[0]

    def read_value(self, register, address, group, is_float=True):
        data = [0x10, 0x00, 0x00, register, 0x00, 0x00, 0x00, 0x00]
        arbitration_id = self.generate_can_arbitration_id(self.protno, 1, address, self.source_address, group)
        self.send_frame(arbitration_id, data)
        _, response_data = self.receive_frame()
        if response_data and response_data[0] == 0x41:
            if is_float:
                return self.bytes_to_float(response_data[4:8])
            else:
                return struct.unpack('>I', response_data[4:8])[0]
        return None

    # Functions to get specific values
    def get_module_voltage(self, address, group):
        return self.read_value(0x01, address, group)

    def get_module_current(self, address, group):
        return self.read_value(0x02, address, group)

    def get_module_current_limit(self, address, group):
        return self.read_value(0x03, address, group)

    def get_temperature_dc_board(self, address, group):
        return self.read_value(0x04, address, group)

    def get_input_phase_voltage(self, address, group):
        return self.read_value(0x05, address, group)

    def get_pfc0_voltage(self, address, group):
        return self.read_value(0x08, address, group)

    def get_pfc1_voltage(self, address, group):
        return self.read_value(0x0A, address, group)

    def get_panel_board_temperature(self, address, group):
        return self.read_value(0x0B, address, group)

    def get_voltage_phase_a(self, address, group):
        return self.read_value(0x0C, address, group)

    def get_voltage_phase_b(self, address, group):
        return self.read_value(0x0D, address, group)

    def get_voltage_phase_c(self, address, group):
        return self.read_value(0x0E, address, group)

    def get_temperature_pfc_board(self, address, group):
        return self.read_value(0x10, address, group)

    def get_rated_output_power(self, address, group):
        return self.read_value(0x11, address, group)

    def get_rated_output_current(self, address, group):
        return self.read_value(0x12, address, group)

    # Functions to set values
    def set_altitude(self, altitude, address, group):
        if 1000 <= altitude <= 5000:
            altitude_bytes = altitude.to_bytes(2, byteorder='big')
            data = [0x03, 0x00, 0x00, 0x17] + [0x00, 0x00] + list(altitude_bytes)
            arbitration_id = self.generate_can_arbitration_id(self.protno, 1, address, self.source_address, group)
            self.send_frame(arbitration_id, data)

    def set_output_current(self, current, address, group):
        current_value = int(current * 1024)
        current_bytes = current_value.to_bytes(4, byteorder='big')
        data = [0x03, 0x00, 0x00, 0x1B] + list(current_bytes)
        arbitration_id = self.generate_can_arbitration_id(self.protno, 1, address, self.source_address, group)
        self.send_frame(arbitration_id, data)

    def set_group_id(self, group_id, address):
        if 0 <= group_id <= 7:
            data = [0x03, 0x00, 0x00, 0x1E, 0x00, 0x00, 0x00, group_id]
            arbitration_id = self.generate_can_arbitration_id(self.protno, 1, address, self.source_address, 0)
            self.send_frame(arbitration_id, data)

    # More functions can be added for other registers

    def __del__(self):
        if self.bus:
            self.bus.shutdown()

if __name__ == "__main__":
    module = UXRChargerModule(channel='/dev/ttyACM0')
    address = 0x03
    group = 0x05

    while True:
        # Read and print module voltage
        voltage = module.get_module_voltage(address, group)
        if voltage is not None:
            print(f"Module Voltage: {voltage} V")
        time.sleep(0.2)

        # Read and print module current
        current = module.get_module_current(address, group)
        if current is not None:
            print(f"Module Current: {current} A")
        time.sleep(0.2)

        # Read and print module current limit
        current_limit = module.get_module_current_limit(address, group)
        if current_limit is not None:
            print(f"Module Current Limit: {current_limit} A")
        time.sleep(0.2)

        # Read and print temperature of DC board
        temp_dc_board = module.get_temperature_dc_board(address, group)
        if temp_dc_board is not None:
            print(f"Temperature of DC Board: {temp_dc_board} °C")
        time.sleep(0.2)

        # Read and print input phase voltage (DC input voltage)
        input_voltage = module.get_input_phase_voltage(address, group)
        if input_voltage is not None:
            print(f"Input Phase Voltage: {input_voltage} V")
        time.sleep(0.2)

        # Read and print PFC0 voltage
        pfc0_voltage = module.get_pfc0_voltage(address, group)
        if pfc0_voltage is not None:
            print(f"PFC0 Voltage: {pfc0_voltage} V")
        time.sleep(0.2)

        # Read and print PFC1 voltage
        pfc1_voltage = module.get_pfc1_voltage(address, group)
        if pfc1_voltage is not None:
            print(f"PFC1 Voltage: {pfc1_voltage} V")
        time.sleep(0.2)

        # Read and print ambient temperature of panel board
        panel_temp = module.get_panel_board_temperature(address, group)
        if panel_temp is not None:
            print(f"Panel Board Temperature: {panel_temp} °C")
        time.sleep(0.2)

        # Read and print phase A voltage
        voltage_phase_a = module.get_voltage_phase_a(address, group)
        if voltage_phase_a is not None:
            print(f"Voltage Phase A: {voltage_phase_a} V")
        time.sleep(0.2)

        # Read and print phase B voltage
        voltage_phase_b = module.get_voltage_phase_b(address, group)
        if voltage_phase_b is not None:
            print(f"Voltage Phase B: {voltage_phase_b} V")
        time.sleep(0.2)

        # Read and print phase C voltage
        voltage_phase_c = module.get_voltage_phase_c(address, group)
        if voltage_phase_c is not None:
            print(f"Voltage Phase C: {voltage_phase_c} V")
        time.sleep(0.2)

        # Read and print temperature of PFC board
        temp_pfc_board = module.get_temperature_pfc_board(address, group)
        if temp_pfc_board is not None:
            print(f"Temperature of PFC Board: {temp_pfc_board} °C")
        time.sleep(0.2)

        # Read and print rated output power
        rated_power = module.get_rated_output_power(address, group)
        if rated_power is not None:
            print(f"Rated Output Power: {rated_power} W")
        time.sleep(0.2)

        # Read and print rated output current
        rated_current = module.get_rated_output_current(address, group)
        if rated_current is not None:
            print(f"Rated Output Current: {rated_current} A")
        time.sleep(0.2)

        # Continue looping indefinitely