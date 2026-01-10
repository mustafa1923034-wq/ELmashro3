#!/usr/bin/env python3
"""
Complete Traffic Control System Startup Script
Run: python run_system.py [mode]
Modes: all, backend, dashboard, controller, train
"""

import subprocess
import sys
import time
import os
from config import *

def run_backend():
    """Start backend server"""
    print("🚀 Starting Backend Server...")
    return subprocess.Popen([sys.executable, "backend.py"])

def run_dashboard():
    """Start dashboard"""
    print("📊 Starting Dashboard...")
    return subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard.py"])

def run_controller():
    """Start RL controller"""
    print("🤖 Starting RL Controller...")
    return subprocess.Popen([sys.executable, "traffic_controller.py"])

def run_training():
    """Start RL training"""
    print("🎓 Starting RL Training...")
    return subprocess.Popen([sys.executable, "train_rl.py"])

def check_dependencies():
    """Check if all dependencies are installed"""
    print("🔍 Checking dependencies...")
    try:
        import flask, streamlit, requests, plotly, numpy, stable_baselines3, gymnasium, pyserial
        print("✅ All dependencies installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Run: pip install -r requirements.txt")
        return False

def print_system_info():
    """Print system configuration"""
    print("\n" + "="*60)
    print("🚦 INTELLIGENT TRAFFIC CONTROL SYSTEM")
    print("="*60)
    print(f"Backend URL:    {BACKEND_URL}")
    print(f"ESP Serial:     {ESP_SERIAL_PORT}")
    print(f"Arduino Serial: {ARDUINO_SERIAL_PORT}")
    print(f"Baud Rate:      {BAUD_RATE}")
    print(f"Cycle Timing:   {CYCLE_TOTAL}s total")
    print(f"                {YELLOW_TIME}s yellow × 2")
    print(f"                {GREEN_MIN}-{GREEN_MAX}s green")
    print(f"                {MIN_RED_TIME}s minimum red")
    print("="*60 + "\n")

def main():
    if len(sys.argv) < 2:
        mode = "all"
    else:
        mode = sys.argv[1].lower()
    
    print_system_info()
    
    if not check_dependencies():
        sys.exit(1)
    
    processes = []
    
    try:
        if mode in ["all", "backend"]:
            processes.append(run_backend())
            time.sleep(3)  # Wait for backend to start
        
        if mode in ["all", "dashboard"]:
            processes.append(run_dashboard())
            time.sleep(2)
        
        if mode in ["all", "controller"]:
            # Check if model exists
            if not os.path.exists(MODEL_PATH):
                print(f"⚠️ Model not found: {MODEL_PATH}")
                print("   Run training first or place model in models/ directory")
                train_now = input("   Train model now? (y/n): ").lower()
                if train_now == 'y':
                    processes.append(run_training())
                    print("⏳ Wait for training to complete, then restart controller")
                    return
            else:
                processes.append(run_controller())
        
        if mode == "train":
            processes.append(run_training())
        
        print("\n✅ System components started!")
        print("Press Ctrl+C to stop all processes\n")
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping all processes...")
        
    finally:
        # Terminate all processes
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=5)
            except:
                pass
        
        print("✅ All processes terminated")

if __name__ == "__main__":
    main()