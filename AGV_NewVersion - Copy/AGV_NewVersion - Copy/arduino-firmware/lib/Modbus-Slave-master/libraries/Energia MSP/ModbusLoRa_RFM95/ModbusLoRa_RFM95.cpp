/*
ModbusLoRa.cpp - Source for Modbus Serial Library
Copyright (C) 2016 UNPARALLEL INOVATION
*/

#include "ModbusLoRa_RFM95.h"


ModbusLoRa::ModbusLoRa(RHReliableDatagram &manager)
:
_manager(manager) {
}

bool ModbusLoRa::setSlaveId(byte slaveId){
  _slaveId = slaveId;
  return true;
}

byte ModbusLoRa::getSlaveId() {
  return _slaveId;
}

#ifndef DEBUG_MODE
void ModbusLoRa::configLoRa(unsigned char resetpin, uint8_t * buf, int size_of_buf) {

  // initialize
  _frame = frame;
  buff = buf;
  size_of_buff = size_of_buf;

  resetPin = resetpin;

  pinMode(resetPin, OUTPUT);
  digitalWrite(resetPin, LOW);
  delay(100);
  pinMode(resetPin, INPUT_PULLUP);
  delay(100);

  _t15 = 750;
  _t35 = 1750;

  _manager.init();
}
#endif

#ifdef DEBUG_MODE
void ModbusLoRa::configLoRa(HardwareSerial* DebugSerialPort, unsigned char resetpin, uint8_t * buf, int size_of_buf) {

  // initialize
  _frame = frame;
  buff = buf;
  size_of_buff = size_of_buf;

  this->DebugPort = DebugSerialPort;

  resetPin = resetpin;

  pinMode(resetPin, OUTPUT);
  digitalWrite(resetPin, LOW);
  delay(100);
  pinMode(resetPin, INPUT_PULLUP);
  delay(100);

  _t15 = 750;
  _t35 = 1750;

  if (!_manager.init())
  (*DebugPort).println(F("init failed"));
}
#endif

void ModbusLoRa::task() {
  uint8_t from = 0;

  if (_manager.available())
  {
    rf95_len = size_of_buff;

    if (_manager.recvfromAck(buff, &rf95_len, &from))
    {
      #ifdef DEBUG_MODE
      (*DebugPort).println();
      (*DebugPort).println(F("-----------------------------------------------"));
      (*DebugPort).println();
      (*DebugPort).print(F("MSG RECEIVED from address: "));
      (*DebugPort).println(from);
      // (*DebugPort).print("Len: ");
      // (*DebugPort).println(rf95_len);
      for (int i = 0; i < rf95_len; ++i) {
        (*DebugPort).print(buff[i], DEC);
        (*DebugPort).print(":");
      }
      (*DebugPort).println();
      (*DebugPort).println(F("------------------------------"));

      if (rf95_len > BUFFER_SIZE) {
        (*DebugPort).println(F("-------- ERROR BUFFER Overflow --------"));
      }
      #endif

      if (rf95_len < 5) return;

      _len = rf95_len;

      for (int i = 0; i < _len; ++i) {
        frame[i] = buff[i];
      }
    }
    #ifdef DEBUG_MODE
    else {
      (*DebugPort).println(F("FAILED to receive MSG"));
    }
    #endif

    for (int i = 0; i < _len; ++i) {
      _frame[i] = frame[i];
    }

    if (this->receive(_frame)) {
      if (_reply == MB_REPLY_NORMAL)
      this->sendPDU(_frame, from);
      else if (_reply == MB_REPLY_ECHO)
      this->send(_frame, from);
    }
  }
}

bool ModbusLoRa::receive(byte* frame) {
  //first byte of frame = address
  byte address = frame[0];
  //Last two bytes = crc
  u_int crc = ((frame[_len - 2] << 8) | frame[_len - 1]);

  //Slave Check
  if (address != 0xFF && address != this->getSlaveId()) {
    #ifdef DEBUG_MODE
    (*DebugPort).print(F("Wrong Slave ID: "));
    (*DebugPort).print(address);
    (*DebugPort).print(F(" : "));
    (*DebugPort).println(this->getSlaveId());
    #endif
    return false;
  }

  //CRC Check
  if (crc != this->calcCrc(_frame[0], _frame+1, _len-3)) {
    #ifdef DEBUG_MODE
    (*DebugPort).println(F("Wrong CRC"));
    #endif
    return false;
  }

  //PDU starts after first byte
  //framesize PDU = framesize - address(1) - crc(2)
  this->receivePDU(frame+1);
  //No reply to Broadcasts
  if (address == 0xFF) _reply = MB_REPLY_OFF;
  return true;
}

bool ModbusLoRa::send(byte* frame, uint8_t from) {

  #ifdef DEBUG_MODE
  (*DebugPort).print(F("SENDING REPPLY to address: "));
  (*DebugPort).println(from);
  (*DebugPort).println(F("REPLY DEC"));
  for (int i = 0 ; i < _len ; i++) {
    if(frame[i] < 10)
    (*DebugPort).print('0');
    (*DebugPort).print(frame[i]);
    (*DebugPort).print(':');
  }
  (*DebugPort).println(F("REPLY HEX"));
  for (int i = 0 ; i < _len ; i++) {
    if(frame[i] < 16)
    (*DebugPort).print('0');
    (*DebugPort).print(frame[i], HEX);
    (*DebugPort).print(':');
  }

  if(!_manager.sendtoWait(frame, _len, from))
    (*DebugPort).println(F("FAILED to receive ACK"));
  #else
  _manager.sendtoWait(frame, _len, from);
  #endif
}

bool ModbusLoRa::sendPDU(byte* pduframe, uint8_t from) {

  frame[0] = _slaveId;

  int i = 0;

  for (i = 0; i < _len; ++i)
  {
    frame[i+1] = pduframe[i];
  }

  //Send CRC
  word crc = calcCrc(_slaveId, _frame, _len);
  frame[++i] = crc >> 8;
  frame[++i] = crc & 0xFF;

  _len += 3; // increment _len to fit _slaveId and CRC bytes

  #ifdef DEBUG_MODE
  (*DebugPort).print(F("SENDING REPPLY to address: "));
  (*DebugPort).println(from);
  // (*DebugPort).println("REPLY DEC");
  // (*DebugPort).print(_slaveId);
  // (*DebugPort).print(':');
  // for (int i = 0 ; i < _len ; i++) {
  //   if(pduframe[i] < 10)
  //   (*DebugPort).print('0');
  //   (*DebugPort).print(pduframe[i]);
  //   (*DebugPort).print(':');
  // }
  // (*DebugPort).print(crc >> 8);
  // (*DebugPort).print(':');
  // (*DebugPort).print(crc & 0xFF);
  // (*DebugPort).print(':');
  // (*DebugPort).println();
  //
  // (*DebugPort).println("REPLY HEX");
  // (*DebugPort).print(_slaveId, HEX);
  // (*DebugPort).print(':');
  // for (int i = 0 ; i < _len ; i++) {
  //   if(pduframe[i] < 16)
  //   (*DebugPort).print('0');
  //   (*DebugPort).print(pduframe[i], HEX);
  //   (*DebugPort).print(':');
  // }
  // if(crc >> 8 < 16)
  // (*DebugPort).print('0');
  // (*DebugPort).print(crc >> 8, HEX);
  // (*DebugPort).print(':');
  // if(crc & 0xFF < 16)
  // (*DebugPort).print('0');
  // (*DebugPort).print(crc & 0xFF, HEX);
  // (*DebugPort).print(':');
  // (*DebugPort).println();

  // (*DebugPort).println("REPLY DEC");
  for (int i = 0 ; i < _len ; i++) {
    if(frame[i] < 10)
    (*DebugPort).print('0');
    (*DebugPort).print(frame[i]);
    (*DebugPort).print(':');
  }
  (*DebugPort).println();

  if(!_manager.sendtoWait(frame, _len, from)) {
    (*DebugPort).println(F("FAILED to receive ACK"));
  }
  #else
  _manager.sendtoWait(frame, _len, from);
  #endif
}

word ModbusLoRa::calcCrc(byte address, byte * frameIn, byte bufferSize)
{
  unsigned char * framePtr = frameIn;

  unsigned int temp, temp2, flag;
  temp = 0xFFFF;

  temp = temp ^ address;
  for (unsigned char j = 1; j <= 8; j++)
  {
    flag = temp & 0x0001;
    temp >>= 1;
    if (flag)
    temp ^= 0xA001;
  }

  for (unsigned char i = 0; i < bufferSize; i++)
  {
    temp = temp ^ framePtr[i];
    for (unsigned char j = 1; j <= 8; j++)
    {
      flag = temp & 0x0001;
      temp >>= 1;
      if (flag)
      temp ^= 0xA001;
    }
  }
  // Reverse byte order.
  temp2 = temp >> 8;
  temp = (temp << 8) | temp2;
  temp &= 0xFFFF;
  // the returned value is already swapped
  // crcLo byte is first & crcHi byte is last
  return (word) temp;
}
