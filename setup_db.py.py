import sqlite3
import os

# match structure in README
DB_FOLDER = "/home/weatherstation/weather_data"
DB_PATH = f"{DB_FOLDER}/weather.db"

def init_db():
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Enable Write-Ahead Logging (WAL) for power-loss protection
    c.execute('PRAGMA journal_mode=WAL;')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS weather_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temp_c REAL,
            humidity REAL,
            pressure_hpa REAL,
            wind_speed_kph REAL,
            rain_mm REAL,
            wind_dir_voltage REAL,
            battery_volts REAL,
            battery_current_ma REAL
        )
    ''')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON weather_data (timestamp)')
    
    conn.commit()
    conn.close()
    print(f"Database initialized successfully at: {DB_PATH}")

if __name__ == "__main__":
    init_db()
