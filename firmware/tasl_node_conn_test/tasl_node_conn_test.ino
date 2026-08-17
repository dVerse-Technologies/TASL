/* ============================================================================
   TASL marble run - NODE FIRMWARE (network + battery monitoring)
   Board: ESP32 DevKit V1 (DOIT, 30-pin)
   Power: TP4056 charger module + 1S 3.7 V LiPo

   WHAT THIS IS FOR
   Proves the network path works AND reports real battery level:

       ESP32  ->  Wi-Fi  ->  router  ->  laptop  ->  dashboard

   There are still NO IR sensors. Ball events are faked on a button press.
   That is Step 3.

   WHAT IT DOES
     - connects to Wi-Fi, printing progress to the Serial Monitor
     - sends BOOT once at startup
     - sends a heartbeat every 2 seconds, carrying real battery millivolts
     - sends LOW_BATTERY once each time the battery drops a state
     - sends a fake BALL_PASS every time you press the onboard BOOT button
     - queues messages if the laptop is unreachable, and flushes them on
       reconnect

   BATTERY WIRING
     LiPo + ----[ R1 ]----+----[ R2 ]---- GND
                          |
                       GPIO 34

   R1 and R2 equal (100k/100k recommended - 10k/10k works but wastes ~200 uA
   continuously, which matters across a long event day).

   GPIO 34 is on ADC1. This is not optional: ADC2 pins stop working the moment
   Wi-Fi is enabled, so a battery reading on ADC2 would test perfectly on the
   bench and then read zero in the field.

   ONBOARD LED (GPIO2, blue)
     fast blinking       = connecting to Wi-Fi
     short flash         = message sent successfully
     three rapid flashes = send failed, message queued

   NO EXTRA LIBRARIES NEEDED. WiFi.h and HTTPClient.h ship with the ESP32 core.
   ========================================================================= */

#include <WiFi.h>
#include <HTTPClient.h>

// Wi-Fi credentials and the laptop's IP live in secrets.h, which is
// gitignored - that is what keeps them off GitHub. Copy secrets.example.h to
// secrets.h and fill in your own values.
#include "secrets.h"

/* ===========================================================================
   EDIT THIS ONE LINE PER BOARD. Everything else is in secrets.h.
   =========================================================================== */

// Must be different on each board: NODE01, NODE02, NODE03.
// Must exactly match a node_id in config/nodes.json on the laptop.
#define NODE_ID  "NODE02"

/* ======================= end of things to edit ============================ */

const char* WIFI_SSID = TASL_WIFI_SSID;
const char* WIFI_PASS = TASL_WIFI_PASS;
const char* SERVER_IP = TASL_SERVER_IP;

const uint16_t SERVER_PORT  = 8000;
const char*    FW_VERSION   = "batt-1.1.0";

// Echoed in ball events so the log is self-describing. Not used for anything
// real until Step 3, when it becomes the actual beam spacing you measure.
const float    GAP_MM       = 100.0;

const uint8_t  PIN_LED      = 2;   // onboard blue LED on DevKit V1
const uint8_t  PIN_BUTTON   = 0;   // onboard BOOT button - doubles as our test trigger

/* ==========================================================================
   IR BEAM ALIGNMENT (build stage 4)

   Reads both beams and prints a live readout so you can aim each sensor and
   see the margin you actually have, rather than guessing. It does NOT time
   balls yet - that is stage 5.

   Wiring per beam (see hardware/NODE_WIRING.md section 6):

     3V3 -- [100 ohm] -->|-- IR emitter -- GND
     3V3 -- phototransistor COLLECTOR
            phototransistor EMITTER --+-- [10k] -- GND
                                      +-- GPIO

   Beam clear    -> phototransistor conducts -> pin reads HIGH
   Beam blocked  -> phototransistor off      -> 10k pulls it LOW

   So a ball is a FALLING edge. Set BEAM_ALIGN 0 once both beams are aimed.
   ========================================================================== */

#define BEAM_ALIGN      1     // 1 = print the live alignment readout

#define PIN_BEAM_A      32    // ADC1. Same reason as the battery pin.
#define PIN_BEAM_B      33    // ADC1.

const unsigned long BEAM_PRINT_MS = 400;

// A clear beam should sit near 4095 and a blocked one near 0. Anything in
// between is a beam that is aimed badly enough to trigger unreliably later,
// which is exactly the fault that is impossible to find once 20 nodes are
// bolted to a track.
const int BEAM_GOOD_MARGIN = 1500;

const unsigned long HEARTBEAT_MS   = 2000;
const unsigned long WIFI_RETRY_MS  = 5000;
const unsigned long DEBOUNCE_MS    = 250;

// Set to a number of milliseconds to fire a ball automatically on a timer
// (e.g. 15000). Leave at 0 to only fire on a button press.
const unsigned long AUTO_BALL_MS   = 0;

/* ==========================================================================
   BATTERY MONITORING
   ========================================================================== */

// Set to 0 on a board where the divider is not fitted. It will report UNKNOWN
// instead of pretending, which is the honest answer and keeps the dashboard
// from showing a fake red battery.
#define BATT_ENABLED    1

#define PIN_BATTERY     34      // ADC1 only. See the note at the top of this file.

// R1 and R2 are equal, so the pin sees half the pack voltage. Multiply back up.
const float BATT_DIVIDER  = 2.0f;

// Trim for resistor tolerance. 5% resistors can put the real divider anywhere
// between about 1.90 and 2.10, which is +/- 0.2 V at the pack - easily a whole
// battery state. CALIBRATE THIS ONCE PER BOARD:
//
//   1. flash, open Serial Monitor at 115200, read the "batt:" line
//   2. measure the actual pack voltage with a multimeter
//   3. BATT_CAL = measured_volts / reported_volts
//   4. reflash
//
// Leave at 1.000 until you have actually measured it.
const float BATT_CAL      = 1.000f;

// If this fails to compile you are on ESP32 Arduino core 1.x. Set it to 0 to
// fall back to the plain ratio maths with a fixed offset.
#define USE_ADC_CALIBRATION  1

// Fixed fudge used only when USE_ADC_CALIBRATION is 0.
const float ADC_OFFSET_V  = 0.05f;
const float ADC_REF_V     = 3.3f;

// How often to take a reading. Independent of the heartbeat so a sample is
// never taken during the current spike of a Wi-Fi transmit, which would read
// artificially low.
const unsigned long BATT_SAMPLE_MS = 500;
const unsigned long BATT_PRINT_MS  = 5000;
const int           BATT_SAMPLES   = 16;

/* State thresholds, in millivolts, for a 1S LiPo.

   Deliberately four coarse steps, not a percentage. A LiPo holds voltage
   nearly flat through most of its usable charge then falls off a cliff, so a
   proportional bar reads "almost full" right up until the node dies.

   Chosen with ~100 mV of Wi-Fi transmit sag already in mind - these are the
   voltages you want to act on, not the datasheet's empty point. */
const int BATT_T_GREEN  = 3850;   // >= this is healthy
const int BATT_T_YELLOW = 3700;   // >= this is getting low
const int BATT_T_RED    = 3580;   // >= this is low; below is critical

// A reading must beat a threshold by this much to climb back UP a state.
// Without it, a pack sitting exactly on a boundary flips state on every
// transmit and the dashboard blinks GREEN/YELLOW at the audience all day.
const int BATT_HYSTERESIS_MV = 40;

// Below this, nothing plausible is connected - an unplugged divider, wrong
// pin, or a broken joint. Report UNKNOWN rather than a false CRITICAL.
const int BATT_SANITY_MIN_MV = 2500;
// Above this the pack cannot really be: 4.2 V is a full 1S cell and the TP4056
// will not push past it. Means BATT_CAL or BATT_DIVIDER is wrong.
const int BATT_SANITY_MAX_MV = 4350;

/* --------------------------------------------------------------------------
   Offline outbox.

   A node that cannot reach the laptop must not lose the ball it just measured.
   Fixed-size arrays, not dynamic allocation - an ESP32 that fragments its heap
   over a long event is an ESP32 that crashes during the finale.
   -------------------------------------------------------------------------- */
#define QUEUE_MAX       12
#define QUEUE_BODY_LEN  384
#define QUEUE_PATH_LEN  24

char  q_path[QUEUE_MAX][QUEUE_PATH_LEN];
char  q_body[QUEUE_MAX][QUEUE_BODY_LEN];
int   q_count = 0;

uint32_t      g_seq            = 0;
unsigned long g_lastHeartbeat  = 0;
unsigned long g_lastWifiTry    = 0;
unsigned long g_lastButton     = 0;
unsigned long g_lastAutoBall   = 0;
unsigned long g_lastBattSample = 0;
unsigned long g_lastBattPrint  = 0;
unsigned long g_lastBeamPrint  = 0;

// Smoothed battery reading. -1 means "no valid reading yet".
float g_battMvEma   = -1.0f;
bool  g_battValid   = false;
int   g_battLevel   = 3;      // 3=GREEN 2=YELLOW 1=RED 0=CRITICAL
bool  g_battWarned  = false;  // suppresses repeat calibration warnings

const char* LEVEL_NAME[4] = { "CRITICAL", "RED", "YELLOW", "GREEN" };

/* ------------------------------------------------------------------ LED --- */

void flash(int times, int on_ms, int off_ms) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_LED, HIGH);
    delay(on_ms);
    digitalWrite(PIN_LED, LOW);
    if (i < times - 1) delay(off_ms);
  }
}

/* -------------------------------------------------------------- battery --- */

// Returns the pack voltage in millivolts, or -1 if nothing sane is connected.
int readBatteryMv() {
#if !BATT_ENABLED
  return -1;
#else
  uint32_t sum = 0;
  for (int i = 0; i < BATT_SAMPLES; i++) {
    #if USE_ADC_CALIBRATION
      // Uses the per-chip calibration burned into eFuse at the factory. This
      // corrects the ESP32's well-known ADC non-linearity properly, which is
      // strictly better than raw/4095 * 3.3 plus a guessed offset.
      sum += analogReadMilliVolts(PIN_BATTERY);
    #else
      sum += analogRead(PIN_BATTERY);
    #endif
    delayMicroseconds(200);
  }

  float pin_mv;
  #if USE_ADC_CALIBRATION
    pin_mv = (float)sum / BATT_SAMPLES;
  #else
    float raw = (float)sum / BATT_SAMPLES;
    pin_mv = (raw / 4095.0f) * ADC_REF_V * 1000.0f;
    if (raw > 0) pin_mv += ADC_OFFSET_V * 1000.0f;
  #endif

  float pack_mv = pin_mv * BATT_DIVIDER * BATT_CAL;

  if (pack_mv < BATT_SANITY_MIN_MV) {
    if (!g_battWarned) {
      g_battWarned = true;
      Serial.printf("[batt] reading %.0f mV is too low to be a live pack.\n", pack_mv);
      Serial.println("       Check the divider is soldered to GPIO34 and to GND,");
      Serial.println("       or set BATT_ENABLED 0 if this board has no divider.");
    }
    return -1;
  }
  if (pack_mv > BATT_SANITY_MAX_MV) {
    if (!g_battWarned) {
      g_battWarned = true;
      Serial.printf("[batt] reading %.0f mV is above a full 1S cell (4200 mV).\n", pack_mv);
      Serial.println("       BATT_CAL or BATT_DIVIDER is wrong. Measure the pack with a");
      Serial.println("       multimeter and set BATT_CAL = measured / reported.");
    }
    return -1;
  }
  return (int)(pack_mv + 0.5f);
#endif
}

// Which state a voltage implies. 'margin' is added to every threshold, so
// passing the hysteresis value asks "is it comfortably in a better state?".
int battLevelFor(int mv, int margin) {
  if (mv >= BATT_T_GREEN  + margin) return 3;
  if (mv >= BATT_T_YELLOW + margin) return 2;
  if (mv >= BATT_T_RED    + margin) return 1;
  return 0;
}

const char* battStateName() {
  return g_battValid ? LEVEL_NAME[g_battLevel] : "UNKNOWN";
}

void sendLowBattery(int mv, const char* state);

void sampleBattery() {
  int mv = readBatteryMv();
  if (mv < 0) {
    g_battValid = false;
    return;
  }

  // Exponential moving average. A single sample taken while the radio fires
  // can read 100 mV low; the average rides over that without hiding a real
  // decline, which happens over minutes not milliseconds.
  if (g_battMvEma < 0) {
    g_battMvEma = mv;            // seed, so we do not ramp up from zero
    g_battLevel = battLevelFor(mv, 0);
  } else {
    g_battMvEma = (g_battMvEma * 0.8f) + (mv * 0.2f);
  }
  g_battValid = true;

  int smoothed = (int)(g_battMvEma + 0.5f);
  int falling  = battLevelFor(smoothed, 0);
  int rising   = battLevelFor(smoothed, BATT_HYSTERESIS_MV);

  int previous = g_battLevel;
  if (falling < g_battLevel) {
    g_battLevel = falling;       // drop immediately - never hide a dying cell
  } else if (rising > g_battLevel) {
    g_battLevel = rising;        // climb only once clearly past the threshold
  }

  // One event per downward step. Not on every heartbeat, or the log floods and
  // the real transition becomes impossible to find.
  if (g_battLevel < previous) {
    Serial.printf("[batt] state fell %s -> %s at %d mV\n",
                  LEVEL_NAME[previous], LEVEL_NAME[g_battLevel], smoothed);
    sendLowBattery(smoothed, LEVEL_NAME[g_battLevel]);
  }
}

void printBattery() {
  if (!g_battValid) {
    Serial.println("[batt] no valid reading - reporting UNKNOWN to the dashboard");
    return;
  }
  int   mv  = (int)(g_battMvEma + 0.5f);
  // Percentage is printed for your reference only. It is deliberately NOT sent
  // to the dashboard: see the threshold comment above for why a 1S LiPo
  // percentage bar lies to you.
  float pct = ((mv - 3400.0f) / (4200.0f - 3400.0f)) * 100.0f;
  if (pct < 0)   pct = 0;
  if (pct > 100) pct = 100;
  Serial.printf("[batt] %d mV  (%.2f V)  state=%s  approx %.0f%%\n",
                mv, mv / 1000.0f, battStateName(), pct);
}

/* ----------------------------------------------------------------- beams --- */

#if BEAM_ALIGN
// Alignment uses the ANALOG level only, never digitalRead. On the ESP32 an
// analogRead() re-routes the pad to the ADC and switches the digital input
// path off, so a pin you have analogRead() once will read LOW from
// digitalRead() forever afterwards. Mixing the two on one pin is a trap.
//
// That is also why BEAM_ALIGN must go to 0 before stage 5: ball timing uses
// digitalRead and the two modes cannot share a pin.
//
// Analog is the better tool for aiming anyway - digital only says "past the
// threshold", not how much margin you have.
void printBeam(const char* name, uint8_t pin) {
  int raw   = analogRead(pin);
  bool clear = raw > 2048;          // mid-rail, representative of the digital trip point

  const char* verdict;
  if (clear && raw >= BEAM_GOOD_MARGIN)             verdict = "CLEAR   (good)";
  else if (clear)                                   verdict = "CLEAR   (WEAK - aim it better)";
  else if (raw <= 4095 - BEAM_GOOD_MARGIN)          verdict = "BLOCKED (good)";
  else                                              verdict = "BLOCKED (marginal)";

  Serial.printf("  beam %s: %-7s raw=%4d  %s\n",
                name, clear ? "CLEAR" : "BLOCKED", raw, verdict);
}

void printBeams() {
  Serial.println("[beam] alignment readout");
  printBeam("A", PIN_BEAM_A);
  printBeam("B", PIN_BEAM_B);
}
#endif

/* ----------------------------------------------------------------- Wi-Fi --- */

void connectWiFi() {
  Serial.printf("[wifi] connecting to \"%s\" ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);

  // Stops the ESP32 from writing new credentials to flash on every boot, and
  // from silently reusing stale ones you thought you'd changed.
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    digitalWrite(PIN_LED, !digitalRead(PIN_LED));
    delay(100);
  }
  digitalWrite(PIN_LED, LOW);

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[wifi] CONNECTED");
    Serial.printf("       node id : %s\n", NODE_ID);
    Serial.printf("       my IP   : %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("       gateway : %s\n", WiFi.gatewayIP().toString().c_str());
    Serial.printf("       signal  : %d dBm\n", WiFi.RSSI());
    Serial.printf("       server  : http://%s:%u\n", SERVER_IP, SERVER_PORT);
  } else {
    Serial.println("[wifi] FAILED to connect. Common causes:");
    Serial.println("       - SSID is a 5 GHz network (ESP32 is 2.4 GHz only)");
    Serial.println("       - wrong password");
    Serial.println("       - SSID typed with wrong case (it is case sensitive)");
    Serial.println("       Retrying...");
  }
}

/* ------------------------------------------------------------- transport --- */

// Returns true if the message is dealt with (delivered, or rejected as bad and
// not worth retrying). Returns false if it should be queued and tried again.
bool postJson(const char* path, const char* body) {
  if (WiFi.status() != WL_CONNECTED) return false;

  char url[96];
  snprintf(url, sizeof(url), "http://%s:%u%s", SERVER_IP, SERVER_PORT, path);

  HTTPClient http;
  http.setConnectTimeout(2500);
  http.setTimeout(2500);
  if (!http.begin(url)) {
    Serial.println("[net] http.begin failed");
    return false;
  }
  http.addHeader("Content-Type", "application/json");

  int code = http.POST((uint8_t*)body, strlen(body));
  http.end();

  if (code == 404) {
    // The laptop does not have this node_id in config/nodes.json. Retrying
    // forever will not fix a typo, so drop it and shout instead.
    Serial.printf("[net] REJECTED: server does not know node_id \"%s\".\n", NODE_ID);
    Serial.println("      Fix config/nodes.json on the laptop, or fix NODE_ID here.");
    return true;
  }
  if (code <= 0) {
    Serial.printf("[net] no response (%d) - is the server running? is the firewall open?\n", code);
    return false;
  }
  return (code >= 200 && code < 300);
}

void enqueue(const char* path, const char* body) {
  if (q_count >= QUEUE_MAX) {
    // Drop the oldest. A stale heartbeat is worthless; a recent one is not.
    for (int i = 1; i < QUEUE_MAX; i++) {
      strncpy(q_path[i - 1], q_path[i], QUEUE_PATH_LEN);
      strncpy(q_body[i - 1], q_body[i], QUEUE_BODY_LEN);
    }
    q_count = QUEUE_MAX - 1;
  }
  strncpy(q_path[q_count], path, QUEUE_PATH_LEN - 1);
  q_path[q_count][QUEUE_PATH_LEN - 1] = '\0';
  strncpy(q_body[q_count], body, QUEUE_BODY_LEN - 1);
  q_body[q_count][QUEUE_BODY_LEN - 1] = '\0';
  q_count++;
}

void sendOrQueue(const char* path, const char* body) {
  if (postJson(path, body)) {
    flash(1, 25, 0);
  } else {
    enqueue(path, body);
    flash(3, 40, 60);
    Serial.printf("[net] laptop unreachable - queued (%d waiting)\n", q_count);
  }
}

void drainQueue() {
  if (q_count == 0 || WiFi.status() != WL_CONNECTED) return;

  int sent = 0;
  while (q_count > 0) {
    if (!postJson(q_path[0], q_body[0])) break;   // still down; try again later
    for (int i = 1; i < q_count; i++) {
      strncpy(q_path[i - 1], q_path[i], QUEUE_PATH_LEN);
      strncpy(q_body[i - 1], q_body[i], QUEUE_BODY_LEN);
    }
    q_count--;
    sent++;
  }
  if (sent) Serial.printf("[net] reconnected - flushed %d queued message(s)\n", sent);
}

/* ---------------------------------------------------------------- events --- */

// The fields every message carries. Written into a caller-supplied buffer so
// we never allocate on the heap.
//
// batt_mv is omitted entirely when we have no valid reading, rather than sent
// as 0. The dashboard then shows a grey empty battery - "I don't know" - which
// is a different and more useful statement than "flat".
void baseFields(char* buf, size_t n) {
  g_seq++;
  if (g_battValid) {
    snprintf(buf, n,
      "\"node_id\":\"%s\",\"fw\":\"%s\",\"proto\":1,\"seq\":%lu,"
      "\"uptime_ms\":%lu,\"batt_mv\":%d,\"batt_state\":\"%s\",\"rssi\":%d",
      NODE_ID, FW_VERSION,
      (unsigned long)g_seq,
      (unsigned long)millis(),
      (int)(g_battMvEma + 0.5f),
      battStateName(),
      (int)WiFi.RSSI());
  } else {
    snprintf(buf, n,
      "\"node_id\":\"%s\",\"fw\":\"%s\",\"proto\":1,\"seq\":%lu,"
      "\"uptime_ms\":%lu,\"batt_state\":\"UNKNOWN\",\"rssi\":%d",
      NODE_ID, FW_VERSION,
      (unsigned long)g_seq,
      (unsigned long)millis(),
      (int)WiFi.RSSI());
  }
}

void sendBoot() {
  char base[256], body[QUEUE_BODY_LEN];
  baseFields(base, sizeof(base));
  snprintf(body, sizeof(body),
           "{%s,\"event\":\"BOOT\",\"note\":\"network + battery firmware\"}", base);
  sendOrQueue("/api/event", body);
  Serial.println("[evt] BOOT sent");
}

void sendHeartbeat() {
  char base[256], body[QUEUE_BODY_LEN];
  baseFields(base, sizeof(base));
  snprintf(body, sizeof(body), "{%s}", base);
  sendOrQueue("/api/heartbeat", body);
}

void sendLowBattery(int mv, const char* state) {
  char base[256], body[QUEUE_BODY_LEN];
  baseFields(base, sizeof(base));
  snprintf(body, sizeof(body),
           "{%s,\"event\":\"LOW_BATTERY\",\"note\":\"dropped to %s at %d mV\"}",
           base, state, mv);
  sendOrQueue("/api/event", body);
  Serial.printf("[evt] LOW_BATTERY sent (%s)\n", state);
}

// Fakes a ball pass. Note the ordering: we work out dt and speed from the
// node's own micros() clock BEFORE transmitting. That is exactly how the real
// firmware will behave in Step 3, which is why Wi-Fi latency can never affect
// a velocity measurement.
void sendBall() {
  uint32_t t_a = micros();
  uint32_t dt  = 40000 + (esp_random() % 90000);   // 40-130 ms, a plausible ball
  uint32_t t_b = t_a + dt;
  float speed  = (GAP_MM / 1000.0f) / (dt / 1000000.0f);

  char base[256], body[QUEUE_BODY_LEN];
  baseFields(base, sizeof(base));
  snprintf(body, sizeof(body),
    "{%s,\"event\":\"BALL_PASS\",\"t_a_us\":%lu,\"t_b_us\":%lu,\"dt_us\":%lu,"
    "\"gap_mm\":%.1f,\"speed_mps\":%.4f}",
    base, (unsigned long)t_a, (unsigned long)t_b, (unsigned long)dt, GAP_MM, speed);

  sendOrQueue("/api/event", body);
  Serial.printf("[evt] BALL_PASS  dt=%.1f ms  speed=%.3f m/s\n", dt / 1000.0, speed);
}

/* ------------------------------------------------------------------ main --- */

void setup() {
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  // No INPUT_PULLUP here: the 10k pull-DOWN on the board sets the idle level.
  // An internal pull-up would fight it and hold the pin high permanently,
  // which looks exactly like a beam that never triggers.
  pinMode(PIN_BEAM_A, INPUT);
  pinMode(PIN_BEAM_B, INPUT);

  Serial.begin(115200);
  delay(400);

  Serial.println();
  Serial.println("=====================================");
  Serial.println(" TASL node - network + battery");
  Serial.printf ("  node id : %s\n", NODE_ID);
  Serial.printf ("  firmware: %s\n", FW_VERSION);
  Serial.println("=====================================");
  Serial.println("Press the BOOT button to send a test ball.");
  Serial.println();

#if BEAM_ALIGN
  analogSetPinAttenuation(PIN_BEAM_A, ADC_11db);
  analogSetPinAttenuation(PIN_BEAM_B, ADC_11db);
  Serial.println("[beam] ALIGNMENT MODE - aim each beam until CLEAR reads 'good',");
  Serial.println("       then set BEAM_ALIGN 0 before building stage 5.");
#endif

#if BATT_ENABLED
  // 12-bit resolution (0-4095) and 11 dB attenuation, which puts the usable
  // input range at roughly 0-3.1 V. A full 4.2 V pack lands at 2.1 V through
  // the halving divider, comfortably inside that.
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_BATTERY, ADC_11db);

  // Take a reading before the radio comes up, so the very first heartbeat
  // already carries a battery level instead of UNKNOWN.
  sampleBattery();
  printBattery();
#else
  Serial.println("[batt] BATT_ENABLED is 0 - reporting UNKNOWN");
#endif

  connectWiFi();
  sendBoot();
  g_lastHeartbeat = millis();
}

void loop() {
  unsigned long now = millis();

  // Battery is sampled even while Wi-Fi is down. A node that cannot reach the
  // laptop is exactly the node you most want a voltage from when it reconnects.
#if BATT_ENABLED
  if (now - g_lastBattSample >= BATT_SAMPLE_MS) {
    g_lastBattSample = now;
    sampleBattery();
  }
  if (now - g_lastBattPrint >= BATT_PRINT_MS) {
    g_lastBattPrint = now;
    printBattery();
  }
#endif

  // Printed before the Wi-Fi guard below, so you can still align beams on a
  // bench with no router in range.
#if BEAM_ALIGN
  if (now - g_lastBeamPrint >= BEAM_PRINT_MS) {
    g_lastBeamPrint = now;
    printBeams();
  }
#endif

  // Reconnect if Wi-Fi drops. Nothing else can work until this does.
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(PIN_LED, (now / 150) % 2);
    if (now - g_lastWifiTry > WIFI_RETRY_MS) {
      g_lastWifiTry = now;
      Serial.println("[wifi] disconnected - retrying");
      WiFi.disconnect();
      connectWiFi();
    }
    return;
  }

  if (now - g_lastHeartbeat >= HEARTBEAT_MS) {
    g_lastHeartbeat = now;
    drainQueue();
    sendHeartbeat();
  }

  // BOOT button pulls GPIO0 to ground. Safe to read as a normal input once the
  // chip has finished booting.
  if (digitalRead(PIN_BUTTON) == LOW && now - g_lastButton > DEBOUNCE_MS) {
    g_lastButton = now;
    sendBall();
  }

  if (AUTO_BALL_MS > 0 && now - g_lastAutoBall >= AUTO_BALL_MS) {
    g_lastAutoBall = now;
    sendBall();
  }

  delay(10);
}
