/* ============================================================================
   TEMPLATE - copy this to secrets.h and fill in your own values.

       cp secrets.example.h secrets.h

   secrets.h is gitignored. This template is committed so anyone cloning the
   repo knows what they need to supply.
   ========================================================================= */

#ifndef TASL_SECRETS_H
#define TASL_SECRETS_H

// Your 2.4 GHz network. The ESP32 cannot see 5 GHz networks at all - a 5 GHz
// SSID will never connect no matter what you type. SSIDs are case sensitive.
#define TASL_WIFI_SSID  "YOUR_2.4GHZ_SSID"
#define TASL_WIFI_PASS  "YOUR_WIFI_PASSWORD"

// The laptop running the dashboard, on the LAN.
// Find it with 'ipconfig' (Windows) or 'ipconfig getifaddr en0' (macOS).
// If this changes, every node goes silent - set a DHCP reservation.
#define TASL_SERVER_IP  "192.168.1.35"

#endif
