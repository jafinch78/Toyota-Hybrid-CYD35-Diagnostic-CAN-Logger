// Reference TFT_eSPI User_Setup.h for the CYD 3.5-inch boards in this release.
// Copy these definitions into the active TFT_eSPI User_Setup.h. Do not place
// this file beside the .ino as another Arduino sketch tab.
#define USER_SETUP_LOADED
#define USER_SETUP_INFO "CYD35_E32R35T_ST7796_XPT2046"

#define ST7796_DRIVER
#define TFT_MISO 12
#define TFT_MOSI 13
#define TFT_SCLK 14
#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST  -1
#define TFT_BL   27
#define TOUCH_CS 33

#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4
#define LOAD_FONT6
#define LOAD_FONT7
#define LOAD_FONT8
#define SMOOTH_FONT

#define SPI_FREQUENCY        80000000
#define SPI_READ_FREQUENCY   20000000
#define SPI_TOUCH_FREQUENCY   2500000
