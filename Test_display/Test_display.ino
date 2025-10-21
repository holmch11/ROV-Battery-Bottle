#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_ThinkInk.h>

#define SEALEVELPRESSURE_HPA (1013.25)

#define EPD_DC 10
#define EPD_CS 9
#define EPD_BUSY 7 // can set to -1 to not use a pin (will wait a fixed delay)
#define SRAM_CS 6
#define EPD_RESET 8  // can set to -1 and share with microcontroller Reset!
#define EPD_SPI &SPI // primary SPI


// 2.9" Monochrome displays with 296x128 pixels and UC8151D chipset
ThinkInk_290_Mono_M06 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);
Adafruit_BME280 bme;  // I2C to turn off PIN_I2C_POWER

int currentLine = 0;
const int maxLines = 15; // Adjust this value based on your eInk display size
const int pin12 = 12;

void setup() {
  Serial.begin(115200);

  display.begin(THINKINK_MONO);
  display.clearDisplay();
  pinMode(pin12, INPUT_PULLDOWN);
}

void loop() {
  if (digitalRead(pin12) == HIGH) {
    float temp = bme.readTemperature();
    float hum = bme.readHumidity();
    float pres = bme.readPressure() / 100.0F;
    Serial.print("Pressure: "); Serial.print(pres); Serial.println(" hPa");
    Serial.println("sending info to display");
    display.setCursor(0, currentLine * 15);
    display.print("Temp: "); display.print(temp); display.println(" *C");
    display.print("Hum: "); display.print(hum); display.println(" %");
    display.print("Pres: "); display.print(pres); display.println(" hPa");
    display.display();

    currentLine++;
    if (currentLine >= maxLines) {
      currentLine = 0;
      display.clearDisplay();
    }

    delay(2000); // Debounce delay
  }
}
