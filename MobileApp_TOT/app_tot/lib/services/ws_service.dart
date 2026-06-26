import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'api_service.dart';

typedef WsCallback = void Function(Map<String, dynamic> msg);

/// WebSocket client for real-time AGV updates from /ws endpoint.
/// Singleton — call WsService.instance to get the shared instance.
/// Uses web_socket_channel so it works on both web and native.
class WsService {
  WsService._();
  static final WsService instance = WsService._();

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _reconnectTimer;
  Timer? _pingTimer;
  final List<WsCallback> _listeners = [];
  bool _active = false;
  bool _connected = false;

  bool get isConnected => _connected;

  void addListener(WsCallback cb) {
    if (!_listeners.contains(cb)) _listeners.add(cb);
  }

  void removeListener(WsCallback cb) => _listeners.remove(cb);

  Future<void> start() async {
    if (_active && _connected) return;
    _active = true;
    if (!_connected) await _connect();
  }

  void stop() {
    _active = false;
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
    _connected = false;
  }

  Future<void> _connect() async {
    if (!_active) return;
    try {
      final url = await ApiService.wsUrl;
      _channel = WebSocketChannel.connect(Uri.parse(url));
      // wait for connection (throws if rejected)
      await _channel!.ready.timeout(const Duration(seconds: 6));
      _connected = true;

      _pingTimer?.cancel();
      _pingTimer = Timer.periodic(const Duration(seconds: 20), (_) {
        if (_connected) _channel?.sink.add('ping');
      });

      _sub = _channel!.stream.listen(
        _onData,
        onDone: _onDisconnected,
        onError: (_) => _onDisconnected(),
        cancelOnError: true,
      );
    } catch (_) {
      _connected = false;
      _scheduleReconnect();
    }
  }

  void _onData(dynamic raw) {
    if (raw == null) return;
    final text = raw.toString();
    if (text == 'pong') return;
    try {
      final msg = jsonDecode(text);
      if (msg is Map<String, dynamic>) {
        for (final cb in List<WsCallback>.from(_listeners)) {
          cb(msg);
        }
      }
    } catch (_) {}
  }

  void _onDisconnected() {
    _pingTimer?.cancel();
    _sub?.cancel();
    _channel = null;
    _connected = false;
    if (_active) _scheduleReconnect();
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 5), _connect);
  }
}
