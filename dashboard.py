import streamlit as st
import requests
import time
from datetime import datetime
from config import *

st.set_page_config(
    page_title="🚦 Traffic Control Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .status-card {
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    .online { 
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border-left: 5px solid #28a745;
    }
    .offline { 
        background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
        border-left: 5px solid #dc3545;
    }
    .traffic-light {
        display: inline-flex;
        flex-direction: column;
        align-items: center;
        gap: 5px;
        margin: 10px 0;
    }
    .light {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        border: 3px solid #333;
        box-shadow: inset 0 0 10px rgba(0,0,0,0.2);
    }
    .green.active { background-color: #28a745; box-shadow: 0 0 20px #28a745; }
    .yellow.active { background-color: #ffc107; box-shadow: 0 0 20px #ffc107; }
    .red.active { background-color: #dc3545; box-shadow: 0 0 20px #dc3545; }
    .light:not(.active) { background-color: #6c757d; opacity: 0.3; }
    .metric-card {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #007bff;
    }
    .metric-label {
        font-size: 14px;
        color: #6c757d;
    }
    .beacon-active {
        animation: pulse 2s infinite;
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        border-left: 5px solid #ffc107;
    }
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
</style>
""", unsafe_allow_html=True)


def check_backend_status():
    try:
        response = requests.get(f"{BACKEND_URL}/status", timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def get_traffic_data():
    try:
        response = requests.get(f"{BACKEND_URL}/get", timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def set_priority_lane(lane):
    try:
        response = requests.post(
            f"{BACKEND_URL}/set_lane",
            json={"lane": lane},
            timeout=2
        )
        if response.status_code == 200:
            return True, response.json()
    except Exception as e:
        return False, str(e)
    return False, "Unknown error"

def clear_beacon():
    try:
        response = requests.post(f"{BACKEND_URL}/clear_beacon", timeout=2)
        if response.status_code == 200:
            return True
    except:
        pass
    return False

def extend_beacon():
    try:
        response = requests.post(f"{BACKEND_URL}/extend_beacon", timeout=2)
        if response.status_code == 200:
            return True, response.json()
    except Exception as e:
        return False, str(e)
    return False, "Unknown error"

def get_phase_name(phase_idx):
    phases = ["🟢 GREEN", "🟡 YELLOW", "🔴 RED", "🟡 YELLOW"]
    return phases[phase_idx] if 0 <= phase_idx < len(phases) else "UNKNOWN"


with st.sidebar:
    st.title("⚙️ System Control")
    
    status = check_backend_status()
    if status:
        st.success("✅ Backend Connected")
        esp_status = "✅ Connected" if status.get("esp_connected") else "❌ Disconnected"
        arduino_status = "✅ Connected" if status.get("arduino_connected") else "❌ Disconnected"
        st.info(f"ESP32: {esp_status}")
        st.info(f"Arduino: {arduino_status}")
        
        if status.get("esp_connected"):
            time_since = status.get("time_since_esp_update", 0)
            st.caption(f"ESP last update: {time_since:.1f}s ago")
        if status.get("arduino_connected"):
            time_since = status.get("time_since_arduino_update", 0)
            st.caption(f"Arduino last update: {time_since:.1f}s ago")
    else:
        st.error("❌ Backend Offline")
    
    st.divider()
    
    st.subheader("🔄 Auto Refresh")
    auto_refresh = st.checkbox("Enable", value=True)
    refresh_rate = st.slider("Rate (seconds)", 1, 10, 2)
    
    st.divider()
    
    st.subheader("🔧 Manual Control")
    if st.button("🔄 Force Refresh", use_container_width=True):
        st.rerun()


st.title("🚦 Traffic Control Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")


col1, col2, col3, col4 = st.columns(4)

status = check_backend_status()
if status:
    data = get_traffic_data()
    esp_connected = status.get("esp_connected", False)
    arduino_connected = status.get("arduino_connected", False)
    latency = status.get("current_state", {}).get("latency_ms", 0)
    cycle_progress = data.get("cycle_progress", [0,0,0,0]) if data else [0,0,0,0]
    cycle_seconds = sum(cycle_progress)//4 if cycle_progress else 0
else:
    data = {}
    esp_connected = False
    arduino_connected = False
    latency = 0
    cycle_seconds = 0


with col1:
    st.metric("Backend", "Online" if status else "Offline")
with col2:
    st.metric("ESP32", "Connected" if esp_connected else "Disconnected")
with col3:
    st.metric("Arduino", "Connected" if arduino_connected else "Disconnected")
with col4:
    st.metric("Latency", f"{latency}ms")


st.subheader("⏱️ Current Time in Cycle")
st.metric("Current Time", f"{cycle_seconds}s / 55s")


# ================= Beacon Active =================
beacon_active = data.get("beacon", False) if data else False
priority_lane = data.get("priority_lane") if data else None

if status and esp_connected and beacon_active and priority_lane is not None:
    st.subheader("🚨 Beacon Active")
    
    # ✅ تصحيح: JUNCTION_MAPPING الآن list وليس dict
    if 0 <= priority_lane < len(JUNCTION_MAPPING):
        junction_name = JUNCTION_MAPPING[priority_lane]["name"]
    else:
        junction_name = f"Lane {priority_lane}"
    
    system_a = [0,1]
    system_b = [2,3]
    system_name = "A" if priority_lane in system_a else "B"
    
    st.markdown(f"""
    <div class='status-card beacon-active'>
        <h3>⚠️ EMERGENCY VEHICLE DETECTED</h3>
        <p>Priority granted to: <strong>{junction_name}</strong> (Lane {priority_lane})</p>
        <p>System {system_name} (Lanes {system_a if system_name=="A" else system_b}) will prioritize Lane {priority_lane}</p>
    </div>
    """, unsafe_allow_html=True)
    
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    with col_btn1:
        if st.button("✅ Cancel Priority", use_container_width=True, type="secondary"):
            if clear_beacon():
                st.success("✅ Priority cancelled")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ Failed to cancel priority")
    with col_btn2:
        if st.button("⏱️ Extend Priority", use_container_width=True):
            success, result = extend_beacon()
            if success:
                st.success("✅ Priority extended for 30 seconds")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"❌ Failed: {result}")
    with col_btn3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()


# ================= Manual Beacon Control =================
if status and esp_connected and (not beacon_active or priority_lane is None):
    st.subheader("🚨 Manual Beacon Control")
    st.info("Select a lane to manually activate emergency priority")
    
    col_select, col_activate = st.columns([3,1])
    with col_select:
        lane_options = [
            f"{i} - {JUNCTION_MAPPING[i]['name']} ({JUNCTION_MAPPING[i]['in_edge']}→{JUNCTION_MAPPING[i]['out_edge']})"
            for i in range(4)
        ]
        selected_option = st.selectbox("Select Priority Lane", lane_options)
        selected_lane = int(selected_option.split(" - ")[0])
    with col_activate:
        st.write("")
        if st.button("🚨 Activate Beacon", use_container_width=True, type="primary"):
            success, result = set_priority_lane(selected_lane)
            if success:
                st.success(f"✅ Beacon activated for {JUNCTION_MAPPING[selected_lane]['name']}")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(f"❌ Failed: {result}")


# ================= Traffic Light Status =================
st.subheader("🚦 Traffic Lights Status")

if not status or not esp_connected or not data:
    st.warning("⚠️ ESP32 not connected or no data. Displaying simulated data.")
    for i in range(4):
        col1, col2, col3, col4 = st.columns(4)
        with [col1, col2, col3, col4][i]:
            st.markdown(f"### {JUNCTION_MAPPING[i]['name']}")
            st.markdown("""
            <div class='traffic-light'>
                <div class='light red active'></div>
                <div class='light yellow'></div>
                <div class='light green'></div>
            </div>
            """, unsafe_allow_html=True)
            st.write("**Status:** 🔴 RED")
            st.write("**Density:** 0 vehicles")
            st.write("**Timing:** 30s green | 15s red")
else:
    cols = st.columns(4)
    for i in range(4):
        with cols[i]:
            junction_name = JUNCTION_MAPPING[i]["name"]
            phase_idx = data.get("current_phase_idx", [0,0,0,0])[i]
            phase_name = get_phase_name(phase_idx)
            
            light_html = f"""
            <div class='traffic-light'>
                <div class='light red {'active' if phase_idx==2 else ''}'></div>
                <div class='light yellow {'active' if phase_idx in [1,3] else ''}'></div>
                <div class='light green {'active' if phase_idx==0 else ''}'></div>
            </div>
            """
            st.markdown(f"### {junction_name}")
            st.markdown(light_html, unsafe_allow_html=True)
            
            density_before = data.get("density", [0,0,0,0])[i]
            density_after = data.get("density_after", [0,0,0,0])[i]
            
            st.write(f"**Phase:** {phase_name}")
            st.write(f"**Density Before:** {density_before} vehicles")
            st.write(f"**Density After:** {density_after} vehicles")
            
            current_times_list = data.get("current_times", [[30,5,15,5] for _ in range(4)])
            if i < len(current_times_list):
                current_times_i = current_times_list[i]
                if len(current_times_i) >= 4:
                    green_time = current_times_i[0]
                    red_time = current_times_i[2]
                    st.write(f"**Green Time:** {green_time}s")
                    st.write(f"**Red Time:** {red_time}s")
            
            current_progress = data.get("cycle_progress", [0,0,0,0])[i]
            st.write(f"**Current Progress:** {current_progress}s / 55s")


# ================= Current Cycle Timings =================
st.subheader("⏱️ Current Cycle Timings (Individual Signals)")
current_times = data.get("current_times", [[30,5,15,5] for _ in range(4)]) if data else [[30,5,15,5] for _ in range(4)]
cols = st.columns(4)
for i in range(4):
    with cols[i]:
        if i < len(current_times):
            times = current_times[i]
            if len(times) >=4:
                green, yellow1, red, yellow2 = times
                total = green + yellow1 + red + yellow2
                st.markdown(f"""
                <div class='metric-card'>
                    <div class='metric-label'>{JUNCTION_MAPPING[i]['name']}</div>
                    <div class='metric-value'>{green}s</div>
                    <div class='metric-label'>Green</div>
                    <div class='metric-value'>{red}s</div>
                    <div class='metric-label'>Red</div>
                    <div class='metric-label'>Total: {total}s</div>
                </div>
                """, unsafe_allow_html=True)
else:
    st.info("Connect ESP32 to see current cycle timings")


# ================= Sensor Status =================
st.subheader("📡 Sensor Status")
sensor_status = data.get("sensor_status", [True]*8) if data else [True]*8
cols = st.columns(8)
for i in range(8):
    with cols[i]:
        color = "🟢" if sensor_status[i] else "🔴"
        st.write(f"**Sensor {i}:** {color}")


# ================= Auto-refresh =================
try:
    from streamlit_autorefresh import st_autorefresh
    if auto_refresh:
        st_autorefresh(interval=refresh_rate*1000, key="dashboard_refresh")
except ImportError:
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()