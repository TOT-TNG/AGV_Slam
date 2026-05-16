 /*
  Modbus - (Modbus Serial)
 http://github.com/andresarmento/modbus-arduino
 
 Modbus functions supported:
 0x01 - Read Coils
 0x02 - Read Input Status (Read Discrete Inputs)
 0x03 - Read Holding Registers
 0x04 - Read Input Registers
 0x05 - Write Single Coil
 0x06 - Write Single Register
 0x0F - Write Multiple Coils
 0x10 - Write Multiple Registers
 */

#include <Modbus.h>
#include <ModbusLoRa.h>

#include <avr/pgmspace.h>
#include "q3.h"
#include "cl1.h"
#include "cond1.h"

#define PRINTREGISTERS

// ModBus Port information
#define BAUD 57600
#define ID 1
#define RESETPIN 6

// Define the number of registers, inputs and coils to be created
#define NUM_DISCRETE_INPUT 3
#define NUM_INPUT_REGISTERS 3
#define NUM_COILS 3
#define NUM_HOLDING_REGISTERS 10

#define PRINTINTERVAL 2000   //in miliseconds

// ModbusLoRa Object
ModbusLoRa modbus;

const int ledPin = RED_LED;

int value = 0;
int idx = 0;

unsigned long update_time = 0;
unsigned long inc_time = 0;
unsigned long last_print = 0;

void setup() {
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, HIGH);

  Serial.begin(57600);
  Serial.println("Hello! - ModBus Serial Slave");

  // Config Modbus Serial (port, speed, byte format) 
  modbus.configLoRa(&Serial1, BAUD, RESETPIN);

  // Set the Slave ID (1-247)
  modbus.setSlaveId(ID);  

  // Use addIsts() for digital inputs - Discrete Input - Master Read-Only
  for (int i = 0; i < NUM_DISCRETE_INPUT; ++i) {
    modbus.addIsts(i);
  }

  // Use addIreg() for analog Inputs - Input Register - Master Read-Only
  for (int i = 0; i < NUM_INPUT_REGISTERS; ++i) {
    modbus.addIreg(i);
  }

  // Use addCoil() for digital outputs -  Coil - Master Read-Write 
  for (int i = 0; i < NUM_COILS; ++i) {
    modbus.addCoil(i);
  }

  // Use addHreg() for analog outpus - Holding Register - Master Read-Write
  for (int i = 0; i < NUM_HOLDING_REGISTERS; ++i) {
    modbus.addHreg(i, i);
  }

  modbus.addHreg(0x55, 20);
  modbus.addHreg(0x57, 50);
  modbus.addHreg(0x59, 200);

  update_time = millis();
  inc_time = update_time;

  digitalWrite(ledPin, LOW);
}

void loop() {
  //Call once inside loop() - all magic here
  modbus.task();

  if (millis() > inc_time + 500) {
    inc_time = millis();

    ++value;

    if(value >= 1000)
      value = 0;
  }

  if (millis() > update_time + 1000) {
    update_time = millis();

    // Set Digital Input - Discrete Input - Master Read-Only
    modbus.Ists(0, HIGH);

    // Set Analog Input - Input Register - Master Read-Only
    modbus.Ireg(0, 125);
    modbus.Ireg(1, analogRead(A0));

    //Attach ledPin to Digital Output - Coil - Master Read-Write 
    //modbus.Coil(0, !modbus.Coil(0));
    digitalWrite(ledPin, modbus.Coil(0));

    // Write to Analog Output - Holding Register - Master Read-Write
    modbus.Hreg(0, value);
    modbus.Hreg(9, 99);

    float value_q3 = pgm_read_float_near(q3 + idx);
    float value_cl1 = pgm_read_float_near(cl1 + idx);
    float value_cond1 = pgm_read_float_near(cond1 + idx);

    modbus.Hreg(0x55,value_q3*10);
    modbus.Hreg(0x57,value_cl1*1000);
    modbus.Hreg(0x59, value_cond1*100);

    ++idx;
    if( idx == 1124)
      idx = 0;
  }

#ifdef PRINTREGISTERS
  if ( millis() > last_print + PRINTINTERVAL) {
    last_print = millis();

    // Clear serial monitor - Does not work with Serial Monitor from Arduino IDE
    // On a terminal emulator run the following comand to get a complete serial monitor  (screen port baudrate)
    // screen /dev/tty.usbmodem401373 57600
    Serial.println('\n');
    Serial.write(27);       // ESC command
    Serial.print("[2J");    // clear screen command
    Serial.write(27);
    Serial.print("[H");     // cursor to home command

    Serial.print(" - Serial Slave - millis: ");
    Serial.println(millis());
    Serial.println("----------------------------------------------- ");

    // Print all Registers
    Serial.println("Digital Inputs - Read-Only");
    for (int i = 0; i < NUM_DISCRETE_INPUT; ++i) {
      Serial.print("Input ");
      Serial.print(i);
      Serial.print(" : ");
      Serial.println((modbus.Ists(i) != 0) ? "ON" : "OFF");
    }
    Serial.println();
    Serial.println("Analog Inputs - Read-Only");
    for (int i = 0; i < NUM_INPUT_REGISTERS; ++i) {
      Serial.print("I-Reg ");
      Serial.print(i);
      Serial.print(" : ");
      Serial.println(modbus.Ireg(i));
    }
    Serial.println();
    Serial.println("Digital Outputs - Read-Write");
    for (int i = 0; i < NUM_COILS; ++i) {
      Serial.print("Coil ");
      Serial.print(i);
      Serial.print(" : ");
      Serial.println((modbus.Coil(i) != 0) ? "ON" : "OFF");
    }
    Serial.println();
    Serial.println("Analog Outputs - Read-Write");
    for (int i = 0; i < NUM_HOLDING_REGISTERS; ++i) {
      Serial.print("H-Reg ");
      Serial.print(i);
      Serial.print(" : ");
      Serial.println(modbus.Hreg(i));
    }

    Serial.print("------------------------ ");

    delay(5);
  }
#endif
}






