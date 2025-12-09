# ECEGR 4640 01 25FQ IoT - Weather Station

A class project to create a standalone, offline Weather Station for **Yes Farm**, operated by the Black Farmers Collective.

This system runs on a Raspberry Pi 3B+ using a custom Python backend to log sensor data to SQLite and a Flask-based web dashboard. It functions as a Captive Portal, allowing users to view weather data without an internet connection.

### Hardware Notes
*   **Controller:** Raspberry Pi 3B+
*   **Sensors:** SparkFun Weather Meters (Wind/Rain) + Associated HAT w/ BME280.
*   **Compatibility Warning:** Boards with Broadcom modems or the modern RPi5 GPIO scheme may not work with the current library set.

---

## Installation & Setup Guide

**Target OS:** Raspberry Pi OS Lite (Bookworm) 64-bit. 
**Default User:** `weatherstation`

### Phase 1: System Preparation

1.  **Update System:**
    ```bash
    sudo apt update && sudo apt upgrade -y
    ```

2.  **Enable I2C Interface:**
    *   Run `sudo raspi-config`
    *   Navigate to **Interface Options** -> **I2C** -> **Yes**.

3.  **Install Dependencies:**
    *   *Includes system math libraries for NumPy and network tools for the hotspot.*
    ```bash
    sudo apt install git python3-venv python3-pip libopenblas-dev i2c-tools dnsmasq swig liblgpio-dev -y
    ```

4.  **Allow Web Server to Sync Time:**
    *   Allows the `weatherstation` user to update the system clock via the web dashboard.
    ```bash
    sudo visudo
    ```
    Add this line to the very bottom of the file:
    ```text
    weatherstation ALL=(ALL) NOPASSWD: /usr/bin/date
    ```

5.  **Allow Python to use Port 80**
    ```bash
    sudo setcap 'cap_net_bind_service=+ep' $(readlink -f /usr/bin/python3)
    ```

### Phase 2: Project Environment

1.  **Create Directory Structure:**
    ```bash
    mkdir -p ~/weather_project/static
    mkdir -p ~/weather_data
    ```

2.  **Setup Python Virtual Environment:**
    ```bash
    cd ~/weather_project
    python3 -m venv venv
    source venv/bin/activate
    pip install flask pandas adafruit-circuitpython-bme280 adafruit-circuitpython-ads1x15 adafruit-circuitpython-ina219 openpyxl gpiozero lgpio
    ```

3.  **Download Offline Assets:**
    *   *Since the station will be offline, Chart.js must be stored locally.*
    ```bash
    cd ~/weather_project/static
    wget -O chart.js https://cdn.jsdelivr.net/npm/chart.js
    ```

4.  **Deploy Source Code:**
    Place the project Python scripts into `~/weather_project/`:
    *   `setup_db.py`
    *   `logger.py`
    *   `app.py`

5.  **Initialize Database:**
    ```bash
    source ~/weather_project/venv/bin/activate
    python ~/weather_project/setup_db.py
    ```

### Phase 3: Automation (Systemd Services)

Create the services to run the logger and web server automatically on boot.

**1. Logger Service:** (`sudo nano /etc/systemd/system/weather-logger.service`)
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

**2. Web Interface Service:** (`sudo nano /etc/systemd/system/weather-web.service`)
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

**3. Enable Services:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable weather-logger.service
sudo systemctl enable weather-web.service
```

### Phase 4: Network Configuration

1.  **Stop Conflicts:**
    ```bash
    sudo systemctl stop systemd-resolved
    sudo systemctl disable systemd-resolved
    sudo rm /etc/resolv.conf
    echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
    ```

2.  **Configure Captive Portal**
    *   Edit `/etc/dnsmasq.conf`:
    ```text
    [keyfile]
    unmanaged-devices=interface-name:wlan0
    ```

3.  **Set Static IP:**
    *   Edit `/etc/dhcpcd.conf` (Add to bottom):
    ```text
    interface=wlan0
    dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
    address=/#/192.168.4.1
    # Apple/Android Detection
    address=/captive.apple.com/192.168.4.1
    address=/connectivitycheck.gstatic.com/192.168.4.1
    # Routing
    domain=wlan
    dhcp-option=3,192.168.4.1
    dhcp-option=6,192.168.4.1
    ```

4.  **Create the hotspot:**
    ```bash
    sudo nmcli con add type wifi ifname wlan0 mode ap con-name WeatherStation ssid WeatherStation ipv4.method manual ipv4.addresses 192.168.4.1/24 ipv4.gateway 192.168.4.1 wifi-sec.key-mgmt none connection.autoconnect yes connection.autoconnect-priority 100
    ```
---

## Finalizing

```bash
sudo systemctl enable dnsmasq
sudo reboot
```

### How to Access
1.  **Connect:** Join the WiFi network `WeatherStation`.
2.  **Dashboard:** The captive portal popup should appear. If not, browse to `http://192.168.4.1` or any other URL.
3.  **Maintenance:** SSH into the Pi using:
    `ssh weatherstation@192.168.4.1`
