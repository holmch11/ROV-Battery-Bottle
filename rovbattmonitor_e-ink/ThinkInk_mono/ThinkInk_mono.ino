/***************************************************
  Adafruit invests time and resources providing this open source code,
  please support Adafruit and open-source hardware by purchasing
  products from Adafruit!

  Written by Limor Fried/Ladyada for Adafruit Industries.
  MIT license, all text above must be included in any redistribution
 ****************************************************/

#include "Adafruit_ThinkInk.h"

#define EPD_CS      9
#define EPD_DC      10
#define SRAM_CS     6
#define EPD_RESET   -1 // can set to -1 and share with microcontroller Reset!
#define EPD_BUSY    -1 // can set to -1 to not use a pin (will wait a fixed delay)

// 1.54" Monochrome displays with 200x200 pixels and SSD1681 chipset
//ThinkInk_154_Mono_D67 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

// 1.54" Monochrome displays with 200x200 pixels and SSD1608 chipset
//ThinkInk_154_Mono_D27 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

// 1.54" Monochrome displays with 152x152 pixels and UC8151D chipset
//ThinkInk_154_Mono_M10 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);


// 2.13" Monochrome displays with 250x122 pixels and SSD1675 chipset
//ThinkInk_213_Mono_B72 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

// 2.13" Monochrome displays with 250x122 pixels and SSD1675B chipset
//ThinkInk_213_Mono_B73 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

// 2.13" Monochrome displays with 250x122 pixels and SSD1680 chipset
ThinkInk_213_Mono_BN display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);
//ThinkInk_213_Mono_B74 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

// 2.13" Monochrome displays with 212x104 pixels and UC8151D chipset
//ThinkInk_213_Mono_M21 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);


// 2.9" 4-level Grayscale (use mono) displays with 296x128 pixels and IL0373 chipset
//ThinkInk_290_Grayscale4_T5 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

// 2.9" Monochrome displays with 296x128 pixels and UC8151D chipset
//ThinkInk_290_Mono_M06 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);


// 4.2" Monochrome displays with 400x300 pixels and SSD1619 chipset
//ThinkInk_420_Mono_BN display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);

// 4.2" Monochrome displays with 400x300 pixels and UC8276 chipset
//ThinkInk_420_Mono_M06 display(EPD_DC, EPD_RESET, EPD_CS, SRAM_CS, EPD_BUSY);


void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  Serial.println("Adafruit EPD full update test in mono");
  display.begin(THINKINK_MONO);
}

void loop() {
  Serial.println("Banner demo");
  display.clearBuffer();
  display.setTextSize(3);
  display.setCursor((display.width() - 180)/2, (display.height() - 24)/2);
  display.setTextColor(EPD_BLACK);
  display.print("Monochrome");
  display.display();

  delay(2000);
  
  Serial.println("B/W rectangle demo");
  display.clearBuffer();
  display.fillRect(display.width()/2, 0, display.width()/2, display.height(), EPD_BLACK);
  display.display();

  delay(2000);
  
  Serial.println("Text demo");
  // large block of text
  display.clearBuffer();
  display.setTextSize(1);
  testdrawtext("Lorem ipsum dolor sit amet, consectetur adipiscing elit. Curabitur adipiscing ante sed nibh tincidunt feugiat. Maecenas enim massa, fringilla sed malesuada et, malesuada sit amet turpis. Sed porttitor neque ut ante pretium vitae malesuada nunc bibendum. Nullam aliquet ultrices massa eu hendrerit. Ut sed nisi lorem. In vestibulum purus a tortor imperdiet posuere. ", EPD_BLACK);
  display.display();

  delay(2000);

  display.clearBuffer();
  for (int16_t i=0; i<display.width(); i+=4) {
    display.drawLine(0, 0, i, display.height()-1, EPD_BLACK);
  }

  for (int16_t i=0; i<display.height(); i+=4) {
    display.drawLine(display.width()-1, 0, 0, i, EPD_BLACK);
  }
  display.display();

  delay(2000);  
}


void testdrawtext(const char *text, uint16_t color) {
  display.setCursor(0, 0);
  display.setTextColor(color);
  display.setTextWrap(true);
  display.print(text);
}
