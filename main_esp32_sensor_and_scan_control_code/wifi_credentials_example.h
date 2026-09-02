// Copy this file to wifi_credentials.h and edit it.
//
// wifi_credentials.h is in .gitignore. Do not remove it from there, and do not
// put a real password in this example file.

#ifndef WIFI_CREDENTIALS_H
#define WIFI_CREDENTIALS_H

// The network the laptop is on. Usually the laptop's own hotspot, so the robot
// works in a hall with no usable Wi-Fi.
static const char *WIFI_NAME = "ASIL_DEMO";
static const char *WIFI_PASSWORD = "change-me";

// Where the laptop server is listening. On a Windows hotspot the laptop is
// usually 192.168.137.1. Check with ipconfig.
static const char *LAPTOP_ADDRESS = "http://192.168.137.1:8000";

// Optional shared word. It has to match robot_shared_key in settings.json.
// Leave both empty to turn the check off, which is fine on a private hotspot.
static const char *ROBOT_SHARED_KEY = "";

#endif  // WIFI_CREDENTIALS_H
