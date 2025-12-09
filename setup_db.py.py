import sqlite3
import os
DB_PATH = "/home/weatherstation/weather_data/weather.db"
def init_db():
    if not os.path.exists(os.path.dirname(DB_PATH)): os.makedirs(os.path.dirname(DB_PATH))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('PRAGMA journal_mode=WAL;')
    c.execute('''CREATE TABLE IF NOT EXISTS weather_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        temp_c REAL, humidity REAL, pressure_hpa REAL, wind_speed_kph REAL,
        rain_mm REAL, wind_dir_voltage REAL)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON weather_data (timestamp)')
    conn.commit()
    conn.close()
    print("DB Initialized.")
if __name__ == "__main__": init_db()
