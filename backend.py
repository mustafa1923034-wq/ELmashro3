from flask import Flask, request, jsonify
import serial
import threading
import time
import json
from config import *

app = Flask(__name__)

traffic_state = {
    "density": [0, 0, 0, 0],
    "density_after": [0, 0, 0, 0],
    "halting": [0, 0, 0, 0],
    "beacon": False,
    "priority_lane": None,
    "beacon_start_time": time.time(),
    "current_phase_idx": [0, 0, 0, 0],
    "current_times": [[30, 5, 15, 5] for _ in range(4)],
    "next_green": [30, 30, 30, 30],
    "current_green": [30, 30, 30, 30],
    "prev_green": [30, 30, 30, 30],
    "latency_ms": 0,
    "last_update": time.time(),
    "cycle_total": CYCLE_TOTAL,
    "yellow_time": YELLOW_TIME,
    "green_min": GREEN_MIN,
    "green_max": GREEN_MAX,
    "cycle_progress": [0, 0, 0, 0],
    "sensor_status": [True, True, True, True, True, True, True, True],
}

lock = threading.Lock()
last_esp_data_time = time.time()
last_arduino_data_time = time.time()
esp_start_time = time.time()
arduino_start_time = time.time()

def init_serial(port, name):
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=1)
        print(f"✅ {name} Serial connected: {port} @ {BAUD_RATE} baud")
        return ser
    except Exception as e:
        print(f"⚠️ {name} Serial error: {e}")
        return None

# ✅ فتح الـ ports
esp_ser = init_serial(ESP_SERIAL_PORT, "ESP")
arduino_ser = init_serial(ARDUINO_SERIAL_PORT, "Arduino")

def serial_reader(port, name):
    global traffic_state, last_esp_data_time, last_arduino_data_time, esp_start_time, arduino_start_time
    buffer = ""
    
    print(f"📡 Starting {name} serial reader thread")
    
    while True:
        if name == "ESP":
            ser = esp_ser
        else:
            ser = arduino_ser
            
        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    new_data = ser.read(ser.in_waiting)
                    if new_data:
                        buffer += new_data.decode('utf-8', errors='ignore')

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if not line:
                        continue

                    print(f"📥 [{name}] Received: {line}")
                    
                    with lock:
                        traffic_state["last_update"] = time.time()
                        
                        if name == "ESP":
                            last_esp_data_time = time.time()
                        else:
                            last_arduino_data_time = time.time()

                        if line.startswith("DENSITIES:"):
                            values = line.replace("DENSITIES:", "").split(",")
                            if len(values) >= 8:
                                traffic_state["density"] = [
                                    int(values[0]), int(values[2]), 
                                    int(values[4]), int(values[6])
                                ]
                                traffic_state["density_after"] = [
                                    int(values[1]), int(values[3]), 
                                    int(values[5]), int(values[7])
                                ]

                        elif line.startswith("CYCLE_OBS:"):
                            parts = line.split(':', 2)
                            if len(parts) == 3:
                                try:
                                    timestamp = int(parts[1])
                                    data_str = parts[2]
                                    values = data_str.split(",")
                                    if len(values) >= 12:
                                        traffic_state["density"] = [
                                            int(values[0]), int(values[3]), int(values[6]), int(values[9])
                                        ]
                                        traffic_state["density_after"] = [
                                            int(values[1]), int(values[4]), int(values[7]), int(values[10])
                                        ]
                                        traffic_state["halting"] = [0, 0, 0, 0]
                                except:
                                    pass

                        elif line.startswith("PRIORITY:"):
                            priority_lane = int(line[9:])
                            traffic_state["beacon"] = True
                            traffic_state["priority_lane"] = priority_lane
                            traffic_state["beacon_start_time"] = time.time()

                        elif line.startswith("APPLIED_CYCLE:"):
                            values = list(map(int, line[15:].split(",")))
                            if len(values) == 16:
                                traffic_state["current_times"] = [
                                    values[0:4], values[4:8], values[8:12], values[12:16]
                                ]

                        elif line.startswith("PROGRESS:"):
                            parts = line[9:].split(":")
                            if len(parts) == 2:
                                try:
                                    lane = int(parts[0])
                                    progress = int(parts[1])
                                    if 0 <= lane < 4:
                                        if "cycle_progress" not in traffic_state:
                                            traffic_state["cycle_progress"] = [0, 0, 0, 0]
                                        traffic_state["cycle_progress"][lane] = progress
                                except:
                                    pass

                        elif line.startswith("LATENCY:"):
                            try:
                                traffic_state["latency_ms"] = int(line[8:])
                            except:
                                pass

                        elif line.startswith("SENSOR_STATUS:"):
                            try:
                                statuses = list(map(int, line[15:].split(",")))
                                if len(statuses) == 8:
                                    traffic_state["sensor_status"] = [bool(s) for s in statuses]
                            except:
                                pass

                        elif line.startswith("PHASE:"):
                            try:
                                parts = line[6:].split(":")
                                if len(parts) == 2:
                                    lane = int(parts[0])
                                    phase = int(parts[1])
                                    if 0 <= lane < 4:
                                        traffic_state["current_phase_idx"][lane] = phase
                            except:
                                pass

                        elif line == "PING":
                            pass

                        elif line == "BEACON_CLEAR":
                            traffic_state["beacon"] = False
                            traffic_state["priority_lane"] = None

                        elif line == "BEACON_EXTENDED":
                            pass

            except Exception as e:
                print(f"❌ {name} Serial read error: {e}")
                buffer = ""
                if name == "ESP":
                    new_ser = init_serial(ESP_SERIAL_PORT, "ESP")
                    if new_ser:
                        globals()['esp_ser'] = new_ser
                else:
                    new_ser = init_serial(ARDUINO_SERIAL_PORT, "Arduino")
                    if new_ser:
                        globals()['arduino_ser'] = new_ser
        else:
            if name == "ESP":
                if time.time() - esp_start_time > 30:
                    new_ser = init_serial(ESP_SERIAL_PORT, "ESP")
                    if new_ser:
                        globals()['esp_ser'] = new_ser
                        esp_start_time = time.time()
            else:
                if time.time() - arduino_start_time > 30:
                    new_ser = init_serial(ARDUINO_SERIAL_PORT, "Arduino")
                    if new_ser:
                        globals()['arduino_ser'] = new_ser
                        arduino_start_time = time.time()
            time.sleep(1)

# ✅ إنشاء Threads
if esp_ser:
    threading.Thread(target=lambda: serial_reader(ESP_SERIAL_PORT, "ESP"), daemon=True).start()

if arduino_ser:
    threading.Thread(target=lambda: serial_reader(ARDUINO_SERIAL_PORT, "Arduino"), daemon=True).start()

@app.route("/get", methods=["GET"])
def get_state():
    with lock:
        return jsonify(traffic_state)

@app.route("/set_lane", methods=["POST"])
def set_lane():
    data = request.json
    if not data or "lane" not in data:
        return jsonify({"status": "error", "message": "Missing lane parameter"}), 400
    
    lane = data["lane"]
    
    if lane < 0 or lane >= len(JUNCTION_MAPPING):
        return jsonify({"status": "error", "message": f"Invalid lane: {lane}"}), 400
    
    with lock:
        traffic_state["beacon"] = True
        traffic_state["priority_lane"] = lane
        traffic_state["beacon_start_time"] = time.time()
        
        if esp_ser and esp_ser.is_open:
            try:
                esp_ser.write(f"PRIORITY:{lane}\n".encode())
                print(f"🚨 Beacon activated for lane {lane} ({JUNCTION_MAPPING[lane]['name']})")
            except Exception as e:
                print(f"❌ Failed to send beacon to ESP: {e}")
    
    return jsonify({
        "status": "ok", 
        "lane": lane,
        "junction": JUNCTION_MAPPING[lane]["name"]
    })

@app.route("/set_next_cycle", methods=["POST"])
def set_next_cycle():
    data = request.json
    if not data or "next_green" not in data:
        return jsonify({"status": "error", "message": "Missing next_green parameter"}), 400
    
    next_green = data.get("next_green")
    latency = data.get("latency_ms", 0)
    
    if not isinstance(next_green, list) or len(next_green) != 4:
        return jsonify({"status": "error", "message": "Invalid next_green format"}), 400
    
    validated_green = []
    for i, g in enumerate(next_green):
        try:
            g = int(g)
            if g < GREEN_MIN:
                g = GREEN_MIN
            elif g > GREEN_MAX:
                g = GREEN_MAX
            validated_green.append(g)
        except:
            validated_green.append(30)
    
    with lock:
        traffic_state["prev_green"] = traffic_state["current_green"][:]
        traffic_state["current_green"] = validated_green[:]
        traffic_state["latency_ms"] = latency
        
        if esp_ser and esp_ser.is_open:
            try:
                command = f"NEXT_GREEN:{','.join(map(str, validated_green))}\n"
                esp_ser.write(command.encode())
                print(f"🔄 Sent green times: {validated_green} (latency: {latency}ms)")
            except Exception as e:
                print(f"❌ Failed to send to ESP: {e}")
    
    return jsonify({
        "status": "ok", 
        "validated_green": validated_green,
        "cycle_total": CYCLE_TOTAL
    })

@app.route("/clear_beacon", methods=["POST"])
def clear_beacon():
    with lock:
        traffic_state["beacon"] = False
        traffic_state["priority_lane"] = None
        print("✅ Beacon cleared")
    return jsonify({"status": "ok"})

@app.route("/extend_beacon", methods=["POST"])
def extend_beacon():
    with lock:
        if traffic_state.get("beacon") and traffic_state.get("priority_lane") is not None:
            traffic_state["beacon_start_time"] = time.time() - 30
            if esp_ser and esp_ser.is_open:
                try:
                    esp_ser.write(b"EXTEND_BEACON\n")
                    print("⏱️ Beacon extended for 30s")
                except Exception as e:
                    print(f"❌ Failed to extend beacon: {e}")
            return jsonify({"status": "ok", "message": "Beacon extended"})
        return jsonify({"status": "error", "message": "No active beacon"}), 400

@app.route("/status", methods=["GET"])
def get_status():
    current_time = time.time()
    esp_connected = esp_ser and esp_ser.is_open and (current_time - last_esp_data_time) < 5.0
    arduino_connected = arduino_ser and arduino_ser.is_open and (current_time - last_arduino_data_time) < 5.0
    
    with lock:
        return jsonify({
            "backend": True,
            "esp_connected": esp_connected,
            "arduino_connected": arduino_connected,
            "serial_ports": {
                "esp": ESP_SERIAL_PORT,
                "arduino": ARDUINO_SERIAL_PORT
            },
            "last_update": traffic_state["last_update"],
            "time_since_esp_update": current_time - last_esp_data_time,
            "time_since_arduino_update": current_time - last_arduino_data_time,
            "system_config": {
                "cycle_total": CYCLE_TOTAL,
                "yellow_time": YELLOW_TIME,
                "green_min": GREEN_MIN,
                "green_max": GREEN_MAX
            },
            "current_state": traffic_state
        })

@app.route("/config", methods=["GET"])
def get_config():
    return jsonify({
        "junctions": JUNCTION_MAPPING,
        "system_pairs": SYSTEM_PAIRS,
        "cycle_config": {
            "total": CYCLE_TOTAL,
            "yellow": YELLOW_TIME,
            "green_min": GREEN_MIN,
            "green_max": GREEN_MAX,
            "min_red": MIN_RED_TIME
        },
        "normalization": {
            "max_density": MAX_DENSITY,
            "max_halting": MAX_HALTING
        }
    })

if __name__ == "__main__":
    print("🚦 Traffic Control Backend Server")
    print("=" * 50)
    print(f"Host: {BACKEND_HOST}:{BACKEND_PORT}")
    print(f"ESP Serial: {ESP_SERIAL_PORT} @ {BAUD_RATE}")
    print(f"Arduino Serial: {ARDUINO_SERIAL_PORT} @ {BAUD_RATE}")
    print(f"Cycle: {CYCLE_TOTAL}s | Yellow: {YELLOW_TIME}s")
    print(f"Green range: {GREEN_MIN}-{GREEN_MAX}s")
    print("=" * 50)
    
    app.run(host=BACKEND_HOST, port=BACKEND_PORT, debug=False, threaded=True)