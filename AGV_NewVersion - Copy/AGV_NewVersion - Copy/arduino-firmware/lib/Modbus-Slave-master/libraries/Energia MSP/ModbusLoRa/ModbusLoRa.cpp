/*
ModbusLoRa.cpp - Source for Modbus Serial Library
Copyright (C) 2016 UNPARALLEL INOVATION
*/

#include "ModbusLoRa.h"

ModbusLoRa::ModbusLoRa() {
}

bool ModbusLoRa::setSlaveId(byte slaveId){
  _slaveId = slaveId;
  return true;
}

byte ModbusLoRa::getSlaveId() {
  return _slaveId;
}

#ifndef DEBUG_MODE
void ModbusLoRa::configLoRa(HardwareSerial* port, long baud, unsigned char resetpin) {

  _frame = frame;
  this->_port = port;
  (*port).begin(baud);
  (*port).setTimeout(2000);
  (*_port).flush();

  restartRX = false;
  resetPin = resetpin;
  pinMode(resetPin, OUTPUT);
  digitalWrite(resetPin, LOW);
  delay(100);
  pinMode(resetPin, INPUT);
  digitalWrite(resetPin, INPUT_PULLUP);

  if (baud > 19200) {
    _t15 = 750;
    _t35 = 1750;
  } else {
    _t15 = 15000000/baud; // 1T * 1.5 = T1.5
    _t35 = 35000000/baud; // 1T * 3.5 = T3.5
  }

  delayMicroseconds(_t35);

  unsigned long currentMillis = millis();
  while (!(*_port).available()  && millis() - currentMillis < 2000);

  String str = (*_port).readStringUntil('\n');

  send_cmd_lora("sys reset", true, false);
  send_cmd_lora("mac pause", false, false);
  send_cmd_lora("radio rx 0", true, false);
  lastWaitRXMillis = millis();
}
#endif

#ifdef DEBUG_MODE
void ModbusLoRa::configLoRa(HardwareSerial* port,
  HardwareSerial* DebugSerialPort,  long baud, unsigned char resetpin) {

    _frame = frame;
    this->_port = port;
    this->DebugPort = DebugSerialPort;
    (*port).begin(baud);
    (*port).setTimeout(2000);
    (*_port).flush();

    restartRX = false;
    resetPin = resetpin;
    pinMode(resetPin, OUTPUT);
    digitalWrite(resetPin, LOW);
    delay(100);
    pinMode(resetPin, INPUT);
    digitalWrite(resetPin, INPUT_PULLUP);

    if (baud > 19200) {
      _t15 = 750;
      _t35 = 1750;
    } else {
      _t15 = 15000000/baud; // 1T * 1.5 = T1.5
      _t35 = 35000000/baud; // 1T * 3.5 = T3.5
    }

    delayMicroseconds(_t35);

    unsigned long currentMillis = millis();
    while (!(*_port).available()  && millis() - currentMillis < 2000);

    String str = (*_port).readStringUntil('\n');

    send_cmd_lora("sys reset", true, false);
    send_cmd_lora("mac pause", false, false);
    send_cmd_lora("radio rx 0", true, false);
    lastWaitRXMillis = millis();
    (*DebugPort).println("-----------");
  }
  #endif

  void ModbusLoRa::task() {
    _len = 0;
    unsigned long currentMillis = millis();

    if ((currentMillis - lastWaitRXMillis > 15300) || restartRX) {
      lastWaitRXMillis = currentMillis;
      restartRX = false;
      send_cmd_lora("radio rx 0", true, false);
    }

    while ((*_port).available() > _len)	{
      _len = (*_port).available();
      delayMicroseconds(_t15);
    }

    if (_len < 10) return;

    #ifdef DEBUG_MODE
    if (_len > BUFFER_SIZE) {
      (*DebugPort).println("-------- ERROR BUFFER Overflow --------");
    }
    #endif

    String str = (*_port).readStringUntil('\n');

    #ifdef DEBUG_MODE
    (*DebugPort).println("-----------------------------------------------");
    (*DebugPort).print("Msg received: ");
    (*DebugPort).println(str);
    #endif

    restartRX = true;

    String recv_msg = "radio_rx  ";
    if (str.substring(0,recv_msg.length()) == recv_msg)
    {
      _len = ((str.length()-11)/2);

      byte frame_aux[str.length()];

      str.getBytes(frame_aux, str.length());

      for (int i = 0; i < _len; ++i) {
        _frame[i] = hexToChar(frame_aux[2*i+10], frame_aux[2*i+11]);
      }

      if (this->receive(_frame)) {
        if (_reply == MB_REPLY_NORMAL)
        this->sendPDU(_frame);
        else if (_reply == MB_REPLY_ECHO)
        this->send(_frame);
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
      (*DebugPort).print("Wrong Slave ID: ");
      (*DebugPort).print(address);
      (*DebugPort).print(" : ");
      (*DebugPort).println(this->getSlaveId());
      #endif
      return false;
    }

    //CRC Check
    if (crc != this->calcCrc(_frame[0], _frame+1, _len-3)) {
      #ifdef DEBUG_MODE
      (*DebugPort).println("Wrong CRC");
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

  bool ModbusLoRa::send(byte* frame) {
    char buf[10 + _len*2];
    char rtx[] = "radio tx ";
    char c2[2];

    for (int i = 0; i < 9; ++i) {
      buf[i] = rtx[i];
    }

    for (int i = 0; i < _len; ++i)
    {
      sprintf(c2, "%02x", frame[i]);
      buf[9+2*i] = c2[0];
      buf[10+2*i] = c2[1];
    }

    buf[9+2*_len] = '\0';

    #ifdef DEBUG_MODE
    (*DebugPort).print("TX frame dec: ");
    for (int i = 0 ; i < _len ; i++) {
      (*DebugPort).print(frame[i]);
      (*DebugPort).print(':');
    }
    (*DebugPort).println();

    (*DebugPort).print("TX frame hex: ");
    for (int i = 0 ; i < _len ; i++) {
      (*DebugPort).print(frame[i], HEX);
      (*DebugPort).print(':');
    }
    (*DebugPort).println();

    send_cmd_lora(buf, true, true);
    #else
    send_cmd_lora(buf, false, true);
    #endif
  }

  bool ModbusLoRa::sendPDU(byte* pduframe) {
    char buf[16 + _len*2];
    char rtx[] = "radio tx ";
    char c2[2];

    for (int i = 0; i < 9; ++i) {
      buf[i] = rtx[i];
    }

    sprintf(c2, "%02x", _slaveId);
    buf[9] = c2[0];
    buf[10] = c2[1];

    for (int i = 0; i < _len; ++i)
    {
      sprintf(c2, "%02x", pduframe[i]);
      buf[11+2*i] = c2[0];
      buf[12+2*i] = c2[1];
    }

    //Send CRC
    word crc = calcCrc(_slaveId, _frame, _len);
    sprintf(c2, "%02x", crc >> 8);
    buf[11+2*_len] = c2[0];
    buf[12+2*_len] = c2[1];
    sprintf(c2, "%02x", crc & 0xFF);
    buf[11+2*(_len+1)] = c2[0];
    buf[12+2*(_len+1)] = c2[1];

    buf[13+2*(_len+1)] = '\0';

    #ifdef DEBUG_MODE
    (*DebugPort).print("TX pduframe dec: ");
    (*DebugPort).print(_slaveId);
    (*DebugPort).print(':');
    for (int i = 0 ; i < _len ; i++) {
      if(pduframe[i] < 10)
      (*DebugPort).print('0');
      (*DebugPort).print(pduframe[i]);
      (*DebugPort).print(':');
    }
    (*DebugPort).print(crc >> 8);
    (*DebugPort).print(':');
    (*DebugPort).print(crc & 0xFF);
    (*DebugPort).print(':');
    (*DebugPort).println();

    (*DebugPort).print("TX pduframe hex: ");
    (*DebugPort).print(_slaveId, HEX);
    (*DebugPort).print(':');
    for (int i = 0 ; i < _len ; i++) {
      if(pduframe[i] < 16)
      (*DebugPort).print('0');
      (*DebugPort).print(pduframe[i], HEX);
      (*DebugPort).print(':');
    }
    if(crc >> 8 < 16)
    (*DebugPort).print('0');
    (*DebugPort).print(crc >> 8, HEX);
    (*DebugPort).print(':');
    if(crc & 0xFF < 16)
    (*DebugPort).print('0');
    (*DebugPort).print(crc & 0xFF, HEX);
    (*DebugPort).print(':');
    (*DebugPort).println();

    send_cmd_lora(buf, true, true);
    #else
    send_cmd_lora(buf, false, true);
    #endif
  }

  int ModbusLoRa::send_cmd_lora(char * cmd, bool printCmdRes, bool doubleRes) {
    unsigned long currentMillis = millis();
    #ifdef DEBUG_MODE
    if (printCmdRes) {
      (*DebugPort).print("Cmd: ");
      (*DebugPort).println(cmd);
    }
    #endif
    (*_port).print(cmd);
    (*_port).write("\r\n");

    (*_port).flush();
    delayMicroseconds(_t35);

    while (!(*_port).available()  && millis() - currentMillis < 2000);
    String str = (*_port).readStringUntil('\n');

    #ifdef DEBUG_MODE
    if (printCmdRes) {
      (*DebugPort).print("Res: ");
      (*DebugPort).println(str);
      (*DebugPort).println();
    }
    #endif

    if(doubleRes)
    {
      while (!(*_port).available()  && millis() - currentMillis < 4000);
      str = (*_port).readStringUntil('\n');

      #ifdef DEBUG_MODE
      if (printCmdRes) {
        (*DebugPort).print("Res: ");
        (*DebugPort).println(str);
        (*DebugPort).println();
      }
      #endif
    }
    return 0;
  }

  word ModbusLoRa::calcCrc(byte address, byte* pduFrame, byte pduLen) {
    byte CRCHi = 0xFF, CRCLo = 0x0FF, Index;

    Index = CRCHi ^ address;
    CRCHi = CRCLo ^ _auchCRCHi[Index];
    CRCLo = _auchCRCLo[Index];

    while (pduLen--) {
      Index = CRCHi ^ *pduFrame++;
      CRCHi = CRCLo ^ _auchCRCHi[Index];
      CRCLo = _auchCRCLo[Index];
    }

    return (CRCHi << 8) | CRCLo;
  }

  char ModbusLoRa::hexToC(char c)
  {
    if (c >= '0' && c <= '9')
    return c - '0';
    else if (c >= 'a' && c <= 'f')
    return 10 + c - 'a';
    else if (c >= 'A' && c <= 'F')
    return 10 + c - 'A';
    else return 0;
  }
  char ModbusLoRa::hexToChar(char c1, char c2) {
    return (hexToC(c1) * 16 + hexToC(c2));
  }
