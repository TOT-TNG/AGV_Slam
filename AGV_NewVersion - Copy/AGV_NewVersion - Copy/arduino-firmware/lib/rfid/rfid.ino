/*
* MOSI: Pin 11 / ICSP-4
* MISO: Pin 12 / ICSP-1
* SCK: Pin 13 / ISCP-3
* SS: Pin 10
* RST: Pin 9
*/
#include <Servo.h>
#include <SPI.h>
#include <RFID.h>

#define SS_PIN 10
#define RST_PIN 9
#define GREEN_LED 6
#define RED_LED 7
Servo myservo;
RFID rfid(SS_PIN, RST_PIN);

unsigned char reading_card[5]; //for reading card
unsigned char master[5] = {165,200,111,42,40}; // allowed card
unsigned char i;

void indication(int led);
void allow();
void denied();
int pos = 0;
void setup()
{
   myservo.attach(3);
  Serial.begin(9600);
  SPI.begin();
  rfid.init();
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  myservo.write(0);
}

void loop()
{
    if (rfid.isCard())
    {
        if (rfid.readCardSerial())
        {
                /* Reading card */
                Serial.println(" ");
                Serial.println("Card found");
                Serial.println("Cardnumber:");
                for (i = 0; i < 5; i++)
                {     
                  Serial.print(rfid.serNum[i]);
                  Serial.print(" ");
                  reading_card[i] = rfid.serNum[i];
                }
                Serial.println();
                //verification
                for (i = 0; i < 5; i++)
                {
                  if (reading_card[i]!=master[i])
                  {
                    break;
                  }
                }
                if (i == 5)
                {
                  allow();
                }
                else
                {
                  denied();
                }
         }
    }
    rfid.halt();
}

void allow()
{
  Serial.println("Access accept!");
  indication(GREEN_LED);
  myservo.write(180);
  digitalWrite(GREEN_LED, HIGH);
  delay(2000);
  digitalWrite(GREEN_LED, LOW);
 myservo.write(0);
}
void denied()
{
  Serial.println("Access denied!");
  indication(RED_LED);
}
void indication(int led)
{
  digitalWrite(led, HIGH);
  delay(1000);
  digitalWrite(led, LOW);

}
