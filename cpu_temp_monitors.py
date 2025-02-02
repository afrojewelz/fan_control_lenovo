#!/usr/bin/env python3

import subprocess
import time
import re
import sched

###############################################################################
# Configuration: All variables here
###############################################################################
CPU_SENSORS_CHECK_INTERVAL = 5    # seconds
HDD_SENSORS_CHECK_INTERVAL = 60   # seconds

# CPU temperature thresholds: [ [temp_threshold, fan_value], ... ]
#   If CPU temp >= temp_threshold, fan_value is applied.
CPU_THRESHOLDS = [
    [0,   0],
    [47,  1],
    [48,  2],
    [49,  3],
    [50,  4],
    [51,  5],
    [52,  6],
    [53,  7],
    [54,  8],
    [55,  10],
    [60,  20],
    [65,  25],
    [70,  35],
    [75,  100],
]

# HDD temperature thresholds: [ [temp_threshold, fan_value], ... ]
#   If HDD temp >= temp_threshold, fan_value is applied.
HDD_THRESHOLDS = [
    [0,   0],
    [55,  10],
    [58,  20],
    [60,  30],
    [65,  50],
    [75,  100],
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
cpu_fan_speed = 0
hdd_fan_speed = 0

# Create a global scheduler
scheduler = sched.scheduler(time.time, time.sleep)

def get_cpu_temperature():
    """Runs 'sensors' and returns CPU Tctl temp as float, or None."""
    try:
        output = subprocess.check_output(["sensors"]).decode("utf-8")
        match = re.search(r"Tctl:\s*\+([\d.]+)°C", output)
        if match:
            return float(match.group(1))
        else:
            print("[WARN] Could not find Tctl temperature in 'sensors' output.")
            return None
    except Exception as e:
        print(f"[ERROR] get_cpu_temperature() -> {e}")
        return None

def get_hdd_temperature(device):
    """Runs 'smartctl -A <device>' and returns 'Current Drive Temperature' as float, or None."""
    try:
        output = subprocess.check_output(["smartctl", "-A", device]).decode("utf-8")
        # Example line: "Current Drive Temperature:     50 C"
        match = re.search(r"Current Drive Temperature:\s+(\d+)\s*C", output)
        if match:
            return float(match.group(1))
        else:
            print(f"[WARN] Could not parse temperature for {device}.")
            return None
    except Exception as e:
        print(f"[ERROR] get_hdd_temperature({device}) -> {e}")
        return None

def choose_fan_value(temperature, thresholds):
    """
    Given a measured temperature and a threshold list,
    pick a fan value in ascending threshold order.
    """
    chosen_value = 0
    for threshold, fan_val in thresholds:
        if temperature >= threshold:
            chosen_value = fan_val
        else:
            break
    return chosen_value

def set_fan_speed(fan_speed):
    """
    Construct and run the ipmitool raw command to set the fan speed.
    # auto 0x01 0x00全局 0x01-6 风扇号码 最后0x01-0x64为风扇速度
    # ipmitool raw 0x3c 0x30 0x00 0x00 0x64  # 设置到 100%  
    # ipmitool raw 0x3c 0x30 0x01 0x00 0x00  # 可能的自动模式命令
    ipmitool raw 0x3c 0x30 0x00 0x00 <fan_speed>
    """
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
    Decide the final fan speed (the higher of CPU vs HDD)
    and set it via ipmitool.
    """
    global cpu_fan_speed, hdd_fan_speed
    final_speed = max(cpu_fan_speed, hdd_fan_speed)
    print(f"[DECISION] CPU={cpu_fan_speed}, HDD={hdd_fan_speed} -> final={final_speed}")
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

def check_hdds():
    """
    Check all HDDs, find the max temp, compute required fan speed,
    update the global 'hdd_fan_speed', then schedule next check.
    """
    global hdd_fan_speed

    max_hdd_temp = 0.0
    print("[INFO] Checking HDD temperatures...")
    for device in HDD_LIST:
        hdd_temp = get_hdd_temperature(device)
        if hdd_temp is not None:
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

    # Run the scheduler (blocks until the script exits)
    scheduler.run()

if __name__ == "__main__":
    main()
