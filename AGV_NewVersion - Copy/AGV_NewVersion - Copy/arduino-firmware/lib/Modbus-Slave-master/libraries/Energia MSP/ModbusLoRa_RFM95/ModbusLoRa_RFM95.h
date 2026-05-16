/*
    ModbusLoRa.h - Header for ModbusLoRa Library
    Copyright (C) 2016 UNPARALLEL INOVATION
*/

#include <Arduino.h>
#include <Modbus.h>

#include <SPI.h>
#include <RH_RF95.h>
#include <RHReliableDatagram.h>

#ifndef MODBUSLORA_RFM95_H
#define MODBUSLORA_RFM95_H

#define DEBUG_MODE

// #define BUFFER_SIZE RH_RF95_MAX_MESSAGE_LEN
#define BUFFER_SIZE 128

class ModbusLoRa : public Modbus {
    private:

        #ifdef DEBUG_MODE
          HardwareSerial* DebugPort;
        #endif

        // LoRa Variables
        RHReliableDatagram &_manager;
        unsigned char resetPin;
        uint8_t * buff;
        int size_of_buff;
        uint8_t rf95_len;

        unsigned int _t15; // inter character time out
        unsigned int _t35; // frame delay
        byte  _slaveId;
        bool restartRX;
        unsigned long lastWaitRXMillis;

        unsigned char frame[BUFFER_SIZE];

        word calcCrc(byte address, byte* pduframe, byte pdulen);

        bool receive(byte* frame);
        bool sendPDU(byte* pduframe, uint8_t from);
        bool send(byte* frame, uint8_t from);

    public:
        ModbusLoRa(RHReliableDatagram & manager);

        bool setSlaveId(byte slaveId);
        byte getSlaveId();

        void task();

    #ifndef DEBUG_MODE
        void configLoRa(unsigned char resetpin, uint8_t * buf, int size_of_buf);
    #else
        void configLoRa(HardwareSerial* DebugSerialPort, unsigned char resetpin, uint8_t * buf, int size_of_buf);
    #endif
};

#endif //MODBUSLORA_RFM95_H
