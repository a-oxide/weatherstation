from flask import Flask, render_template_string, request, jsonify, send_file, url_for
import sqlite3
import io
import datetime
from datetime import timedelta
import pandas as pd
import math
import subprocess

app = Flask(__name__)

# match structure
DB_PATH = "/home/weatherstation/weather_data/weather.db"

# wind direction mapping
VOLT_MAP = {
    0.4: "W", 0.9: "NW", 1.2: "N", 1.4: "SW",
    1.8: "NE", 2.0: "S", 2.2: "SE", 2.8: "E"
}

def get_wind_cardinal(volts):
    if volts is None or volts < 0.1: return "--"
    closest_v = min(VOLT_MAP.keys(), key=lambda k: abs(k-volts))
    if abs(closest_v - volts) > 0.3: return "?" 
    return VOLT_MAP[closest_v]

def calculate_dew_point(T, RH):
    if T is None or RH is None or RH == 0: return None
    b, c = 17.625, 243.04
    gamma = (b * T) / (c + T) + math.log(RH / 100.0)
    return (c * gamma) / (b - gamma)

# "insights" function, provided by GLM 4.6
def generate_objective_insights(curr, prev, range_arg):
    insights = []
    
    # 1. Frost / Cold Stress
    min_temp = curr.get('min_temp', curr['avg_temp'])
    if min_temp < 0:
        insights.append(("❄️", f"Hard freeze detected (Low: {min_temp:.1f}°C)."))
    elif min_temp < 4:
        insights.append(("❄️", f"Frost risk present (Low: {min_temp:.1f}°C)."))

    # 2. Watering Context
    if range_arg == '7d':
        if curr['total_rain'] < 5:
            insights.append(("💧", f"Low rainfall ({curr['total_rain']:.1f}mm). Soil moisture likely depleted."))
        elif curr['total_rain'] > 50:
             insights.append(("🌧️", f"Heavy saturation ({curr['total_rain']:.1f}mm). Soil likely waterlogged."))
    
    # 3. Evaporation Risk
    if curr['avg_hum'] < 40 and curr['avg_wind'] > 10:
        insights.append(("🍃", "High evaporation rate. Drying winds present."))
    
    # 4. Fungal Risk
    if curr['avg_hum'] > 85 and curr['avg_temp'] > 18:
        insights.append(("🍄", "High humidity & warmth detected. Risk of fungal growth."))

    # 5. Pressure Tendency
    curr_pres = curr.get('avg_pres', 0)
    prev_pres = prev.get('avg_pres', curr_pres) # Default to current if prev missing
    
    pres_diff = curr_pres - prev_pres
    if abs(pres_diff) > 4: 
        direction = "rising" if pres_diff > 0 else "falling"
        insights.append(("🧭", f"Barometer pressure {direction} rapidly ({abs(pres_diff):.1f} hPa)."))

    if not insights:
        insights.append(("✅", "Conditions are stable."))
        
    return insights

# flask routes

@app.route('/api/sync-time', methods=['POST'])
def sync_time():
    try:
        data = request.json
        client_ts = data.get('timestamp') / 1000 
        client_dt = datetime.datetime.fromtimestamp(client_ts)
        server_dt = datetime.datetime.now()
        
        diff = abs((client_dt - server_dt).total_seconds())
        
        if diff > 60:
            time_str = client_dt.strftime('%Y-%m-%d %H:%M:%S')
            # Requires sudoers permission
            subprocess.run(["sudo", "date", "-s", time_str], check=True)
            return jsonify({"status": "updated", "diff": diff})
        else:
            return jsonify({"status": "ignored", "diff": diff})
    except Exception as e:
        print(f"Time Sync Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/v2/data')
def api_v2():
    range_arg = request.args.get('range', '7d')
    conn = get_db()
    
    now = datetime.datetime.now()
    if range_arg == '24h':
        start = now - timedelta(days=1)
        prev_start = start - timedelta(days=1)
        grp, fmt = "", "%H:%M"
    elif range_arg == '7d':
        start = now - timedelta(days=7)
        prev_start = start - timedelta(days=7)
        grp, fmt = "GROUP BY strftime('%Y-%m-%d', timestamp)", "%Y-%m-%d"
    else: 
        start = now - timedelta(days=30)
        prev_start = start - timedelta(days=30)
        grp, fmt = "GROUP BY strftime('%Y-%m-%d', timestamp)", "%m-%d"

    # chart data
    query = f"""
        SELECT strftime('{fmt}', timestamp) as label,
               SUM(rain_mm) as rain, AVG(temp_c) as temp, AVG(humidity) as hum, 
               AVG(pressure_hpa) as pres, AVG(wind_speed_kph) as wind, MAX(wind_speed_kph) as gust
        FROM weather_data WHERE timestamp >= ? {grp} ORDER BY timestamp ASC
    """
    if range_arg == '24h': 
         query = f"""
            SELECT strftime('{fmt}', timestamp) as label,
                   rain_mm as rain, temp_c as temp, humidity as hum, 
                   pressure_hpa as pres, wind_speed_kph as wind, wind_speed_kph as gust
            FROM weather_data WHERE timestamp >= ? ORDER BY timestamp ASC
        """
    rows = conn.execute(query, (start,)).fetchall()

    # current stats
    stats_q = """
        SELECT SUM(rain_mm) as total_rain, AVG(temp_c) as avg_temp, MAX(temp_c) as max_temp, MIN(temp_c) as min_temp,
               MAX(wind_speed_kph) as max_wind, AVG(wind_speed_kph) as avg_wind,
               AVG(humidity) as avg_hum, AVG(pressure_hpa) as avg_pres,
               AVG(battery_volts) as batt_volts
        FROM weather_data WHERE timestamp >= ?
    """
    curr = dict(conn.execute(stats_q, (start,)).fetchone())
    for k in curr: curr[k] = curr[k] or 0 
    curr['dew_point'] = calculate_dew_point(curr['avg_temp'], curr['avg_hum'])

    # prev stats
    prev_q = "SELECT AVG(pressure_hpa) as avg_pres FROM weather_data WHERE timestamp >= ? AND timestamp < ?"
    row = conn.execute(prev_q, (prev_start, start)).fetchone()
    prev = dict(row) if row else {}
    if 'avg_pres' not in prev or prev['avg_pres'] is None:
        prev['avg_pres'] = curr.get('avg_pres', 0)

    # wind check
    latest_q = "SELECT wind_dir_voltage FROM weather_data ORDER BY id DESC LIMIT 1"
    last_row = conn.execute(latest_q).fetchone()
    last_volts = last_row['wind_dir_voltage'] if last_row else 0
    dir_str = get_wind_cardinal(last_volts)
    
    wind_ok = (last_volts > 0.1) or (curr['max_wind'] > 0)

    conn.close()

    return jsonify({
        "chart": {
            "labels": [r['label'] for r in rows],
            "rain": [r['rain'] for r in rows],
            "temp": [r['temp'] for r in rows],
            "hum": [r['hum'] for r in rows],
            "pres": [r['pres'] for r in rows],
            "wind": [r['wind'] for r in rows],
            "gust": [r['gust'] for r in rows]
        },
        "stats": curr,
        "latest_dir": dir_str,
        "wind_ok": wind_ok,
        "insights": generate_objective_insights(curr, prev, range_arg)
    })

@app.route('/export')
def export():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM weather_data", conn)
    conn.close()
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    out.seek(0)
    return send_file(out, download_name="weather_data.xlsx", as_attachment=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# html (provided by Gemini 3 Pro Preview)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Station Dashboard</title>
    <script src="{{ url_for('static', filename='chart.js') }}"></script>
    <style>
        :root { 
            --bg: #f4f6f8; --card: #ffffff; --text: #2d3748; --sub: #718096;
            --accent: #4299e1; --rain: #3182ce; --temp: #e53e3e; --wind: #38a169;
        }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 0; }
        
        #sync-banner {
            background: #ed8936; color: white; text-align: center;
            padding: 8px; font-size: 0.85rem; font-weight: 600;
            display: none; transition: background 0.3s;
        }
        .sync-success { background: #48bb78 !important; }
        .sync-reload { background: #4299e1 !important; }
        .sync-err { background: #e53e3e !important; }

        .container { max-width: 900px; margin: 0 auto; padding: 12px; }
        
        .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }
        .logo h1 { margin: 0; font-size: 1.4rem; font-weight: 800; color: #1a202c; }
        .logo span { font-size: 0.75rem; color: var(--sub); text-transform: uppercase; letter-spacing: 1px; }
        
        .status-group { display: flex; gap: 12px; background: white; padding: 8px 12px; border-radius: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
        .status-item { font-size: 0.7rem; font-weight: 700; color: var(--sub); display: flex; align-items: center; gap: 5px; }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: #cbd5e0; }
        .dot.ok { background: #48bb78; box-shadow: 0 0 4px #48bb78; }
        .dot.err { background: #e53e3e; }

        .insights { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
        .insight-pill { background: white; padding: 12px 16px; border-radius: 10px; display: flex; align-items: center; gap: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); border-left: 4px solid var(--accent); }
        .insight-icon { font-size: 1.2rem; min-width: 24px; text-align: center; }
        .insight-text { font-size: 0.9rem; line-height: 1.4; color: #2d3748; }

        .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 20px; }
        @media(max-width: 380px) { .grid { grid-template-columns: 1fr; } }
        @media(min-width: 700px) { .grid { grid-template-columns: repeat(4, 1fr); gap: 15px; } }

        .card { background: var(--card); padding: 16px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.03); display: flex; flex-direction: column; justify-content: space-between; }
        .card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .card-lbl { font-size: 0.7rem; font-weight: 700; color: var(--sub); text-transform: uppercase; }
        .card-val { font-size: 1.6rem; font-weight: 800; color: var(--text); line-height: 1.1; }
        .card-sub { font-size: 0.75rem; color: var(--sub); margin-top: 6px; }
        
        .c-temp .card-val { color: var(--temp); }
        .c-rain .card-val { color: var(--rain); }
        .c-wind .card-val { color: var(--wind); }

        .chart-wrapper { background: white; border-radius: 16px; padding: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
        .chart-controls { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
        .tabs { display: flex; background: #edf2f7; padding: 3px; border-radius: 8px; }
        .tab { padding: 8px 14px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; color: var(--sub); transition: 0.2s; -webkit-tap-highlight-color: transparent; }
        .tab.active { background: white; color: var(--text); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        select { padding: 8px; border-radius: 8px; border: 1px solid #e2e8f0; background: white; font-size: 0.9rem; }
        .chart-box { height: 300px; position: relative; }
        .footer { text-align: center; margin-top: 30px; margin-bottom: 20px; font-size: 0.8rem; color: #a0aec0; }
        .btn-dl { color: var(--accent); text-decoration: none; font-weight: 600; }
    </style>
</head>
<body>

<div id="sync-banner">Verifying System Clock...</div>

<div class="container">
    <div class="header">
        <div class="logo">
            <h1>LocalWeather</h1>
            <span>Garden Station</span>
        </div>
        <div class="status-group">
            <div class="status-item"><div class="dot" id="st_sys"></div> SYS</div>
            <div class="status-item"><div class="dot" id="st_env"></div> ENV</div>
            <div class="status-item"><div class="dot" id="st_wnd"></div> WND</div>
        </div>
    </div>

    <div class="insights" id="insight_container"></div>

    <div class="grid">
        <div class="card c-temp">
            <div class="card-head"><span class="card-lbl">Temp</span> 🌡️</div>
            <div class="card-val" id="v_temp">--</div>
            <div class="card-sub">Dew Point: <span id="v_dew">--</span></div>
        </div>
        <div class="card c-rain">
            <div class="card-head"><span class="card-lbl">Rain</span> ☔</div>
            <div class="card-val" id="v_rain">--</div>
            <div class="card-sub">Last 24h</div>
        </div>
        <div class="card c-wind">
            <div class="card-head"><span class="card-lbl">Wind</span> 💨</div>
            <div class="card-val" id="v_wind">--</div>
            <div class="card-sub"><span id="v_dir">--</span> • Gust <span id="v_gust">--</span></div>
        </div>
        <div class="card c-pres">
            <div class="card-head"><span class="card-lbl">Barometer</span> 🧭</div>
            <div class="card-val" id="v_pres">--</div>
            <div class="card-sub">Hum: <span id="v_hum">--</span></div>
        </div>
    </div>

    <div class="chart-wrapper">
        <div class="chart-controls">
            <div class="tabs">
                <div class="tab active" onclick="setChartMode('climate')">Climate</div>
                <div class="tab" onclick="setChartMode('wind')">Wind</div>
                <div class="tab" onclick="setChartMode('atmos')">Atmos</div>
            </div>
            <select id="timeRange" onchange="fetchData()">
                <option value="24h">24 Hours</option>
                <option value="7d" selected>7 Days</option>
                <option value="30d">30 Days</option>
            </select>
        </div>
        <div class="chart-box">
            <canvas id="mainChart"></canvas>
        </div>
    </div>

    <div class="footer">
        <a href="/export" class="btn-dl">Download CSV/Excel</a>
    </div>
</div>

<script>
    let myChart;
    let currentMode = 'climate';
    let globalData = null;

    async function syncTime() {
        const banner = document.getElementById('sync-banner');
        banner.style.display = 'block';

        try {
            const now = new Date().getTime();
            const res = await fetch('/api/sync-time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timestamp: now })
            });
            
            const data = await res.json();
            
            if (data.status === 'updated') {
                banner.innerText = "Clock Updated! Reloading...";
                banner.className = 'sync-reload';
                setTimeout(() => location.reload(), 1500);
            } else {
                banner.innerText = "Clock Synced";
                banner.className = 'sync-success';
                setTimeout(() => { banner.style.display = 'none'; }, 2000);
            }
        } catch (e) {
            console.error(e);
            banner.innerText = "Sync Failed (Check Connection)";
            banner.className = 'sync-err';
        }
    }

    function initChart() {
        const ctx = document.getElementById('mainChart').getContext('2d');
        myChart = new Chart(ctx, {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 6, maxRotation: 0 } },
                    y: { position: 'left', beginAtZero: false },
                    y1: { position: 'right', grid: { drawOnChartArea: false } }
                }
            }
        });
    }

    function setChartMode(mode) {
        currentMode = mode;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        event.target.classList.add('active');
        renderChart();
    }

    function renderChart() {
        if (!globalData) return;
        const d = globalData.chart;
        myChart.data.labels = d.labels;
        myChart.data.datasets = [];
        myChart.options.scales.y1.display = true;

        if (currentMode === 'climate') {
            myChart.data.datasets = [
                { label: 'Temp (°C)', data: d.temp, borderColor: '#e53e3e', backgroundColor: 'transparent', yAxisID: 'y', tension: 0.4, borderWidth: 2, pointRadius: 0 },
                { label: 'Humidity (%)', data: d.hum, borderColor: '#4299e1', backgroundColor: 'rgba(66, 153, 225, 0.1)', fill: true, yAxisID: 'y1', tension: 0.4, pointRadius: 0 }
            ];
        } else if (currentMode === 'wind') {
            myChart.data.datasets = [
                { label: 'Avg (kph)', data: d.wind, borderColor: '#38a169', backgroundColor: 'transparent', yAxisID: 'y', tension: 0.2, pointRadius: 0 },
                { label: 'Gust (kph)', data: d.gust, borderColor: '#2f855a', borderDash: [4,4], pointRadius: 0, yAxisID: 'y' }
            ];
            myChart.options.scales.y1.display = false;
        } else if (currentMode === 'atmos') {
            myChart.data.datasets = [
                { label: 'Pres (hPa)', data: d.pres, borderColor: '#805ad5', yAxisID: 'y', tension: 0.4, pointRadius: 0 },
                { label: 'Rain (mm)', data: d.rain, backgroundColor: '#3182ce', type: 'bar', yAxisID: 'y1' }
            ];
        }
        myChart.update();
    }

    async function fetchData() {
        const range = document.getElementById('timeRange').value;
        try {
            const res = await fetch(`/api/v2/data?range=${range}`);
            globalData = await res.json();
            updateUI(globalData);
            renderChart();
        } catch(e) { console.error("Fetch failed", e); }
    }

    function updateUI(data) {
        const s = data.stats;
        document.getElementById('v_temp').innerText = s.avg_temp.toFixed(1) + '°';
        document.getElementById('v_dew').innerText = s.dew_point ? s.dew_point.toFixed(1) + '°' : '--';
        document.getElementById('v_rain').innerText = s.total_rain.toFixed(1) + 'mm';
        document.getElementById('v_wind').innerText = s.avg_wind.toFixed(1);
        document.getElementById('v_gust').innerText = s.max_wind.toFixed(1);
        document.getElementById('v_dir').innerText = data.latest_dir;
        document.getElementById('v_pres').innerText = s.avg_pres.toFixed(0);
        document.getElementById('v_hum').innerText = s.avg_hum.toFixed(0) + '%';
        updateStatus('st_sys', true);
        updateStatus('st_env', s.avg_pres > 800); 
        updateStatus('st_wnd', data.wind_ok);
        const container = document.getElementById('insight_container');
        container.innerHTML = '';
        data.insights.forEach(item => {
            const [icon, text] = item;
            container.innerHTML += `<div class="insight-pill"><div class="insight-icon">${icon}</div><div class="insight-text">${text}</div></div>`;
        });
    }

    function updateStatus(id, isOk) {
        document.getElementById(id).className = isOk ? 'dot ok' : 'dot err';
    }

    syncTime();
    initChart();
    fetchData();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
