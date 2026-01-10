/* ===================== CONFIG ===================== */
#define LANES 4
#define SENSORS 8

#define OCCUPIED_DIST 20     // < 20cm = car detected
#define FREE_DIST 30         // > 30cm = free
#define SENSOR_DELAY_MS 25   // Delay between sensors (anti-crosstalk)

const int trigPins[SENSORS] = {2, 4, 6, 8, 10, 12, 11, 13};
const int echoPins[SENSORS] = {3, 5, 7, 9, A0, A1, A2, A3};

/* ===================== STATE ===================== */
bool lastOccupied[SENSORS] = {false};

// Counters per lane
int total_entered[LANES] = {0};
int total_exited[LANES]  = {0};

// Store last readings for continuous printing
long lastDistance[SENSORS];
bool lastValid[SENSORS];

unsigned long lastPrintTime = 0;
const unsigned long PRINT_INTERVAL_MS = 3000; // ← كل 3 ثواني دلوقتي

/* ===================== UTILS ===================== */
long measureDistance(int t, int e){
  digitalWrite(t, LOW); 
  delayMicroseconds(2);
  digitalWrite(t, HIGH); 
  delayMicroseconds(10);
  digitalWrite(t, LOW);

  long d = pulseIn(e, HIGH, 30000); // timeout 30ms
  if(d == 0) {
    return -1; // No echo
  }

  long cm = d * 0.034 / 2;
  if(cm > 400) return -1;
  return cm;
}

/* ===================== SETUP ===================== */
void setup(){
  Serial.begin(115200);

  for(int i = 0; i < SENSORS; i++){
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    lastOccupied[i] = false;
    lastDistance[i] = -1;
    lastValid[i] = false;
  }

  for(int l = 0; l < LANES; l++){
    total_entered[l] = 0;
    total_exited[l]  = 0;
  }

  Serial.println("Ultrasonic Sensor Test Started...");
}

/* ===================== LOOP ===================== */
void loop(){
  unsigned long now = millis();

  // === Read sensors continuously (one every ~25ms) ===
  static unsigned long lastScanTime = 0;
  static int sensorIndex = 0;

  if (now - lastScanTime >= SENSOR_DELAY_MS) {
    int i = sensorIndex;

    long dist = measureDistance(trigPins[i], echoPins[i]);
    lastDistance[i] = dist;
    lastValid[i] = (dist != -1);

    bool occupied = false;
    if (dist > 0 && dist < OCCUPIED_DIST) {
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
    // Between 20–30cm? Keep previous state (hysteresis)
    lastOccupied[i] = occupied;

    sensorIndex = (sensorIndex + 1) % SENSORS;
    lastScanTime = now;
  }

  // === Print full report every 3 seconds ===
  if (now - lastPrintTime >= PRINT_INTERVAL_MS) {
    lastPrintTime = now;

    Serial.println("-------------------------");
    Serial.println("---- Sensor Test ----");

    for(int i = 0; i < SENSORS; i++){
      long dist = lastDistance[i];
      bool valid = lastValid[i];
      bool occupied = lastOccupied[i];

      Serial.print("Sensor ");
      Serial.print(i);
      Serial.print(": ");

      if(dist == -1){
        Serial.print("No echo");
      } else {
        Serial.print(dist);
        Serial.print(" cm");
      }

      Serial.print(" | Status: ");
      Serial.print(valid ? "ON" : "OFF");

      Serial.print(" | Occupied: ");
      Serial.println(occupied ? "YES" : "NO");

      delay(SENSOR_DELAY_MS); // same as original, for consistency in print timing
    }

    // ===== Print densities (exactly like your original code) =====
    Serial.println("---- DENSITY (TEST) ----");
    for(int l = 0; l < LANES; l++){
      int density_before = max(0, total_entered[l] - total_exited[l]);
      int density_after  = total_exited[l];

      Serial.print("Lane ");
      Serial.print(l);
      Serial.print(" | Before Light: ");
      Serial.print(density_before);
      Serial.print(" | After Light: ");
      Serial.println(density_after);
    }

    Serial.println("-------------------------");
  }
}