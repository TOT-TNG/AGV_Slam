/*
 * Example to demonstrate thread definition, semaphores, and thread sleep.
 */
#include <NilRTOS.h>
 
#include <Modbus.h>
#include <ModbusSerial.h>
//#include <Arduino_FreeRTOS.h>

// define two tasks for Blink & AnalogRead

// Modbus Registers Offsets (0-9999)
const int LAMP1_COIL =0; 
const int LAMP2_COIL =1; 
const int LAMP3_COIL =2; 
const int LAMP4_COIL =3; 
const int len_hol = 16; 
// Used Pins
const int ledPin = 13;
const int LED1_VAL = 0; //primeiro led posição 0
const int LED2_VAL = 1; //segundo led posição 1
long int cnt_mb=0;


//const int JK1_VAL = 0;
const int JK2_VAL = 0;
const int K1 = 0;
const int K2 = 1;
const int K3 = 2;
const int K4 = 3;
const int K5 = 4;
const int K7 = 5;
// ModbusSerial object
ModbusSerial mb;

// The LED is attached to pin 13 on Arduino.
const uint8_t LED_PIN = 13;

// Declare a semaphore with an inital counter value of zero.
SEMAPHORE_DECL(sem, 0);
//------------------------------------------------------------------------------
/*
 * Thread 1, turn the LED off when signalled by thread 2.
 */
// Declare a stack with 128 bytes beyond context switch and interrupt needs.
NIL_WORKING_AREA(waThread1, 128);

// Declare the thread function for thread 1.
NIL_THREAD(Thread1, arg) {
  while (TRUE) {
    
    // Wait for signal from thread 2.
    nilSemWait(&sem);
    
    // Turn LED off.
  
  }
}
//------------------------------------------------------------------------------
/*
 * Thread 2, turn the LED on and signal thread 1 to turn the LED off.
 */
// Declare a stack with 128 bytes beyond context switch and interrupt needs. 
NIL_WORKING_AREA(waThread2, 128);

// Declare the thread function for thread 2.
NIL_THREAD(Thread2, arg) {

  pinMode(LED_PIN, OUTPUT);
  
  while (TRUE) {
    // Turn LED on.
  
    
    // Sleep for 200 milliseconds.
    nilThdSleepMilliseconds(1);
    
    // Signal thread 1 to turn LED off.
    nilSemSignal(&sem);
    
    // Sleep for 200 milliseconds.   
    nilThdSleepMilliseconds(1);
  }
}
//------------------------------------------------------------------------------
/*
 * Threads static table, one entry per thread.  A thread's priority is
 * determined by its position in the table with highest priority first.
 * 
 * These threads start with a null argument.  A thread's name may also
 * be null to save RAM since the name is currently not used.
 */
NIL_THREADS_TABLE_BEGIN()
NIL_THREADS_TABLE_ENTRY("thread1", Thread1, NULL, waThread1, sizeof(waThread1))
NIL_THREADS_TABLE_ENTRY("thread2", Thread2, NULL, waThread2, sizeof(waThread2))
NIL_THREADS_TABLE_END()
//------------------------------------------------------------------------------
void setup() {
  // Start Nil RTOS.
    mb.config(&Serial1, 9600, SERIAL_8N1);
    // Set the Slave ID (1-247)
    mb.setSlaveId(1);  
    
    // Set ledPin mode
    pinMode(ledPin, OUTPUT);
    // Add LAMP1_COIL register - Use addCoil() for digital outputs
    mb.addCoil(LAMP1_COIL);
    mb.addCoil(LAMP2_COIL);
    mb.addCoil(LAMP3_COIL);
    mb.addCoil(LAMP4_COIL);
   // mb.addIreg(JK1_VAL);
    mb.addIreg(JK2_VAL);
    mb.addHreg(K1);
    mb.addHreg(K2);
    mb.addHreg(K3);
    mb.addHreg(K4);
    mb.addHreg(K5);
      Serial.begin(9600);
  Serial.println(F("In Setup function"));
  nilSysBegin();
}
//------------------------------------------------------------------------------
// Loop is the idle thread.  The idle thread must not invoke any 
// kernel primitive able to change its state to not runnable.
void loop() {
  // Not used.
  
   mb.task();
   if(++cnt_mb>65535) cnt_mb=0;
      //  mb.Ireg(JK1_VAL,cnt_mb);
     mb.Ireg(JK2_VAL,cnt_mb);
     mb.Hreg(K1,121);
     mb.Hreg(K2,121);
     mb.Hreg(K3,123);
     mb.Hreg(K4,145);
      mb.Hreg(K5,441);
      if(mb.Coil(LAMP1_COIL)==1)   digitalWrite(LED_PIN, LOW);
      else   digitalWrite(LED_PIN, HIGH);
      //  digitalWrite(ledPin, mb.Coil(LAMP1_COIL));
}
