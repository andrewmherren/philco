//#include <Adafruit_NeoPixel.h>
#include <avr/power.h>

// constants
#define STATION 0
#define VOLUME 1
#define MULTI1 2

// function prototypes
bool isWithin(float old_value, float new_value,  float error);
void sendData(int type = -1);
int readMulti1();
void readSerialResponse();

//setup pins
int vol_pin = PIN_F0; //volume potentiometer
int multi1_0_pin = PIN_F1; //multi switch 1
int multi1_1_pin = PIN_F4;
int multi1_2_pin = PIN_F5;
int multi1_3_pin = PIN_F6;
int multi1_4_pin = PIN_F7;
int multi1_5_pin = PIN_B6;
int station_pin = PIN_B4; //station potentimeter
int LED_pin = PIN_D6;

//global values
long multi1 = -1;
float volume = 0;
float station = 0;

void setup() {

  //init USB Serial
  Serial.begin(9600);

  //setup pins
  pinMode(vol_pin, INPUT_PULLUP);
  pinMode(multi1_0_pin, INPUT_PULLUP);
  pinMode(multi1_1_pin, INPUT_PULLUP);
  pinMode(multi1_2_pin, INPUT_PULLUP);
  pinMode(multi1_3_pin, INPUT_PULLUP);
  pinMode(multi1_4_pin, INPUT_PULLUP);
  pinMode(multi1_5_pin, INPUT_PULLUP);
  pinMode(station_pin, INPUT_PULLUP);
  pinMode(LED_pin, OUTPUT);

  digitalWrite(LED_pin, HIGH);

  Serial.println("Setup complete...");
}

bool isWithin(float old_value, float new_value, float error) {
  return (new_value <= (old_value + error) && new_value >= (old_value - error));
}

void sendData(int type) {
  switch (type) {
    case STATION:
      Serial.print(type);
      Serial.print(',');
      Serial.println(station);
      break;
    case VOLUME:
      Serial.print(type);
      Serial.print(',');
      Serial.println(volume); 
      break;
    case MULTI1:
      Serial.print(type);
      Serial.print(',');
      Serial.println(multi1);
      break;
    default:
      sendData(STATION);
      sendData(VOLUME);
      sendData(MULTI1);
  }
}

void communicate(float next_station, float next_volume, int next_multi1) {
  if(multi1 != next_multi1) {
    multi1 = next_multi1;
    sendData(MULTI1);
  }

  if(!isWithin(station, next_station, 10)) {
    station = next_station;
    sendData(STATION);
  }

  if(!isWithin(volume, next_volume, 10)) {
    volume = next_volume;
    sendData(VOLUME);
  }
}

int readMulti1() {
  if(!digitalRead(multi1_0_pin)) {
    return 1;
  } else if (!digitalRead(multi1_1_pin)) {
    return 2;
  } else if (!digitalRead(multi1_2_pin)) {
    return 3;
  } else if (!digitalRead(multi1_3_pin)) {
    return 4;
  } else if (!digitalRead(multi1_4_pin)) {
    return 5;
  } else if (!digitalRead(multi1_5_pin)) {
    return 6;
  } else {
    return 0;
  }
}

void readSerialResponse() {
  String content;
  while (Serial.available()) {
    content = Serial.readString().trim(); // trim to get rid of whitespace (carriage return etc)
    if(content == "read") {
      sendData();
    } else {
      Serial.println("Received = ");
      Serial.println(content); 
    }
  }
}

void loop() {
  delay(25);
  
  // read multi switch
  int next_multi1 = readMulti1();
  // read volume
  float next_volume = analogRead(vol_pin);
  // read station
  float next_station = analogRead(station_pin);
  // communicate changes
  communicate(next_station, next_volume, next_multi1) ;

  readSerialResponse();
}
