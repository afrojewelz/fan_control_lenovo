# fan_control_lenovo
Lenovo Fan Control for ipmitool on SR655 v1

Should not work on other servers ,lenovo oem epyc 7002/7003 <120W only

[![Powered by DartNode](https://dartnode.com/branding/DN-Open-Source-sm.png)](https://dartnode.com "Powered by DartNode - Free VPS for Open Source")

## service setup
root@neopic:/etc/systemd/system# cat cpu_temp_monitor.service 
[Unit]
Description=CPU Temperature Monitor Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cpu_temp_monitor.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
