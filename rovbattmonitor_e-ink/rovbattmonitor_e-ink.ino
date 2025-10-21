/**************************************************************************
  This sketch uses and ESP32-S2 Chip on a Adafruit Feather with an integrated
  BME280 Sensor https://www.adafruit.com/product/5303

  The BME280 Sensor provides temperature, pressure, and humidity data

  The data is output to a 2.9" Mono M06 flexible Feather eink display
  https://www.adafruit.com/product/4262

  The device is generally in low power sleep mode, but can be triggered to output a reading with 
  a hall effect sensor and magnet outside the pressure case.

  Written by Christopher Holm for Oregon State University Robotics holmch@oregonstate.edu
  
  MIT license, all text above must be included in any redistribution
 *****************************************************************************
 Revision History
 2024-05-20 0.0.0 Intial Version CEH
 
 **************************************************************************/
#include <Adafruit_GFX.h>    // Core graphics library
#include "Adafruit_ThinkInk.h" // E-ink Library
#include <Adafruit_BME280.h> // Integrated BME280 Sensor for Temp, pressure, humidity on 0x77
#include <Adafruit_Sensor.h> // Generic Sensor Library
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <sd_defines.h>
#include <sd_diskio.h>// SD card library

// Define Constants
#define MAG_PIN 12  // Digital pin connected to the magnetic reed switch
#define EPD_CS      9
#define EPD_DC      10
#define SRAM_CS     6
#define EPD_RESET   -1
#define EPD_BUSY    -1
#define VAC_PRESSURE 800.00
#define VOLTAGE_DIVIDER 4.98
#define SD_CS 5 // SD card chip select pin (adjust based on your wiring)
#define CURRENT_DIVIDER 1
#define MV_PER_AMP 53.33
#define UPDATE_INTERVAL 240 // 240 seconds

// 2.9" Monochrome displays with 296x128 pixels and UC8151D chipset
ThinkInk_290_Mono_M06 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);
Adafruit_BME280 bme;  // I2C to turn off PIN_I2C_POWER

// Define Variables
int battVoltPin = A1;
int currentPin = A0;
float temp = 0.00;
float pressure = 0.00;
float humidity = 0.00;
float battVoltage = 0.00;
float current = 0.00;
float coulombs = 0.00;
float battCapacity = 15600.0; // Example battery capacity in mAh
RTC_DATA_ATTR int bootCount = 0;
RTC_DATA_ATTR unsigned long lastUpdate = 0;
RTC_DATA_ATTR bool SwitchTriggered = false;
File dataFile;

// Function Definitions
void printBME() {
  Serial.print("Temperature = ");
  Serial.print(bme.readTemperature());
  Serial.println(" °C");
  
  Serial.print("Pressure = ");
  Serial.print(bme.readPressure() / 100.0F);
  Serial.println(" hPa");

  Serial.print("Humidity = ");
  Serial.print(bme.readHumidity());
  Serial.println(" %");

  Serial.println();
}

void print_wakeup_reason() {
  esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();

  switch (wakeup_reason) {
    case ESP_SLEEP_WAKEUP_EXT0 : Serial.println("Wakeup caused by external signal using RTC_IO"); break;
    case ESP_SLEEP_WAKEUP_EXT1 : Serial.println("Wakeup caused by external signal using RTC_CNTL"); break;
    case ESP_SLEEP_WAKEUP_TIMER : Serial.println("Wakeup caused by timer"); break;
    case ESP_SLEEP_WAKEUP_TOUCHPAD : Serial.println("Wakeup caused by touchpad"); break;
    case ESP_SLEEP_WAKEUP_ULP : Serial.println("Wakeup caused by ULP program"); break;
    default : Serial.printf("Wakeup was not caused by deep sleep: %d\n", wakeup_reason); break;
  }
}

void setup() {
  unsigned status;
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  Serial.println("Adafruit EPD update test in mono");
  display.begin(THINKINK_MONO);
  Serial.println(F("BME280 test"));
  status = bme.begin();
  delay(100);

  // Increment boot number and print it every reboot
  ++bootCount;
  Serial.println("Boot number: " + String(bootCount));

  // Print the wakeup reason for ESP32
  print_wakeup_reason();

  uint16_t time = millis();
  time = millis() - time;

  Serial.println(time, DEC);
  delay(1000);

  Serial.println("done");

  // Set reed switch pin mode
  pinMode(MAG_PIN, INPUT_PULLDOWN);

  // Initialize SD card
  if (!SD.begin(SD_CS)) {
    Serial.println("Card failed, or not present");
    return; // don't do anything more if SD card initialization failed
  }
  Serial.println("SD card initialized.");

  // Open the file. Note that only one file can be open at a time,
  // so you have to close this one before opening another.
  dataFile = SD.open("data.csv", FILE_WRITE);
  // If the file opened okay, write to it:
  if (dataFile) {
    // Write header if the file is new
    if (dataFile.size() == 0) {
      dataFile.println("Temperature,Pressure,Humidity,Battery Voltage,Current,Battery Used (%)");
    }
    dataFile.close();
  }
}

// Function to read battery voltage
float readBatteryVoltage() {
  int sensorValue = analogRead(battVoltPin);
  float voltage = sensorValue * (3.3 / 1023.0);
  return voltage * VOLTAGE_DIVIDER;
}

// Function to read current from ACS770 sensor
float readCurrent() {
  int sensorValue = analogRead(currentPin);
  float voltage = sensorValue * (3.3 / 1023.0);
  voltage = voltage * CURRENT_DIVIDER;
  return voltage / MV_PER_AMP;
}

// Function to update and display sensor data
void updateDisplay() {
  // Read sensor data
  battVoltage = readBatteryVoltage();
  temp = bme.readTemperature();
  pressure = bme.readPressure() / 100.0F;
  humidity = bme.readHumidity();
  current = readCurrent();

  // Calculate coulombs based on current
  // Assuming loop runs every second (1 Hz), so current in Amps directly gives coulombs
  coulombs += current;

  float batteryUsedPercentage = (coulombs / (battCapacity * 3.6)) * 100.0; // mAh to coulombs

  // Clear and update display
  display.clearBuffer();
  display.setTextSize(2);
  display.setCursor(25, 25);
  display.setTextColor(EPD_BLACK);
  display.print("Temperature: ");
  display.setCursor(25, 50);
  display.print(temp);
  display.print(" °C");
  display.setCursor(25, 75);
  display.print("Pressure: ");
  display.setCursor(50, 75);
  display.print(pressure);
  display.print(" hPa");
  display.setCursor(25, 100);
  display.print("Humidity: ");
  display.setCursor(50, 100);
  display.print(humidity);
  display.print(" %");
  display.setCursor(25, 125);
  display.print("Battery V: ");
  display.setCursor(50, 125);
  display.print(battVoltage);
  display.print(" V");
  display.setCursor(25, 150);
  display.print("Current: ");
  display.setCursor(50, 150);
  display.print(current);
  display.print(" A");
  display.setCursor(25, 175);
  display.print("Battery used: ");
  display.setCursor(50, 175);
  display.print(batteryUsedPercentage);
  display.print(" %");

  display.display(); // Update display
  printBME();

  // Log data to SD card
  dataFile = SD.open("data.csv", FILE_WRITE);
  if (dataFile) {
    dataFile.print(temp);
    dataFile.print(",");
    dataFile.print(pressure);
    dataFile.print(",");
    dataFile.print(humidity);
    dataFile.print(",");
    dataFile.print(battVoltage);
    dataFile.print(",");
    dataFile.print(current);
    dataFile.print(",");
    dataFile.println(batteryUsedPercentage);
    dataFile.close();
    Serial.println("Data logged to SD card.");
  } else {
    Serial.println("Error opening data.csv for writing.");
  }
}

void loop() {
  unsigned long currentTime = millis() / 1000; // Convert to seconds

  // Read current value
  current = readCurrent();

  // If reed switch is triggered, update display and log data, then go to sleep
  if (digitalRead(MAG_PIN) == HIGH) {
    SwitchTriggered = true;
    updateDisplay();
    esp_sleep_enable_ext0_wakeup(GPIO_NUM_12, 0); // Wake up when reed switch is closed (LOW)
    Serial.println("Going to sleep now");
    delay(1000); // Short delay before sleep to ensure serial print is complete
    esp_deep_sleep_start();
  }

  // If current is flowing, stay awake and measure current at 1 Hz
  if (current > 0.8) {
    coulombs += current; // Accumulate coulombs

    // Check if it's time to update the display
    if (currentTime - lastUpdate >= UPDATE_INTERVAL) {
      updateDisplay();
      lastUpdate = currentTime;
    }

    delay(1000); // Measure current at 1 Hz
  } else {
    // No current flowing, go to deep sleep
    esp_sleep_enable_ext0_wakeup(GPIO_NUM_12, 1); // Wake up when reed switch is closed (HIGH)
    Serial.println("No current flowing, going to sleep now");
  }
}
