// BLE HID mouse test for the iPad Control Bridge.
// Pair "iPad Control Bridge" in iPad Settings > Bluetooth, then send commands
// through the USB serial port at 115200 baud.

#include <ESP32BLECombo.h>

ESP32BLECombo ble;

void setup() {
    Serial.begin(115200);
    delay(500);

    ESP32BLEComboConfig config;
    config.mode = ESP32BLEComboMode::KEYBOARD_MOUSE;
    config.deviceName = "iPad Control Bridge";
    config.manufacturer = "ipad-control-bridge";
    config.batteryLevel = 100;
    // Let the HID descriptor advertise the combined keyboard/mouse role.
    config.appearance = ESP32BLEComboAppearance::AUTO;

    ble.begin(config);

    Serial.println("BLE mouse ready");
    Serial.println("Pair: iPad Settings > Bluetooth > iPad Control Bridge");
    Serial.println("Commands: /move x,y  /click left  /scroll n  /home  /status");
}

void loop() {
    if (!Serial.available()) {
        delay(5);
        return;
    }

    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "/status") {
        Serial.println(ble.isConnected() ? "BLE connected" : "BLE advertising / not connected");
        return;
    }

    if (command == "/home") {
        // iPadOS external-keyboard shortcut: Command + H = Home Screen.
        // 0x83 is the library's GUI modifier (128 + modifier bit 3).
        ble.press(0x83);
        ble.press('h');
        delay(40);
        ble.release('h');
        ble.release(0x83);
        ble.releaseAll();
        Serial.println("home shortcut sent");
        return;
    }

    if (!ble.isConnected()) {
        Serial.println("BLE not connected; pair the iPad first");
        return;
    }

    if (command.startsWith("/move ")) {
        String args = command.substring(6);
        int comma = args.indexOf(',');
        if (comma < 0) {
            Serial.println("Usage: /move x,y");
            return;
        }
        int x = args.substring(0, comma).toInt();
        int y = args.substring(comma + 1).toInt();
        ble.mouseMove(x, y);
        Serial.println("moved");
        return;
    }

    if (command == "/click left") {
        ble.mouseClick(ESP32BLECombo::MOUSE_LEFT);
        Serial.println("left click");
        return;
    }

    if (command == "/down left") {
        ble.mousePress(ESP32BLECombo::MOUSE_LEFT);
        Serial.println("left down");
        return;
    }

    if (command == "/up left") {
        ble.mouseRelease(ESP32BLECombo::MOUSE_LEFT);
        Serial.println("left up");
        return;
    }

    if (command.startsWith("/scroll ")) {
        ble.mouseScroll(command.substring(8).toInt());
        Serial.println("scrolled");
        return;
    }

    Serial.println("Unknown command");
}
