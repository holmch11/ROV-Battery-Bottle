/**************************************************************************
  This sketch uses and ESP32-S2 Chip on a Adafruit Feather with an integrated
  BME280 Sensor https://www.adafruit.com/product/5303

  The BME280 Sensor provides temperature, pressure, and humidity data

  The data is output to a 2.13" Mono SSD1680 Feather eink display
  https://www.adafruit.com/product/4195

  The device is generally in low power sleep mode, but can be triggered to output a reading with 
  a hall effect sensor and magnet outside the pressure case.
  https://www.adafruit.com/product/158

  Written by Christopher Holm for Oregon State University Robotics holmch@oregonstate.edu
  
  MIT license, all text above must be included in any redistribution
 *****************************************************************************
 Revision History
 2022-12-14 0.0.0 Intial Version CEH
 
 **************************************************************************/
// Required Libraries
#include <Adafruit_GFX.h>    // Core graphics library
#include "Adafruit_ThinkInk.h" // E-ink Library
#include <Adafruit_BME280.h> //Integrated BME280 Sensor for Temp,pressure, humidity on 0x77
#include <Adafruit_Sensor.h> //Generic Sensor Library
#include <Wire.h>
#include <SPI.h>


// Define Constants 
#define hallpinBitmask 0x1000 // 2^12 in hex
#define EPD_CS      9
#define EPD_DC      10
#define SRAM_CS     6
#define EPD_RESET   -1
#define EPD_BUSY    -1
#define vacPresure (800.00)


// 2.13" Monochrome displays with 250x122 pixels and SSD1680 chipset
ThinkInk_213_Mono_BN display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

Adafruit_BME280 bme;  //I2C to turn off PIN_I2C_POWER

// Define Variables
int i = 0;
int hallPin = 12;
int hallValue = 0;
int battVoltPin = A1;
int ampPin = A0;
float temp = 0.00;
   
float pressure = 0.00;
float humidity = 0.00;
float battVoltage = 0.00;
float battAmp = 0.00;
float battAmpTotal = 0.00;
int battStatus = 0;
RTC_DATA_ATTR int bootCount = 0;

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

void print_wakeup_reason(){
  esp_sleep_wakeup_cause_t wakeup_reason;

  wakeup_reason = esp_sleep_get_wakeup_cause();

  switch(wakeup_reason)
  {
    case ESP_SLEEP_WAKEUP_EXT0 : Serial.println("Wakeup caused by external signal using RTC_IO"); break;
    case ESP_SLEEP_WAKEUP_EXT1 : Serial.println("Wakeup caused by external signal using RTC_CNTL"); break;
    case ESP_SLEEP_WAKEUP_TIMER : Serial.println("Wakeup caused by timer"); break;
    case ESP_SLEEP_WAKEUP_TOUCHPAD : Serial.println("Wakeup caused by touchpad"); break;
    case ESP_SLEEP_WAKEUP_ULP : Serial.println("Wakeup caused by ULP program"); break;
    default : Serial.printf("Wakeup was not caused by deep sleep: %d\n",wakeup_reason); break;
  }
}
  
// Setup Function***********************************************************************************
void setup(void) {
  unsigned status;
  Serial.begin(115200);
  while (!Serial) { delay(10);}
  Serial.println("Adafruit EPD update test in mono");
  display.begin(THINKINK_MONO);
  Serial.println(F("BME280 test"));
  status = bme.begin();
  delay(100);
  
  //Increment boot number and print it every reboot
  ++bootCount;
  Serial.println("Boot number: "+ String(bootCount));

  //Print the wakeup reason for ESP32
  print_wakeup_reason();
  
  uint16_t time = millis();
  time = millis() - time;
  
  Serial.println(time, DEC);
  delay(1000);

  Serial.println("done");

  
}
//MAIN LOOP ***********************************************************************************

void loop() {
  hallValue = analogRead(hallPin);
  Serial.println (hallValue);
  //  display.clearBuffer();
  //  display.setTextSize(2);
  //  display.setCursor(25,25);
  //  display.setTextColor(EPD_BLACK);
  //  display.print(hallValue);
  //  display.setCursor(25,50);
  //  display.print("Temperature°C: ");
  //  display.setCursor(50,50);
  //  display.print(bme.readTemperature());
  //  display.setCursor(25,75);
  //  display.print("Pressure hPa: ");
  //  display.setCursor(50,75);
  //  display.print(bme.readPressure() / 100.0F);
  //  display.setCursor(25,100);
  //  display.print("Humidity %RH: ");  
  //  display.setCursor(50,100);
  //  display.print(bme.readHumidity()); 
  printBME();
  esp_sleep_enable_ext1_wakeup(hallpinBitmask,ESP_EXT1_WAKEUP_ANY_LOW);
  Serial.println("Going to sleep now");
  esp_deep_sleep_start();
}
