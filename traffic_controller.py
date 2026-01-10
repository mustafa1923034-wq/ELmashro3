import sys
import os
import time
import requests
import json
import numpy as np
from stable_baselines3 import PPO

# Ensure config.py is in the same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import shared configuration
from config import (
    BACKEND_URL,
    MODEL_PATH,
    CYCLE_TOTAL,
    YELLOW_TIME,
    GREEN_MIN,
    GREEN_MAX,
    MIN_RED_TIME,
    JUNCTION_MAPPING,
    MAX_DENSITY,
    MAX_HALTING
)

# ===================== LOAD MODEL =====================
try:
    model = PPO.load(MODEL_PATH)
    print(f"✅ Model loaded: {MODEL_PATH}")
    print(f"   Model info: {model}")
except Exception as e:
    print(f"❌ Model load failed: {e}")
    exit(1)

# ===================== HELPER FUNCTIONS =====================
def validate_green_times(green_times):
    validated = []
    for g in green_times:
        g = float(g)
        if g < GREEN_MIN:
            g = GREEN_MIN
        elif g > GREEN_MAX:
            g = GREEN_MAX
        red_time = CYCLE_TOTAL - g - 2 * YELLOW_TIME
        if red_time < MIN_RED_TIME:
            red_time = MIN_RED_TIME
            g = CYCLE_TOTAL - red_time - 2 * YELLOW_TIME
            if g < GREEN_MIN:
                g = GREEN_MIN
            elif g > GREEN_MAX:
                g = GREEN_MAX
        validated.append(int(g))
    return validated

def create_observation_from_data(data):
    if data is None:
        return None
    densities_before = data.get("density", [0, 0, 0, 0])
    densities_after = data.get("density_after", [0, 0, 0, 0])
    obs = []
    for i in range(4):
        density_before = densities_before[i] if i < len(densities_before) else 0
        obs.append(min(density_before / MAX_DENSITY, 1.0))
        density_after = densities_after[i] if i < len(densities_after) else 0
        obs.append(min(density_after / MAX_DENSITY, 1.0))
        obs.append(0.0)  # halting
        obs.append(0.0)  # halting

    # ✅ Use current_green (actual previous decision)
    prev_green = data.get("current_green", [30, 30, 30, 30])
    green_alloc_norm = [(g - GREEN_MIN) / (GREEN_MAX - GREEN_MIN) for g in prev_green]
    obs.extend(green_alloc_norm)
    
    obs_array = np.array(obs, dtype=np.float32)
    if len(obs_array) != 20:
        if len(obs_array) > 20:
            obs_array = obs_array[:20]
        else:
            obs_array = np.pad(obs_array, (0, 20 - len(obs_array)), 'constant')
    return obs_array

def calculate_red_times(green_times):
    red_times = []
    for g in green_times:
        red = CYCLE_TOTAL - g - 2 * YELLOW_TIME
        red_times.append(max(red, MIN_RED_TIME))
    return red_times

# ===================== MAIN LOOP =====================
print("🚦 Starting RL Traffic Controller...")
print(f"   Cycle: {CYCLE_TOTAL}s total")
print(f"   Yellow: {YELLOW_TIME}s each (2 per cycle)")
print(f"   Green range: {GREEN_MIN}-{GREEN_MAX}s")
print(f"   Backend URL: {BACKEND_URL}")
print("-" * 50)

decision_count = 0
total_latency = 0
last_print_time = time.time()

while True:
    try:
        try:
            response = requests.get(f"{BACKEND_URL}/get", timeout=1.0)
            if response.status_code != 200:
                print(f"⚠️ Backend responded with status {response.status_code}")
                time.sleep(1)
                continue
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Cannot connect to backend: {e}")
            time.sleep(2)
            continue

        if data.get("beacon", False) and data.get("priority_lane") is not None:
            priority_lane = data.get("priority_lane")
            if time.time() - last_print_time > 5:
                print(f"🚨 Beacon active (Lane {priority_lane}) - skipping RL decision")
                last_print_time = time.time()
            time.sleep(0.5)
            continue

        obs = create_observation_from_data(data)
        if obs is None:
            print("⚠️ Failed to create observation")
            time.sleep(0.5)
            continue

        start_time = time.time()
        try:
            action, _states = model.predict(obs, deterministic=True)
            action = np.clip(action, 0.0, 1.0)
            green_times_float = [float(GREEN_MIN + a * (GREEN_MAX - GREEN_MIN)) 
                                for a in action]
            green_times = validate_green_times(green_times_float)
            red_times = calculate_red_times(green_times)
            latency_ms = int((time.time() - start_time) * 1000)
        except Exception as e:
            print(f"❌ Model prediction error: {e}")
            green_times = [30, 30, 30, 30]
            red_times = calculate_red_times(green_times)
            latency_ms = 0

        try:
            response = requests.post(
                f"{BACKEND_URL}/set_next_cycle",
                json={
                    "next_green": green_times,
                    "latency_ms": latency_ms
                },
                timeout=1.0
            )
            if response.status_code == 200:
                decision_count += 1
                total_latency += latency_ms
                if decision_count % 10 == 0 or time.time() - last_print_time > 30:
                    avg_latency = total_latency / decision_count if decision_count > 0 else 0
                    print(f"🔄 Decision #{decision_count}:")
                    print(f"   Green times: {green_times}")
                    print(f"   Red times: {red_times}")
                    print(f"   Current latency: {latency_ms}ms")
                    print(f"   Avg latency: {avg_latency:.1f}ms")
                    print(f"   Cycle total: {[g+10+r for g,r in zip(green_times, red_times)]}")
                    print("-" * 30)
                    last_print_time = time.time()
            else:
                print(f"⚠️ Backend rejected decision: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Failed to send decision: {e}")

        time.sleep(5.0)  
        
    except KeyboardInterrupt:
        print("\n🛑 Controller stopped by user")
        print(f"   Total decisions made: {decision_count}")
        if decision_count > 0:
            print(f"   Average latency: {total_latency/decision_count:.1f}ms")
        break
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        time.sleep(2)