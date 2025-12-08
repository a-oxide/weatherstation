import time
import sqlite3
import board
import busio
from gpiozero import Button

from adafruit_bme280 import basic as adafruit_bme280
from adafruit_ads1x15.ads1015 import ADS1015
from adafruit_ads1x15.analog_in import AnalogIn

#preset filestructure
DB_PATH = "/home/weatherstation/weather_data/weather.db"
LOG_INTERVAL = 60  # seconds

# GPIO Pins (BC Robotics Hat)
PIN_WIND_SPEED = 17
PIN_RAIN = 23

# I2C Addresses
ADDR_BME = 0x77
ADDR_ADC = 0x48
ADDR_INA = 0x40

i2c = busio.I2C(board.SCL, board.SDA)

# BME280
try:
    bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=ADDR_BME)
except Exception as e:
    print(f"BME280 Error: {e}")
    bme280 = None

# ADS1015
try:
    ads = ADS1015(i2c, address=ADDR_ADC)
    wind_dir_channel = AnalogIn(ads, 0) # Channel 0
except Exception as e:
    print(f"ADS1015 Error: {e}")
    wind_dir_channel = None

# rain and wind speed (Interrupts)
wind_sensor = Button(PIN_WIND_SPEED, pull_up=True, bounce_time=0.01) 
rain_sensor = Button(PIN_RAIN, pull_up=True, bounce_time=0.1)

# Counters
wind_count = 0
rain_count = 0

def wind_tick():
    global wind_count
    wind_count += 1

def rain_tick():
    global rain_count
    rain_count += 1

wind_sensor.when_pressed = wind_tick
rain_sensor.when_pressed = rain_tick

# helper funcs
def get_wind_speed_kph(count, interval):
    # 1 tick/sec = 2.4 kph
    if interval == 0: return 0
    speed = (count / interval) * 2.4
    return round(speed, 2)

def log_to_db(data):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO weather_data 
            (temp_c, humidity, pressure_hpa, wind_speed_kph, rain_mm, wind_dir_voltage, battery_volts, battery_current_ma)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', data)
        conn.commit()
        conn.close()
        print(f"Logged: {data}")
    except Exception as e:
        print(f"DB Write Error: {e}")

# main loop
print("Logger Started...") #debug

while True:
    try:
        # reset counters
        wind_count = 0
        rain_count = 0 
        
        # check for ctrlc
        for _ in range(LOG_INTERVAL):
            time.sleep(1)
        
        # read data
        if bme280:
            temp = round(bme280.temperature, 2)
            hum = round(bme280.relative_humidity, 1)
            pres = round(bme280.pressure, 1)
        else:
            temp = hum = pres = 0

        # read wind direction
        wind_volts = round(wind_dir_channel.voltage, 3) if wind_dir_channel else 0
        
        # calc windspeed
        speed = get_wind_speed_kph(wind_count, LOG_INTERVAL)
        
        # calc rain (0.2794mm per tick)
        rain_mm = round(rain_count * 0.2794, 2)

	# messy workaround to my old db structure
        #batt_v = 0
        #batt_ma = 0
        
        # Log
        log_to_db((temp, hum, pres, speed, rain_mm, wind_volts))
        # log_to_db((temp, hum, pres, speed, rain_mm, wind_volts, batt_v, batt_ma))
        
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"Loop Error: {e}")
        time.sleep(5)
