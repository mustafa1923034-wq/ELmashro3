/* ===================== BLUETOOTH ===================== */
#include "BluetoothSerial.h"
BluetoothSerial SerialBT;

String targetDeviceName = "Emergency_Beacon";
bool beaconDetected = false;
int detectedLane = -1;
unsigned long beaconStartTime = 0;
const unsigned long BEACON_DURATION = 30000;

/* ===================== CONFIG ===================== */
#define LANES 4
#define GREEN_MIN 25
#define GREEN_MAX 35
#define YELLOW 5
#define CYCLE_TOTAL 55
#define MIN_RED_TIME 10

const int redPins[LANES] = {4, 5, 25, 14};
const int yellowPins[LANES] = {16, 18, 26, 12};
const int greenPins[LANES] = {17, 19, 27, 21};

/* ===================== STATE ===================== */
enum {GREEN, YELLOW1, RED, YELLOW2};
unsigned long stageDurations[LANES][4];
unsigned long stageStart[LANES];
int stageIndex[LANES];

int nextGreen[LANES];
int latency_ms = 0;

unsigned long lastDataReceivedTime = 0;
const unsigned long DATA_TIMEOUT = 10000;

static bool decisionReceivedForThisCycle = false;
static unsigned long cycleEndTime = 0;


static bool cycleRequestPending = false;
static unsigned long cycleObsRequestedAt = 0;

// ping
static unsigned long lastPingSent = 0;
const unsigned long PING_INTERVAL = 2500;  


static bool pendingBeacon = false;
static int pendingBeaconLane = -1;

/* ===================== LIGHT CONTROL ===================== */
void updateLights(){
  for(int l = 0; l < LANES; l++){
    unsigned long now = millis();
    if(now - stageStart[l] >= stageDurations[l][stageIndex[l]] * 1000){
      stageIndex[l] = (stageIndex[l] + 1) % 4;
      stageStart[l] = now;
    }

    // cycle state
    static int lastReportedPhase[LANES] = {-1, -1, -1, -1};
    if (stageIndex[l] != lastReportedPhase[l]) {
      Serial.print("PHASE:");
      Serial.print(l);
      Serial.print(":");
      Serial.println(stageIndex[l]);
      lastReportedPhase[l] = stageIndex[l];
    }

    // send current 
    unsigned long totalCycleTime = 0;
    for(int i = 0; i < 4; i++) {
      totalCycleTime += stageDurations[l][i] * 1000;
    }
    
    unsigned long elapsedInStage = now - stageStart[l];
    unsigned long currentCycleTime = 0;
    
    // current time
    for(int i = 0; i <= stageIndex[l]; i++) {
      if(i == stageIndex[l]) {
        currentCycleTime += elapsedInStage;
      } else {
        currentCycleTime += stageDurations[l][i] * 1000;
      }
    }
    
    int cycleSec = (currentCycleTime / 1000) % 55;
    static int lastReportedCycleTime[LANES] = {0, 0, 0, 0};
    if (cycleSec != lastReportedCycleTime[l]) {
      Serial.print("PROGRESS:");
      Serial.print(l);
      Serial.print(":");
      Serial.println(cycleSec);
      lastReportedCycleTime[l] = cycleSec;
    }

   
    if(l == 0 && stageIndex[l] == RED && !cycleRequestPending && !beaconDetected) {
      unsigned long elapsed = now - stageStart[l];
      unsigned long redDurationMs = stageDurations[l][RED] * 1000;
      if(elapsed >= redDurationMs - 2000 && elapsed < redDurationMs - 1000) {
        Serial.println("REQUEST_CYCLE_END");
        cycleRequestPending = true;
        cycleObsRequestedAt = now;
      }
    }

    switch(stageIndex[l]){
      case GREEN:
        digitalWrite(redPins[l], LOW);
        digitalWrite(yellowPins[l], LOW);
        digitalWrite(greenPins[l], HIGH);
        break;
      case RED:
        digitalWrite(redPins[l], HIGH);
        digitalWrite(yellowPins[l], LOW);
        digitalWrite(greenPins[l], LOW);
        break;
      case YELLOW1:
      case YELLOW2:
        digitalWrite(redPins[l], LOW);
        digitalWrite(greenPins[l], LOW);
        if((millis() / 75) % 2 == 0) digitalWrite(yellowPins[l], HIGH);
        else digitalWrite(yellowPins[l], LOW);
        break;
    }
  }
}

/* ===================== BEACON LOGIC (DEFERRED) ===================== */
void requestBeacon(int lane) {
  pendingBeacon = true;
  pendingBeaconLane = lane;
  beaconDetected = true;
  detectedLane = lane;
  beaconStartTime = millis();
}

void applyPendingBeaconIfAny() {
  if (!pendingBeacon) return;

  int lane = pendingBeaconLane;
  int sysBase = (lane < 2) ? 0 : 2;
  int otherLane = (lane == sysBase) ? sysBase + 1 : sysBase;
  int otherSysBase = (sysBase == 0) ? 2 : 0;

  // the chosen lane
  stageDurations[lane][GREEN] = 35;
  stageDurations[lane][YELLOW1] = YELLOW;
  stageDurations[lane][RED] = 10;
  stageDurations[lane][YELLOW2] = YELLOW;

  // the second lane
  stageDurations[otherLane][GREEN] = 25;
  stageDurations[otherLane][YELLOW1] = YELLOW;
  stageDurations[otherLane][RED] = 20;
  stageDurations[otherLane][YELLOW2] = YELLOW;

  // the other system
  for (int i = 0; i < 2; i++) {
    int l = otherSysBase + i;
    int safe_green = nextGreen[l];
    if (safe_green < GREEN_MIN) safe_green = GREEN_MIN;
    else if (safe_green > GREEN_MAX) safe_green = GREEN_MAX;
    int red_time = CYCLE_TOTAL - safe_green - 2 * YELLOW;
    if (red_time < MIN_RED_TIME) {
      red_time = MIN_RED_TIME;
      safe_green = CYCLE_TOTAL - red_time - 2 * YELLOW;
      if (safe_green < GREEN_MIN) safe_green = GREEN_MIN;
      else if (safe_green > GREEN_MAX) safe_green = GREEN_MAX;
    }
    stageDurations[l][GREEN] = safe_green;
    stageDurations[l][YELLOW1] = YELLOW;
    stageDurations[l][RED] = red_time;
    stageDurations[l][YELLOW2] = YELLOW;
  }

  pendingBeacon = false;
  pendingBeaconLane = -1;
}

void checkBeaconTimeout() {
  if (beaconDetected && (millis() - beaconStartTime >= BEACON_DURATION)) {
    beaconDetected = false;
    detectedLane = -1;
    Serial.println("BEACON_CLEAR");
  }
}

/* ===================== BLUETOOTH BEACON ===================== */
void checkBluetoothBeacon(){
  if (SerialBT.hasClient()) {
    String received = SerialBT.readString();
    received.trim();
    if (received.startsWith("EMERGENCY_LANE:")) {
      int lane = received.substring(15).toInt();
      if (lane >= 0 && lane < LANES) {
        requestBeacon(lane);
        Serial.print("PRIORITY:");
        Serial.println(lane);
      }
    }
  }
}

/* ===================== COMMUNICATION ===================== */
void readController(){
  if (Serial.available()) {
    static String buffer = "";
    unsigned long start = millis();
    while (Serial.available() && (millis() - start) < 50) {
      char c = Serial.read();
      if (c == '\n') {
        String line = buffer;
        buffer = "";
        line.trim();
        if (line.isEmpty()) continue;

        if(line.startsWith("NEXT_GREEN:")){
          String data = line.substring(11);
          int idx = 0;
          int start = 0;
          for(int i = 0; i <= data.length(); i++){
            if(i == data.length() || data.charAt(i) == ','){
              if(idx < LANES) {
                nextGreen[idx] = data.substring(start, i).toInt();
              }
              start = i + 1;
              idx++;
            }
          }

          for(int l = 0; l < LANES; l++){
            int safe_green = nextGreen[l];
            if(safe_green < GREEN_MIN) safe_green = GREEN_MIN;
            else if(safe_green > GREEN_MAX) safe_green = GREEN_MAX;

            int red_time = CYCLE_TOTAL - safe_green - 2 * YELLOW;
            if(red_time < MIN_RED_TIME) {
              red_time = MIN_RED_TIME;
              safe_green = CYCLE_TOTAL - red_time - 2 * YELLOW;
              if(safe_green < GREEN_MIN) safe_green = GREEN_MIN;
              else if(safe_green > GREEN_MAX) safe_green = GREEN_MAX;
            }

            stageDurations[l][GREEN] = safe_green;
            stageDurations[l][YELLOW1] = YELLOW;
            stageDurations[l][RED] = red_time;
            stageDurations[l][YELLOW2] = YELLOW;
          }

          lastDataReceivedTime = millis();
          decisionReceivedForThisCycle = true;

          if(cycleEndTime > 0) {
            unsigned long now = millis();
            unsigned long latency = now - cycleEndTime;
            Serial.print("LATENCY:");
            Serial.println(latency);
            cycleEndTime = 0;
          }

        } else if(line.startsWith("PRIORITY:")){
          int lane = line.substring(9).toInt();
          requestBeacon(lane);
          Serial.print("PRIORITY:");
          Serial.println(lane);
        } else if(line == "CYCLE_OBS:"){
          cycleRequestPending = false;
        } else if(line == "EXTEND_BEACON"){
          if(beaconDetected){
            beaconStartTime = millis() - (BEACON_DURATION - 30000);
            Serial.println("BEACON_EXTENDED");
          }
        } else if(line.startsWith("CYCLE_END:")){
          int firstColon = line.indexOf(':');
          int secondColon = line.indexOf(':', firstColon + 1);
          if(secondColon != -1) {
            String tsStr = line.substring(firstColon + 1, secondColon);
            cycleEndTime = tsStr.toInt();
          }
        }

      } else if (c != '\r') {
        buffer += c;
        if (buffer.length() > 100) buffer = "";
      }
    }
  }
}

/* ===================== CYCLE OBS TIMEOUT HANDLER ===================== */
void checkCycleObsTimeout() {
  if(cycleRequestPending && millis() - cycleObsRequestedAt > 2000) {
    Serial.println("CYCLE_OBS_TIMEOUT");
    cycleRequestPending = false;
  }
}

/* ===================== DEFAULT TIMING (FALLBACK) ===================== */
void applyDefaultTiming(){
  for(int l = 0; l < LANES; l++){
    stageDurations[l][GREEN] = 30;
    stageDurations[l][YELLOW1] = YELLOW;
    stageDurations[l][RED] = CYCLE_TOTAL - 30 - 2 * YELLOW;
    stageDurations[l][YELLOW2] = YELLOW;
  }
}

/* ===================== SEND MONITORING DATA ===================== */
void sendAppliedCycleOncePerCycle(){
  String applied = "APPLIED_CYCLE:";
  for (int l = 0; l < LANES; l++) {
    applied += String(stageDurations[l][GREEN]) + ",";
    applied += String(stageDurations[l][YELLOW1]) + ",";
    applied += String(stageDurations[l][RED]) + ",";
    applied += String(stageDurations[l][YELLOW2]);
    if (l < LANES - 1) applied += ",";
  }
  Serial.println(applied);
}

/* ===================== SEND PING TO BACKEND ===================== */
void sendPing() {
  unsigned long now = millis();
  if (now - lastPingSent > PING_INTERVAL) {
    Serial.println("PING");
    lastPingSent = now;
  }
}

/* ===================== SETUP ===================== */
void setup(){
  Serial.begin(115200);
  SerialBT.begin("ESP32_Beacon_Receiver");
  
  for(int i = 0; i < LANES; i++){
    pinMode(redPins[i], OUTPUT);
    pinMode(yellowPins[i], OUTPUT);
    pinMode(greenPins[i], OUTPUT);
    stageIndex[i] = 0;
    stageStart[i] = millis();
    stageDurations[i][GREEN] = 30;
    stageDurations[i][YELLOW1] = YELLOW;
    stageDurations[i][RED] = 15;
    stageDurations[i][YELLOW2] = YELLOW;
  }
  
  lastDataReceivedTime = millis();
  Serial.println("✅ ESP32 Beacon Receiver Ready");
  Serial.println("🔍 Searching for: Emergency_Beacon");
}

/* ===================== LOOP ===================== */
void loop(){
  checkBluetoothBeacon();

  static unsigned long lastAppliedCycleStart = 0;
  unsigned long now = millis();
  
 
  for(int l = 0; l < LANES; l++) {
    if(stageIndex[l] == GREEN && (now - stageStart[l]) < 100) {
      if (stageStart[l] != lastAppliedCycleStart) {
       
        if (pendingBeacon) {
          applyPendingBeaconIfAny();
          decisionReceivedForThisCycle = true;
        }
        
        
        if(!decisionReceivedForThisCycle) {
          applyDefaultTiming();
          Serial.println("FALLBACK: default cycle applied");
        }
        
        
        sendAppliedCycleOncePerCycle();
        
       
        lastAppliedCycleStart = stageStart[l];
        decisionReceivedForThisCycle = false;
      }
      break; 
    }
  }


  if(now - lastDataReceivedTime > DATA_TIMEOUT && !beaconDetected){
    applyDefaultTiming();
  }
  
  updateLights();
  readController();
  checkBeaconTimeout(); 
  checkCycleObsTimeout();
  sendPing();
}