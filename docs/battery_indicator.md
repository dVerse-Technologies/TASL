I am building a battery-powered ESP32 sensor node for a modular marble-run engineering challenge.

I want you to design ONLY the electronics/power subsystem described below. Do not redesign the physical marble-run.

NODE
Each sensor node contains:
- ESP32-WROOM-32-class development board
- 1S LiPo battery
- approximately 3.7 V nominal, 500 mAh
- IR LED + IR phototransistor sensor
- 5 mm 4-pin RGB LED
- Wi-Fi connectivity
- power ON/OFF switch.

The node is enclosed in a small 3D-printed PETG enclosure.

POWER REQUIREMENTS
The LiPo should:
- power the ESP32 safely
- be rechargeable
- have appropriate protection
- be replaceable if necessary.

I want an onboard charging solution.

Please design a practical circuit using inexpensive, readily available modules/components in India.

IMPORTANT:
I am considering TP4056-based charging/protection boards, but evaluate whether that is appropriate for this ESP32/LiPo architecture.

I need to know:
1. Exact power architecture from LiPo → ESP32.
2. Whether the ESP32 can be powered directly from the LiPo.
3. Whether a 3.3 V regulator is required.
4. Whether the ESP32 development board's 5V/VIN input is appropriate.
5. Whether a boost/buck/boost-buck regulator is necessary.
6. How to safely charge the LiPo.
7. How to protect against overcharge, over-discharge and short circuit.
8. Recommended charging current for a 500 mAh cell.
9. Whether charging should be possible while the node is switched off.
10. Recommended connector between battery and PCB.
11. Recommended ON/OFF switch location.

BATTERY MONITORING
I want the ESP32 to measure LiPo voltage.

Design the voltage measurement circuit, including:
- resistor divider values
- ADC pin recommendation for ESP32-WROOM-32
- whether ADC1 should be used instead of ADC2 because Wi-Fi is active
- filtering capacitor if necessary
- maximum safe ADC voltage
- calibration considerations.

RGB LED
I have 5 mm, 4-pin RGB LEDs.

Preferred type:
- common cathode
- through-hole
- diffused

Common anode is also acceptable if necessary.

The RGB LED should indicate battery state:

GREEN = battery healthy
YELLOW = battery getting low
RED = battery low
FLASHING RED = critically low

Recommend practical voltage thresholds for a 1S LiPo under ESP32 load.

Do NOT pretend LiPo voltage maps linearly to battery percentage. I primarily need a reliable "OK / low / recharge" indication.

Design the LED circuit with appropriate current-limiting resistors.

I want to understand:
- how many GPIOs are needed
- resistor values
- common cathode vs common anode wiring
- whether PWM is necessary
- whether yellow can be created by red+green simultaneously.

LED CURRENT
Keep LED current modest because this is a battery-powered node.

Recommend sensible LED currents rather than simply using 20 mA per colour.

PERFBOARD
The final prototype will be soldered on perfboard.

Provide:
1. Schematic-level wiring description
2. Exact component list/BOM for ONE node
3. Suggested values
4. Wiring diagram in ASCII
5. Charging safety notes
6. ESP32 firmware logic/pseudocode for battery measurement and RGB status
7. Recommended PCB/perfboard layout
8. Common mistakes to avoid.

Assume the builder is technically capable but is not an electronics specialist, so explain important decisions clearly.

Optimize for:
- safety
- reliability
- low cost
- easy sourcing in India
- repeatability across approximately 20 nodes.