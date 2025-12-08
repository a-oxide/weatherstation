## ECEGR 4640 01 25FQ Iot

A class project to create a Weather Station for Yes Farm operated by the Black Farmers Collective. 

Uses a Raspberry Pi, Sparkfun weather station modules, and an associated HAT.
_Note on picking a RPi: anything with a Broadcom modem or with the modern (RPi5) GPIO scheme will not work properly_

## Installation & Setup Guide
---
**OS:** Raspberry Pi OS Lite (64-bit or 32-bit).
**User:** `weatherstation`

1.  **Flash & Update:**
    ```bash
    sudo apt update && sudo apt upgrade -y
    ```

2.  **Enable I2C (For Sensors):**
    *   Run `sudo raspi-config` -> **Interface Options** -> **I2C** -> **Yes**.

3.  **Install System Dependencies:**
    ```bash
    sudo apt install git python3-venv python3-pip libopenblas-dev libatlas-base-dev i2c-tools hostapd dnsmasq dhcpcd-base -y
    ```

4.  **Allow Web Server to Set Time:**
    ```bash
    sudo visudo
    ```
    Add at the bottom:
    `weatherstation ALL=(ALL) NOPASSWD: /usr/bin/date`

---

1.  **Create Folders:**
    ```bash
    mkdir -p ~/weather_project/static
    mkdir -p ~/weather_data
    ```

2.  **Setup Virtual Environment:**
    ```bash
    cd ~/weather_project
    python3 -m venv venv
    source venv/bin/activate
    pip install flask pandas adafruit-circuitpython-bme280 adafruit-circuitpython-ads1x15 adafruit-circuitpython-ina219 openpyxl
    ```

3.  **Download Offline Assets:**
    ```bash
    cd ~/weather_project/static
    wget -O chart.js https://cdn.jsdelivr.net/npm/chart.js
    ```

4.  **Deploy Files:**
    Place your Python scripts in `~/weather_project/`:
    *   `setup_db.py`: Initializes DB in `../weather_data/`.
    *   `logger.py`: Reads sensors, writes to DB.
    *   `app.py`: Flask web server.

5.  **Initialize Database:**
    ```bash
    source ~/weather_project/venv/bin/activate
    python ~/weather_project/setup_db.py
    ```
---
Create two service files in `/etc/systemd/system/`.

**1. `weather-logger.service`**
```ini
[Unit]
Description=Weather Logger
After=network.target
[Service]
ExecStart=/home/weatherstation/weather_project/venv/bin/python /home/weatherstation/weather_project/logger.py
WorkingDirectory=/home/weatherstation/weather_project
User=weatherstation
Restart=always
[Install]
WantedBy=multi-user.target
```

**2. `weather-web.service`**
```ini
[Unit]
Description=Weather WebUI
After=network.target
[Service]
ExecStart=/home/weatherstation/weather_project/venv/bin/python /home/weatherstation/weather_project/app.py
WorkingDirectory=/home/weatherstation/weather_project
User=weatherstation
Restart=always
[Install]
WantedBy=multi-user.target
```

**Enable them:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable weather-logger.service
sudo systemctl enable weather-web.service
```

---

1.  **Kill System DNS (Frees Port 53 for dnsmasq):**
    ```bash
    sudo systemctl stop systemd-resolved
    sudo systemctl disable systemd-resolved
    sudo rm /etc/resolv.conf
    echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
    ```

2.  **Ignore WiFi in NetworkManager (Prevents boot conflicts):**
    Edit `/etc/NetworkManager/NetworkManager.conf`:
    ```ini
    [keyfile]
    unmanaged-devices=interface-name:wlan0
    ```

3.  **Set Static IP:**
    Edit `/etc/dhcpcd.conf` (Add to bottom):
    ```text
    interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
    ```

4.  **Configure DHCP/Captive Portal:**
    Edit `/etc/dnsmasq.conf`:
    ```text
    interface=wlan0
    dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
    address=/#/192.168.4.1
    no-resolv
    ```

5.  **Configure Hotspot:**
    Edit `/etc/hostapd/hostapd.conf`:
    ```text
    interface=wlan0
    driver=nl80211
    ssid=WeatherStation
    hw_mode=g
    channel=7
    auth_algs=1
    ignore_broadcast_ssid=0
    ```
    Point to it in `/etc/default/hostapd`:
    `DAEMON_CONF="/etc/hostapd/hostapd.conf"`

---
Run these commands to activate the hotspot and reboot.

```bash
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq
sudo reboot
```

*   **Connect:** WiFi "WeatherStation".
*   **View:** Captive portal or `http://192.168.4.1`.
*   **Manage:** `ssh weatherstation@192.168.4.1`.
