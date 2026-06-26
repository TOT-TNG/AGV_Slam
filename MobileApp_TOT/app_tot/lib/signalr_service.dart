import 'package:signalr_netcore/signalr_client.dart';
import 'package:flutter/material.dart';

class SignalRService {
  HubConnection? hubConnection;
  final String hubUrl = "http://192.168.0.46:7000/materialHub";
  final Function(String, String, dynamic) onMessageReceived;
  bool _isConnected = false;

  SignalRService({required this.onMessageReceived});

  Future<void> start() async {
    if (_isConnected) return;
    hubConnection = HubConnectionBuilder().withUrl(hubUrl).build();
    hubConnection?.onclose((_) {
      print("Connection closed");
      _isConnected = false;
      // Tự động kết nối lại sau 5 giây (tùy chọn)
      Future.delayed(const Duration(seconds: 5), () => start());
    } as ClosedCallback);

    hubConnection?.on("ReceiveMaterialUpdate", (args) {
      if (args != null && args.length == 3) {
        final role = args[0] as String;
        final message = args[1] as String;
        final data = args[2];
        onMessageReceived(role, message, data);
      }
    });

    try {
      await hubConnection?.start();
      _isConnected = true;
      print("SignalR Connected");
    } catch (e) {
      print("SignalR Connection Error: $e");
    }
  }

  Future<void> stop() async {
    if (!_isConnected) return;
    await hubConnection?.stop();
    _isConnected = false;
    print("SignalR Disconnected");
  }
}