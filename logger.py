import time, sqlite3, board, busio
from gpiozero import Button
from adafruit_bme280 import basic as adafruit_bme280
from adafruit_ads1x15.ads1015 import ADS1015
from adafruit_ads1x15.analog_in import AnalogIn

DB_PATH = "/home/weatherstation/weather_data/weather.db"
LOG_INTERVAL = 60
PIN_WIND = 17  # Pi 3B+ HAT Specific
PIN_RAIN = 23  # Pi 3B+ HAT Specific

i2c = busio.I2C(board.SCL, board.SDA)
try: bme = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x77)
except: bme = None
try: 
    ads = ADS1015(i2c, address=0x48)
    wind_chan = AnalogIn(ads, 0)
except: wind_chan = None

wind_btn = Button(PIN_WIND, pull_up=True, bounce_time=0.01)
rain_btn = Button(PIN_RAIN, pull_up=True, bounce_time=0.1)
wind_count = 0
rain_count = 0

def w_tick(): global wind_count; wind_count += 1
def r_tick(): global rain_count; rain_count += 1
wind_btn.when_pressed = w_tick
rain_btn.when_pressed = r_tick

print("Logger Running...")
while True:
    try:
        wind_count = 0; rain_count = 0
        for _ in range(LOG_INTERVAL): time.sleep(1)
        
        t = round(bme.temperature, 2) if bme else 0
        h = round(bme.relative_humidity, 1) if bme else 0
        p = round(bme.pressure, 1) if bme else 0
        v = round(wind_chan.voltage, 3) if wind_chan else 0
        s = round((wind_count / LOG_INTERVAL) * 2.4, 2)
        r = round(rain_count * 0.2794, 2)

        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO weather_data (temp_c, humidity, pressure_hpa, wind_speed_kph, rain_mm, wind_dir_voltage) VALUES (?,?,?,?,?,?)", (t,h,p,s,r,v))
        conn.commit(); conn.close()
    except Exception as e: print(e)
