// Copy this file to wifi_credentials.h and edit it.
//
// wifi_credentials.h is in .gitignore. Do not remove it from there, and do not
// put a real password in this example file.
//
// Both ESP boards need their own copy, and both must join the SAME network as
// the laptop.

#ifndef WIFI_CREDENTIALS_H
#define WIFI_CREDENTIALS_H

static const char *WIFI_NAME = "ASIL_DEMO";
static const char *WIFI_PASSWORD = "change-me";

// Where the laptop server is listening. On a Windows hotspot the laptop is
// usually 192.168.137.1. Check with ipconfig.
static const char *LAPTOP_ADDRESS = "http://192.168.137.1:8000";

// Must match robot_shared_key in settings.json and the same value on the main
// ESP32. Leave all of them empty to turn the check off.
static const char *ROBOT_SHARED_KEY = "";

#endif  // WIFI_CREDENTIALS_H
