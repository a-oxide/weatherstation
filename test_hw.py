import time
import board
import busio
from gpiozero import Button
from adafruit_bme280 import basic as adafruit_bme280
from adafruit_ads1x15.ads1015 import ADS1015
from adafruit_ads1x15.analog_in import AnalogIn

# config
PIN_WIND = 5
PIN_RAIN = 6
ADDR_BME = 0x77
ADDR_ADC = 0x48

print("Initializing I2C Bus...")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
except Exception as e:
    print(f"CRITICAL ERROR: I2C Bus failed. {e}")
    exit(1)

try:
    bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=ADDR_BME)
    print(f"BME280 detected at {hex(ADDR_BME)}")
except Exception as e:
    print(f"BME280 NOT FOUND at {hex(ADDR_BME)}: {e}")
    bme280 = None

try:
    ads = ADS1015(i2c, address=ADDR_ADC)
    wind_chan = AnalogIn(ads, 0) # Channel 0
    print(f"ADS1015 detected at {hex(ADDR_ADC)}")
except Exception as e:
    print(f"ADS1015 NOT FOUND at {hex(ADDR_ADC)}: {e}")
    wind_chan = None

print("Initializing GPIO ")
try:
    # bounce_time prevents 1 click from registering as 10
    wind_sensor = Button(PIN_WIND, pull_up=True, bounce_time=0.01)
    rain_sensor = Button(PIN_RAIN, pull_up=True, bounce_time=0.1)
    print(f"GPIO {PIN_WIND} (Wind) & {PIN_RAIN} (Rain) ready.")
except Exception as e:
    print(f"GPIO Error: {e}")
    wind_sensor = None
    rain_sensor = None

def wind_callback():
    print(" >>> WIND TICK DETECTED")

def rain_callback():
    print(" >>> RAIN BUCKET TIPPED")

if wind_sensor: wind_sensor.when_pressed = wind_callback
if rain_sensor: rain_sensor.when_pressed = rain_callback

# --- VOLTAGE MAPPER (For visual testing) ---
def get_cardinal(volts):
    if volts < 0.1: return "Err"
    map = {0.4:"W", 0.9:"NW", 1.2:"N", 1.4:"SW", 1.8:"NE", 2.0:"S", 2.2:"SE", 2.8:"E"}
    closest = min(map.keys(), key=lambda k: abs(k-volts))
    return map[closest] if abs(closest - volts) < 0.3 else "?"

print("\n" + "="*60)
print("TESTING LIVE SENSORS")
print("1. Spin the Anemometer -> You should see 'WIND TICK'")
print("2. Tip the Rain Bucket -> You should see 'RAIN TIPPED'")
print("3. Watch Temp/Wind Dir update below")
print("="*60 + "\n")

print(f"{'Temp (C)':<10} {'Pres (hPa)':<12} {'Wind Volts':<12} {'Dir':<5}")
print("-" * 45)

while True:
    try:
        # Read BME
        t = bme280.temperature if bme280 else 0
        p = bme280.pressure if bme280 else 0
        
        # Read ADC
        v = wind_chan.voltage if wind_chan else 0
        d = get_cardinal(v)
        
        print(f"{t:<10.1f} {p:<12.1f} {v:<12.2f} {d:<5}")
        
        time.sleep(1)
        
    except KeyboardInterrupt:
        print("\nTest Stopped.")
        break
    except Exception as e:
        print(f"Loop Error: {e}")
        time.sleep(1)
