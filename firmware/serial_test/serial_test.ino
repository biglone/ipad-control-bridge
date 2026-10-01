// First hardware check for the XIAO ESP32-S3.
// Upload this before adding BLE HID control.

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("ipad-control-bridge: serial link OK");
}

void loop() {
    if (Serial.available() > 0) {
        const String command = Serial.readStringUntil('\n');
        Serial.print("received: ");
        Serial.println(command);
    }
    delay(10);
}
