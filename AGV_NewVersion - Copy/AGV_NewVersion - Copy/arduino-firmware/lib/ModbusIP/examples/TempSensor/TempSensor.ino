/*
  Modbus-Arduino Example - TempSensor (Modbus IP)
  Copyright by André Sarmento Barbosa
  http://github.com/andresarmento/modbus-arduino
*/

#include <ModbusIP.h>
#define     ETH_RST         4
#define     ETH_CS          33
#define     ETH_SCLK       18
#define     ETH_MISO       23
#define     ETH_MOSI       19
#define     OLED_SCL       22
#define     OLED_SDA       21
const int Val3X[10]={0,1,2,3,4,5,6,7,8,9};
const int Val4X[10]={0,1,2,3,4,5,6,7,8,9};
//
const int JK3x0001_VAL = Val3X[0];
const int JK3x0002_VAL = Val3X[1];
const int JK3x0003_VAL = Val3X[2];

//
const int JK4x0001 = Val4X[0];
const int JK4x0002 = Val4X[1];
const int JK4x0003 = Val4X[2];

//Modbus Registers Offsets (0-9999)
const int SENSOR_IREG = 1; 
    
//Used Pins
const int sensorPin = 1234;

//ModbusIP object
ModbusIP mb;

long ts;
void ethernetReset(const uint8_t resetPin)
{
    pinMode(resetPin, OUTPUT);
    digitalWrite(resetPin, HIGH);
    delay(250);
    digitalWrite(resetPin, LOW);
    delay(50);
    digitalWrite(resetPin, HIGH);
    delay(350);
}
   
void setup() {
   uint8_t mac[]     = { 0x90, 0xA2, 0xDA, 0x00, 0x51, 0x06 };
  uint8_t ip[]      = { 192, 168, 1, 8 };
  uint8_t gateway[] = { 192, 168, 1, 1 };
  uint8_t subnet[]  = { 255, 255, 255, 0 };
    // The media access control (ethernet hardware) address for the shield
  
    //Config Modbus IP 
       SPI.begin(ETH_SCLK, ETH_MISO, ETH_MOSI);

    ethernetReset(ETH_RST);
    Ethernet.init(ETH_CS);
      Ethernet.begin(mac, ip, gateway, subnet);

     mb.config(mac, ip,gateway, subnet);

    // Add SENSOR_IREG register - Use addIreg() for analog Inputs
   // mb.addIreg(SENSOR_IREG);
   

         mb.addHreg(JK4x0001);  
        
    
  
}
long int cnt=0,pos=0;
void loop() {
   //Call once inside loop() - all magic here
 
     cnt++;
     pos++;
   //Read each two seconds
   switch(pos)
   {
     case 1:     mb.Hreg(JK4x0001,cnt);break;
         case 11:   pos=0;break;
   }
     mb.task();
}
