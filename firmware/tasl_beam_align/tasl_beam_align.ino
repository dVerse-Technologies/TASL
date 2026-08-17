/* ============================================================================
   TASL - IR BEAM ALIGNMENT / BREAK TEST
   Board: ESP32 DevKit V1

   Standalone bench tool. No Wi-Fi, no battery, no dashboard.
   Flash it, open Serial Monitor at 115200, break the beam.

   Wiring per beam:
     3V3 --[220R]--> IR emitter --> GND        (long leg = anode)
     3V3 ----------- phototransistor collector
                     emitter --+-- [10k] -- GND
                               +-- GPIO

   Beam clear   -> phototransistor conducts -> pin HIGH
   Beam blocked -> phototransistor off      -> 10k pulls it LOW
   ========================================================================= */

#define BEAMS         1      // 1 or 2

#define PIN_BEAM_A    19
#define PIN_BEAM_B    18

// Set to 1 ONLY if the pin above is ADC1 (GPIO32-39). Gives a raw 0-4095
// level, which is better for fine aiming. Any other pin must stay at 0.
#define BEAM_ANALOG   0

#define PRINT_MS      500

int  breaksA = 0, breaksB = 0;
bool lastA = true, lastB = true;
int  rawMinA = 4095, rawMaxA = 0;
int  rawMinB = 4095, rawMaxB = 0;

void setup() {
  Serial.begin(115200);
  delay(400);

  // No INPUT_PULLUP: the 10k pull-down sets the idle level. An internal
  // pull-up would fight it and hold the pin high permanently, which looks
  // exactly like a beam that never triggers.
  pinMode(PIN_BEAM_A, INPUT);
#if BEAMS > 1
  pinMode(PIN_BEAM_B, INPUT);
#endif

#if BEAM_ANALOG
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_BEAM_A, ADC_11db);
  #if BEAMS > 1
    analogSetPinAttenuation(PIN_BEAM_B, ADC_11db);
  #endif
#endif

  Serial.println();
  Serial.println("=============================");
  Serial.println(" TASL beam break test");
  Serial.printf ("  beam A on GPIO%d\n", PIN_BEAM_A);
#if BEAMS > 1
  Serial.printf ("  beam B on GPIO%d\n", PIN_BEAM_B);
#endif
  Serial.println("=============================");
  Serial.println("Put a finger through the beam.");
  Serial.println("Send 'r' to reset counters.");
  Serial.println();
}

// Reports one beam. Prints a line on every state CHANGE (that is the thing
// you are testing), plus a periodic status line so you can see it is alive.
void checkBeam(const char* name, uint8_t pin, bool& last, int& breaks,
               int& rawMin, int& rawMax) {
  bool clear;
  int  raw = -1;

#if BEAM_ANALOG
  uint32_t sum = 0;
  for (int i = 0; i < 8; i++) { sum += analogRead(pin); delayMicroseconds(200); }
  raw   = sum / 8;
  clear = raw > 2048;
  if (raw < rawMin) rawMin = raw;
  if (raw > rawMax) rawMax = raw;
#else
  clear = digitalRead(pin) == HIGH;
#endif

  if (clear != last) {
    last = clear;
    if (!clear) {
      breaks++;
      Serial.printf(">>> beam %s BROKEN   (break #%d)\n", name, breaks);
    } else {
      Serial.printf("    beam %s clear\n", name);
    }
  }
}

void status(const char* name, uint8_t pin, int breaks, int rawMin, int rawMax) {
#if BEAM_ANALOG
  int span = rawMax - rawMin;
  Serial.printf("beam %s: %-7s raw range %4d..%4d span=%4d  breaks=%d\n",
                name, digitalRead(pin) ? "CLEAR" : "BLOCKED",
                rawMin, rawMax, span, breaks);
#else
  Serial.printf("beam %s: %-7s  breaks=%d\n",
                name, digitalRead(pin) == HIGH ? "CLEAR" : "BLOCKED", breaks);
#endif
}

unsigned long lastPrint = 0;

void loop() {
  if (Serial.available() && Serial.read() == 'r') {
    breaksA = breaksB = 0;
    rawMinA = rawMinB = 4095;
    rawMaxA = rawMaxB = 0;
    Serial.println("-- counters reset --");
  }

  // Polled fast so a quick hand wave is not missed.
  checkBeam("A", PIN_BEAM_A, lastA, breaksA, rawMinA, rawMaxA);
#if BEAMS > 1
  checkBeam("B", PIN_BEAM_B, lastB, breaksB, rawMinB, rawMaxB);
#endif

  unsigned long now = millis();
  if (now - lastPrint >= PRINT_MS) {
    lastPrint = now;
    status("A", PIN_BEAM_A, breaksA, rawMinA, rawMaxA);
#if BEAMS > 1
    status("B", PIN_BEAM_B, breaksB, rawMinB, rawMaxB);
#endif
  }

  delay(2);
}
