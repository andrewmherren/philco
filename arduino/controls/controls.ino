#define UART Serial1
//#include <Adafruit_NeoPixel.h>
#include <avr/power.h>

//setup pins
int vol = PIN_F0; //volume potentiometer
int multi1_0 = PIN_F1; //multi switch 1
int multi1_1 = PIN_F4;
int multi1_2 = PIN_F5;
int multi1_3 = PIN_F6;
int multi1_4 = PIN_F7;
int multi1_5 = PIN_B6;
int multi2 = PIN_B5; //multi switch 2
int station = PIN_B4; //station potentimeter
//int NEO = PIN_D7;
int LED = PIN_D6;
int LS_OE = PIN_D5; //level shifter for uart
int LS_GND = PIN_C7;
int LS_5V = PIN_D0;

//Adafruit_NeoPixel RGB_LED = Adafruit_NeoPixel(2, NEO, NEO_RGB + NEO_KHZ800);

long multi1_old = -1;
int multi2_old = -1;

String content = "";
int rgb[] = {0, 0, 0};
int color = 0;
char character;

void setup() {

  //RGB_LED.begin();
  //RGB_LED.setPixelColor(0, rgb[0], rgb[1], rgb[2]);
  //RGB_LED.setPixelColor(1, rgb[0], rgb[1], rgb[2]);
  //RGB_LED.show();

  //init USB Serial
  Serial.begin(9600);

  //init UART Serial
  UART.begin(9600);

  //setup pins
  pinMode(vol, INPUT_PULLUP);
  pinMode(multi1_0, INPUT_PULLUP);
  pinMode(multi1_1, INPUT_PULLUP);
  pinMode(multi1_2, INPUT_PULLUP);
  pinMode(multi1_3, INPUT_PULLUP);
  pinMode(multi1_4, INPUT_PULLUP);
  pinMode(multi1_5, INPUT_PULLUP);
  pinMode(multi2, INPUT_PULLUP);
  pinMode(station, INPUT_PULLUP);
  pinMode(LED, OUTPUT);
  pinMode(LS_5V, OUTPUT);
  pinMode(LS_OE, OUTPUT);
  pinMode(LS_GND, OUTPUT);

  digitalWrite(LS_5V, HIGH);
  digitalWrite(LS_OE, HIGH);
  digitalWrite(LS_GND, LOW);

  digitalWrite(LED, HIGH);

  Serial.println("Setup complete...");
}

void loop() {
  delay(50);
  String multi1_str = 0;
  int multi1_val = 0;
  int multi2_val = 0;

  /////////monitor multi 1 switch/////////////////////

  multi1_str = String(digitalRead(multi1_0));
  multi1_str += String(digitalRead(multi1_1));
  multi1_str += String(digitalRead(multi1_2));
  multi1_str += String(digitalRead(multi1_3));
  multi1_str += String(digitalRead(multi1_4));
  multi1_str += String(digitalRead(multi1_5));

  if (multi1_str.toInt() != multi1_old) {
    multi1_old = multi1_str.toInt();
    if (multi1_str == "111110") {
      multi1_val = 1;
    } else if (multi1_str == "111101") {
      multi1_val = 2;
    } else if (multi1_str == "111011") {
      multi1_val = 3;
    } else if (multi1_str == "110111") {
      multi1_val = 4;
    } else if (multi1_str == "101111") {
      multi1_val = 5;
    } else if (multi1_str == "011111") {
      multi1_val = 6;
    } else {
      Serial.println(multi1_str);
    }
    if (multi1_val > 0 && multi1_val < 7) {
      Serial.print("Multi1 = ");
      Serial.println(multi1_val);
      UART.print("Multi1 = ");
      UART.println(multi1_val);
    }
  }

  ///////////monitor volume pot//////////////////////

  float float_vol = analogRead(vol);
  //Serial.print("Volume = ");
  //Serial.println(float_vol);
  UART.print("Volume = ");
  UART.println(float_vol);

  /////////////monitor station pot ///////////////////

  float float_station = analogRead(station);

  //Serial.print("Station = ");
  //Serial.println(float_station);
  UART.print("Station = ");
  UART.println(float_station);

  ////////////monitor multi 2 switch/////////////
  multi2_val = digitalRead(multi2);
  if (multi2_val != multi2_old) {
    multi2_old = multi2_val;
    Serial.print("Multi2 = ");
    Serial.println(multi2_val);
    UART.print("Multi2 = ");
    UART.println(multi2_val);
  }

  //read UART responses to set RGB LED
  while (UART.available()) {
    character = UART.read();
    if (character == 'R') {
      color = 0;
      content = "";
    } else if (character == 'G') {
      rgb[color] = content.toInt();
      color = 1;
      content = "";
    } else if (character == 'B') {
      rgb[color] = content.toInt();
      color = 2;
      content = "";
    } else if (isDigit(character)) {
      content.concat(character);
    } else if (character == ';') {
      rgb[color] = content.toInt();
      color = 0;
      content = "";
      Serial.print("R:");
      Serial.print(rgb[0]);
      Serial.print("G:");
      Serial.print(rgb[1]);
      Serial.print("B:");
      Serial.println(rgb[2]);
      //      RGB_LED.setPixelColor(0, rgb[0], rgb[1], rgb[2]);
      //      RGB_LED.setPixelColor(1, rgb[0], rgb[1], rgb[2]);
      //      RGB_LED.show();
    }
  }

}
