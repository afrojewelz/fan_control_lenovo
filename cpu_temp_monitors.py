#!/usr/bin/env python3

import subprocess
import time
import re
import sched

###############################################################################
# Configuration: All variables here
###############################################################################
CPU_SENSORS_CHECK_INTERVAL = 5
NIC_SENSORS_CHECK_INTERVAL = 5    # seconds
HDD_SENSORS_CHECK_INTERVAL = 60   # seconds

# CPU temperature thresholds: [ [temp_threshold, fan_value], ... ]
#   If CPU temp >= temp_threshold, fan_value is applied.
CPU_THRESHOLDS = [
    [1,   0x01],
    [27,  0x01],
    [33,  0x01],
    [37,  0x03],
    [42,  0x03],
    [49,  0x03],
    [54,  0x05],
    [59,  0x05],
    [64,  0x05],
    [69,  0x06],
    [73,  0x06],
    [79,  0x06],
    [80,  0x07],
    [87,  0x07],
]

NIC_THRESHOLDS = [
    [1,   0x01],
    [27,  0x01],
    [33,  0x01],
    [37,  0x03],
    [42,  0x03],
    [49,  0x03],
    [54,  0x05],
    [59,  0x05],
    [64,  0x05],
    [69,  0x06],
    [73,  0x06],
    [79,  0x06],
    [80,  0x07],
    [87,  0x07],
]

# HDD temperature thresholds: [ [temp_threshold, fan_value], ... ]
#   If HDD temp >= temp_threshold, fan_value is applied.
HDD_THRESHOLDS = [
    [1,   0x01],
    [22,  0x02],
    [28,  0x02],
    [34,  0x02],
    [37,  0x03],
    [42,  0x03],
    [47,  0x04],
    [51,  0x05],
    [57,  0x06],
    [61,  0x07],
]

# List of HDD devices you want to monitor. Adjust as needed.
HDD_LIST = [
      "/dev/nvme0",
      "/dev/nvme1",
      "/dev/nvme2",
      "/dev/nvme3",
    # "/dev/sda",
    # "/dev/sdb",
    # "/dev/sdc",
    # "/dev/sdd",
    # "/dev/sde",
    # "/dev/sdf",
    # "/dev/sdg",
    # "/dev/sdh",
    # "/dev/sdi",
    # "/dev/sdj",
    # "/dev/sdk",
    # "/dev/sdl",
]
###############################################################################

# Global variables for storing current fan speed needs
cpu_fan_speed = 0x03
hdd_fan_speed = 0x03
nic_fan_speed = 0x03

# Create a global scheduler
scheduler = sched.scheduler(time.time, time.sleep)

def get_cpu_temperature():
    """Runs 'sensors' and returns CPU Tctl temp as float, or None."""
    try:
        output = subprocess.check_output(["sensors"]).decode("utf-8")
        match = re.search(r"Tctl:\s*\++([\d.]+)°C", output)
        if match:
            return float(match.group(1))
        else:
            print("[WARN] Could not find Tctl temperature in 'sensors' output.")
            return None
    except Exception as e:
        print(f"[ERROR] get_cpu_temperature() -> {e}")
        return None

def get_nic_temperature():
    """Runs 'sensors' and returns NIC temperature as float, or None."""
    try:
        output = subprocess.check_output(["sensors"]).decode("utf-8")
        nic_temp = None
        for nic in ["be2net", "mlx5"]:
            match = re.search(rf"{nic}-\w+.*\n\s*Adapter: PCI adapter\n\s*(?:sensor0|temp1):\s*\++([\d.]+)°C", output, re.MULTILINE)
            print(match)
            if match:
                nic_temp = float(match.group(1))
                print(f"[INFO] {nic} temperature: {nic_temp}°C")
                break
        if nic_temp is None:
            print("[WARN] Could not find NIC temperature in 'sensors' output.")
        return nic_temp
    except Exception as e:
        print(f"[ERROR] get_nic_temperature() -> {e}")
        return None

def get_hdd_temperature():
    """Parses 'tempnvme.sh' output and returns a dictionary with device temperatures."""
    try:
        output = subprocess.check_output(["/root/tempnvme.sh"]).decode("utf-8")
        temperatures = {}
        for nvme in HDD_LIST:
            match = re.search(rf"{nvme}.*\n\s*Adapter: PCI adapter\n\s*sensor0:\s*\++([\d.]+)°C", output, re.MULTILINE)
            if match:
                temp = match.group(1)
                temperatures[nvme] = float(temp)
        return temperatures
    except Exception as e:
        print(f"[ERROR] get_hdd_temperature() -> {e}")
        return {}

def choose_fan_value(temperature, thresholds):
    """
    Given a measured temperature and a threshold list,
    pick a fan value in ascending threshold order.
    """
    chosen_value = 1
    for threshold, fan_val in thresholds:
        if temperature >= threshold:
            chosen_value = fan_val
        else:
            break
    return chosen_value

def set_fan_speed(fan_speed):
    """
    Construct and run the ipmitool raw command to set the fan speed.
    """
    fan_speed = max(0x01, min(fan_speed, 0x64))
    command = [
        "ipmitool", "raw", "0x3c", "0x30", "0x00", "0x00",
        str(fan_speed)
    ]
    print(f"[INFO] Setting fan speed to {fan_speed} (command: {' '.join(command)})")
    try:
        subprocess.run(command, check=True)
        print(f"[INFO] Fan speed successfully set to {fan_speed}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to set fan speed: {e}")

def update_final_fan_speed():
    """
    Decide the final fan speed (the higher of CPU, HDD, and NIC)
    and set it via ipmitool.
    """
    global cpu_fan_speed, hdd_fan_speed, nic_fan_speed
    final_speed = max(cpu_fan_speed, hdd_fan_speed, nic_fan_speed)
    print(f"[DECISION] CPU={cpu_fan_speed}, HDD={hdd_fan_speed}, NIC={nic_fan_speed} -> final={final_speed}")
    set_fan_speed(final_speed)

def check_cpu():
    """
    Check CPU temperature, compute required fan speed,
    update the global 'cpu_fan_speed', then schedule next check.
    """
    global cpu_fan_speed

    cpu_temp = get_cpu_temperature()
    if cpu_temp is not None:
        cpu_fan_speed = choose_fan_value(cpu_temp, CPU_THRESHOLDS)
        print(f"[CPU] Temp={cpu_temp}°C -> cpu_fan_speed={cpu_fan_speed}")
    else:
        print("[WARN] Could not read CPU temperature; leaving cpu_fan_speed as is.")

    # After updating CPU fan speed, decide final fan speed
    update_final_fan_speed()

    # Schedule the next CPU check
    scheduler.enter(CPU_SENSORS_CHECK_INTERVAL, 1, check_cpu)

def check_nic():
    """
    Check NIC temperature, compute required fan speed,
    update the global 'nic_fan_speed', then schedule next check.
    """
    global nic_fan_speed

    nic_temp = get_nic_temperature()
    if nic_temp is not None:
        nic_fan_speed = choose_fan_value(nic_temp, NIC_THRESHOLDS)
        print(f"[NIC] Temp={nic_temp}°C -> nic_fan_speed={nic_fan_speed}")
    else:
        print("[WARN] Could not read NIC temperature; leaving nic_fan_speed as is.")

    # After updating NIC fan speed, decide final fan speed
    update_final_fan_speed()

    # Schedule the next NIC check
    scheduler.enter(NIC_SENSORS_CHECK_INTERVAL, 1, check_nic)

# Update the check_hdds function to use the new get_hdd_temperature()
def check_hdds():
    """Check all HDDs, find the max temp, compute required fan speed,
    update the global 'hdd_fan_speed', then schedule next check."""
    global hdd_fan_speed

    max_hdd_temp = 0.0
    print("[INFO] Checking HDD temperatures...")
    hdd_temperatures = get_hdd_temperature()
    for device, hdd_temp in hdd_temperatures.items():
        print(f"[HDD] {device}: {hdd_temp}°C")
        if hdd_temp > max_hdd_temp:
            max_hdd_temp = hdd_temp

    hdd_fan_speed = choose_fan_value(max_hdd_temp, HDD_THRESHOLDS)
    print(f"[HDD] Max HDD Temp={max_hdd_temp}°C -> hdd_fan_speed={hdd_fan_speed}")

    # After updating HDD fan speed, decide final fan speed
    update_final_fan_speed()

    # Schedule the next HDD check
    scheduler.enter(HDD_SENSORS_CHECK_INTERVAL, 2, check_hdds)

def main():
    print("[START] Starting scheduled temperature monitoring...")

    # Schedule initial calls
    scheduler.enter(0, 1, check_cpu)   # Start CPU checks immediately
    scheduler.enter(0, 2, check_hdds)  # Start HDD checks immediately
    scheduler.enter(0, 3, check_nic)   # Start NIC checks immediately

    # Run the scheduler (blocks until the script exits)
    scheduler.run()

if __name__ == "__main__":
    main()
