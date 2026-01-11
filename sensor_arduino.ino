/* ===================== CONFIG ===================== */
#define LANES 4
#define SENSORS 8
#define OCCUPIED_DIST 20      // Cars detected if < 20cm
#define FREE_DIST 30          // No car if > 30cm
#define DECAY_INTERVAL 25000  // Decay every 25 seconds
#define DENSITY_SEND_CYCLES 3
#define SENSOR_DELAY_MS 25    // Delay between sensors to prevent crosstalk

const int trigPins[SENSORS] = {2, 4, 6, 8, 10, 11, 12, 13};
const int echoPins[SENSORS] = {3, 5, 7, 9, A0, A1, A2, A3};

/* ===================== STATE ===================== */
int density_before_light[LANES];
int density_after_light[LANES];
bool lastOccupied[SENSORS];
long lastDistance[SENSORS];
bool lastValid[SENSORS];

// Counters
int total_entered[LANES] = {0};
int total_exited[LANES] = {0};

// For sensor health
int errorCount[SENSORS] = {0};
bool sensorStatus[SENSORS] = {true};

unsigned long lastSendTime = 0;
unsigned long lastDecayTime = 0;
int cycleCounter = 0;

// For continuous scanning
static unsigned long lastScanTime = 0;
static int sensorIndex = 0;

/* ===================== UTILS ===================== */
long measureDistanceByIndex(int idx) {
  int t = trigPins[idx];
  int e = echoPins[idx];

  digitalWrite(t, LOW);
  delayMicroseconds(2);
  digitalWrite(t, HIGH);
  delayMicroseconds(10);
  digitalWrite(t, LOW);

  long d = pulseIn(e, HIGH, 30000); // timeout 30ms
  if (d == 0) {
    errorCount[idx]++;
    if (errorCount[idx] > 50) sensorStatus[idx] = false;
    return -1;
  }

  // Valid reading → reset error
  errorCount[idx] = 0;
  sensorStatus[idx] = true;

  long cm = d * 0.034 / 2;
  if (cm > 400 || cm < 2) {
    errorCount[idx]++;
    if (errorCount[idx] > 50) sensorStatus[idx] = false;
    return -1;
  }
  return cm;
}

/* ===================== CORE LOGIC ===================== */
void scanNextSensor() {
  if (millis() - lastScanTime < SENSOR_DELAY_MS) return;

  int i = sensorIndex;
  long dist = measureDistanceByIndex(i);
  
  lastDistance[i] = dist;
  lastValid[i] = (dist != -1);

  bool occupied = lastOccupied[i]; // Default: keep previous state (hysteresis)

  if (dist != -1 && dist < OCCUPIED_DIST) {
    occupied = true;
    if (!lastOccupied[i]) {
      int lane = i / 2;
      if (i % 2 == 0) {
        total_entered[lane]++;
      } else {
        total_exited[lane]++;
      }
    }
  } else if (dist > FREE_DIST || dist == -1) {
    occupied = false;
  }
  // If 20 <= dist <= 30 → do nothing

  lastOccupied[i] = occupied;
  sensorIndex = (sensorIndex + 1) % SENSORS;
  lastScanTime = millis();
}

// Update densities for all lanes 
void updateDensities() {
  for (int l = 0; l < LANES; l++) {
    if (total_entered[l] < 0) total_entered[l] = 0;
    if (total_exited[l] < 0) total_exited[l] = 0;

    density_before_light[l] = total_entered[l] - total_exited[l];
    if (density_before_light[l] < 0) density_before_light[l] = 0;

    density_after_light[l] = total_exited[l];
    if (density_after_light[l] < 0) density_after_light[l] = 0;
  }
}

/* ===================== DECAY ===================== */
void decayCounters() {
  for (int l = 0; l < LANES; l++) {
    if (total_entered[l] > 0) total_entered[l]--;
    if (total_exited[l] > 0) total_exited[l]--;
    
    if (total_entered[l] < 0) total_entered[l] = 0;
    if (total_exited[l] < 0) total_exited[l] = 0;
  }
}

/* ===================== COMM ===================== */
void sendToBackend() {
  Serial.print("DENSITIES:");
  for (int l = 0; l < LANES; l++) {
    Serial.print(density_before_light[l]);
    Serial.print(",");
    Serial.print(density_after_light[l]);
    if (l < LANES - 1) Serial.print(",");
  }
  Serial.println();
}

void sendToController() {
  unsigned long timestamp = millis();
  Serial.print("CYCLE_OBS:");
  Serial.print(timestamp);
  Serial.print(":");
  for (int l = 0; l < LANES; l++) {
    Serial.print(density_before_light[l]);
    Serial.print(",");
    Serial.print(density_after_light[l]);
    Serial.print(",0"); // halting = 0
    if (l < LANES - 1) Serial.print(",");
  }
  Serial.println();
}

void sendSensorStatus() {
  Serial.print("SENSOR_STATUS:");
  for (int i = 0; i < SENSORS; i++) {
    Serial.print(sensorStatus[i] ? 1 : 0);
    if (i < SENSORS - 1) Serial.print(",");
  }
  Serial.println();
}

void handleSerial() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "REQUEST_CYCLE_END") {
      updateDensities();
      sendToController();
    }
  }
}

/* ===================== SETUP ===================== */
void setup() {
  Serial.begin(115200);
  for (int i = 0; i < SENSORS; i++) {
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    lastOccupied[i] = false;
    lastDistance[i] = -1;
    lastValid[i] = false;
    errorCount[i] = 0;
    sensorStatus[i] = true;
  }

  for (int l = 0; l < LANES; l++) {
    total_entered[l] = 0;
    total_exited[l] = 0;
    density_before_light[l] = 0;
    density_after_light[l] = 0;
  }
}

/* ===================== LOOP ===================== */
void loop() {
  scanNextSensor();
  updateDensities();
  handleSerial();

  unsigned long now = millis();

  if (now - lastDecayTime >= DECAY_INTERVAL) {
    decayCounters();
    lastDecayTime = now;
  }

  static unsigned long lastDensitySend = 0;
  
  if (now - lastDensitySend > 1500) {
    cycleCounter++;
    if (cycleCounter >= DENSITY_SEND_CYCLES) {
      sendToBackend();
      cycleCounter = 0;
    }
    lastDensitySend = now;
  }

  static unsigned long lastStatusTime = 0;
  if (now - lastStatusTime > 10000) {
    sendSensorStatus();
    lastStatusTime = now;
  }
}