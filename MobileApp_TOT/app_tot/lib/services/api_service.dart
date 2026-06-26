import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Centralized API client for AGVmqtt (TOT ACS) backend.
class ApiService {
  static const String _urlPrefKey     = 'acs_server_url';
  static const String _gatewayKeyPref = 'gateway_key';

  // Có thể ghi đè lúc build: flutter build web --dart-define=API_BASE_URL=https://...
  static const String defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://192.168.0.86:8000',
  );

  static Future<String> get baseUrl async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getString(_urlPrefKey) ?? defaultBaseUrl).trimRight().replaceAll(RegExp(r'/$'), '');
  }

  static Future<void> setBaseUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_urlPrefKey, url.trim());
  }

  static Future<String?> get gatewayKey async {
    final prefs = await SharedPreferences.getInstance();
    final k = prefs.getString(_gatewayKeyPref)?.trim();
    return (k == null || k.isEmpty) ? null : k;
  }

  static Future<void> setGatewayKey(String key) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_gatewayKeyPref, key.trim());
  }

  /// Headers chung: thêm X-Gateway-Key nếu có.
  static Future<Map<String, String>> _headers({bool json = false}) async {
    final key = await gatewayKey;
    return {
      if (json) 'Content-Type': 'application/json',
      if (key != null) 'X-Gateway-Key': key,
    };
  }

  static Future<String> get wsUrl async {
    final base = await baseUrl;
    final key  = await gatewayKey;
    final url  = base.replaceFirst(RegExp(r'^http'), 'ws') + '/ws';
    return key != null ? '$url?key=${Uri.encodeComponent(key)}' : url;
  }

  // ── Auth ─────────────────────────────────────────────────────────────────

  /// Login: local network, no real auth. Any username is accepted.
  static Future<Map<String, dynamic>> login(String username) async {
    final base = await baseUrl;
    final response = await http
        .post(
          Uri.parse('$base/api/auth/login'),
          headers: await _headers(json: true),
          body: jsonEncode({'username': username}),
        )
        .timeout(const Duration(seconds: 8));
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// Quick connectivity check.
  static Future<bool> ping() async {
    try {
      final base = await baseUrl;
      final response = await http
          .get(Uri.parse('$base/api/execute/agv-list'), headers: await _headers())
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ── AGV ──────────────────────────────────────────────────────────────────

  /// GET /api/execute/agv-list → {agvs: [...], total: N}
  static Future<Map<String, dynamic>> getAgvList() async {
    final base = await baseUrl;
    final response = await http
        .get(Uri.parse('$base/api/execute/agv-list'), headers: await _headers())
        .timeout(const Duration(seconds: 10));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// POST /api/agv/cancel-order
  static Future<Map<String, dynamic>> cancelOrder(String agvId) async {
    final base = await baseUrl;
    final response = await http
        .post(
          Uri.parse('$base/api/agv/cancel-order'),
          headers: await _headers(json: true),
          body: jsonEncode({'agv_id': agvId}),
        )
        .timeout(const Duration(seconds: 10));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// POST /api/agv/go-charge
  static Future<Map<String, dynamic>> goCharge(String agvId) async {
    final base = await baseUrl;
    final response = await http
        .post(
          Uri.parse('$base/api/agv/go-charge'),
          headers: await _headers(json: true),
          body: jsonEncode({'agv_id': agvId}),
        )
        .timeout(const Duration(seconds: 10));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// POST /api/agv/go-wait
  static Future<Map<String, dynamic>> goWait(String agvId) async {
    final base = await baseUrl;
    final response = await http
        .post(
          Uri.parse('$base/api/agv/go-wait'),
          headers: await _headers(json: true),
          body: jsonEncode({'agv_id': agvId}),
        )
        .timeout(const Duration(seconds: 10));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  // ── Tasks ────────────────────────────────────────────────────────────────

  /// GET /api/tasks?limit=N&status=X
  static Future<List<Map<String, dynamic>>> getTasks({int limit = 200, String? status}) async {
    final base = await baseUrl;
    final params = <String, String>{'limit': '$limit'};
    if (status != null && status != 'all') params['status'] = status;
    final uri = Uri.parse('$base/api/tasks').replace(queryParameters: params);
    final response = await http.get(uri, headers: await _headers()).timeout(const Duration(seconds: 10));
    _assertOk(response);
    final body = jsonDecode(response.body);
    if (body is List) return List<Map<String, dynamic>>.from(body);
    return List<Map<String, dynamic>>.from((body as Map)['tasks'] ?? body);
  }

  /// POST /api/execute/dispatch → proper dispatch via task queue (same as web UI)
  /// command: 'go_to' | 'go_charge' | 'go_wait' | 'stop' | 'resume'
  static Future<Map<String, dynamic>> dispatchCommand({
    required String agvId,
    required String command,
    String? destNode,
    String? mapId,
    String? sessionId,
    String? sessionLabel,
    String? startNode,
  }) async {
    final base = await baseUrl;
    final response = await http
        .post(
          Uri.parse('$base/api/execute/dispatch'),
          headers: await _headers(json: true),
          body: jsonEncode({
            'agv_id':  agvId,
            'command': command,
            if (destNode != null)     'dest_node':      destNode,
            if (mapId != null)        'map_id':         mapId,
            if (sessionId != null)    'session_id':     sessionId,
            if (sessionLabel != null) 'session_label':  sessionLabel,
            if (startNode != null)    'start_node':     startNode,
          }),
        )
        .timeout(const Duration(seconds: 15));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// POST /api/execute/lifecycle-ack/{agvId} → confirm pickup or delivery done
  static Future<Map<String, dynamic>> lifecycleAck(String agvId) async {
    final base = await baseUrl;
    final response = await http
        .post(Uri.parse('$base/api/execute/lifecycle-ack/${Uri.encodeComponent(agvId)}'),
              headers: await _headers())
        .timeout(const Duration(seconds: 10));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// POST /api/tasks → create task (legacy, kept for history screen)
  static Future<Map<String, dynamic>> createTask({
    required String agvId,
    required String destination,
    String? mapId,
    String notes = '',
    String? sessionId,
    bool returnToCharge = false,
  }) async {
    final base = await baseUrl;
    final prefs = await SharedPreferences.getInstance();
    final operatorName = prefs.getString('name') ?? '';
    final operatorId   = prefs.getString('maNS') ?? '';

    final response = await http
        .post(
          Uri.parse('$base/api/tasks'),
          headers: await _headers(json: true),
          body: jsonEncode({
            'agv_id': agvId,
            'destination': destination,
            if (mapId != null)     'map_id':           mapId,
            'notes':               notes,
            if (operatorName.isNotEmpty) 'operator_name': operatorName,
            if (operatorId.isNotEmpty)   'operator_id':   operatorId,
            if (sessionId != null) 'session_id':       sessionId,
            if (returnToCharge)    'return_to_charge': true,
          }),
        )
        .timeout(const Duration(seconds: 15));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// POST /api/tasks/{taskId}/cancel
  static Future<void> cancelTask(String taskId) async {
    final base = await baseUrl;
    await http
        .post(Uri.parse('$base/api/tasks/$taskId/cancel'), headers: await _headers())
        .timeout(const Duration(seconds: 10));
  }

  // ── Map ──────────────────────────────────────────────────────────────────

  /// GET /api/maps/list → [{id, name}, ...]
  static Future<List<Map<String, dynamic>>> getMaps() async {
    final base = await baseUrl;
    final response = await http
        .get(Uri.parse('$base/api/maps/list'), headers: await _headers())
        .timeout(const Duration(seconds: 10));
    _assertOk(response);
    final body = jsonDecode(response.body);
    if (body is List) return List<Map<String, dynamic>>.from(body);
    return List<Map<String, dynamic>>.from((body as Map)['maps'] ?? []);
  }

  /// GET /api/execute/team-nodes?map_id=X → {teams: [{node_id, name, team, label}, ...]}
  static Future<List<Map<String, dynamic>>> getTeamNodes(String mapId) async {
    final base = await baseUrl;
    final uri = Uri.parse('$base/api/execute/team-nodes').replace(queryParameters: {'map_id': mapId});
    final response = await http.get(uri, headers: await _headers()).timeout(const Duration(seconds: 10));
    _assertOk(response);
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return List<Map<String, dynamic>>.from(body['teams'] ?? []);
  }

  /// GET /api/maps/{mapId} → {robot_points: [{name_id, name, x, y, ...}], ...}
  static Future<Map<String, dynamic>> getMapDetail(String mapId) async {
    final base = await baseUrl;
    final response = await http
        .get(Uri.parse('$base/api/maps/$mapId'), headers: await _headers())
        .timeout(const Duration(seconds: 15));
    _assertOk(response);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  static void _assertOk(http.Response r) {
    if (r.statusCode < 200 || r.statusCode >= 300) {
      String detail = '';
      try {
        final body = jsonDecode(r.body);
        detail = body['detail'] ?? body['message'] ?? '';
      } catch (_) {}
      throw ApiException(r.statusCode, detail.isNotEmpty ? detail : 'HTTP ${r.statusCode}');
    }
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String message;
  const ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}
