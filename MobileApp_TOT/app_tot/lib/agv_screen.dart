import 'dart:async';
import 'dart:math' show Random;
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'services/api_service.dart';
import 'services/ws_service.dart';

class AGVManagementScreen extends StatefulWidget {
  const AGVManagementScreen({super.key});

  @override
  State<AGVManagementScreen> createState() => _AGVManagementScreenState();
}

class _AGVManagementScreenState extends State<AGVManagementScreen> {
  List<Map<String, dynamic>> _agvs = [];
  bool _isLoading = true;
  String _lastUpdated = '';
  Timer? _refreshTimer;

  // Selected factory (map)
  String? _selectedMapId;
  String? _selectedMapName;

  // cache: mapId → nodes
  final Map<String, List<Map<String, dynamic>>> _mapNodes = {};
  final Map<String, List<Map<String, dynamic>>> _teamNodes = {};
  // cache: mapId → {nodeId: displayLabel}
  final Map<String, Map<String, String>> _nodeLabelMap = {};

  @override
  void initState() {
    super.initState();
    _loadSelectedMap().then((_) => _fetchAgvs());
    _refreshTimer =
        Timer.periodic(const Duration(seconds: 3), (_) => _fetchAgvs());
    WsService.instance.addListener(_onWsMessage);
    WsService.instance.start();
  }

  Future<void> _loadSelectedMap() async {
    final prefs = await SharedPreferences.getInstance();
    final mapId = prefs.getString('selected_map_id');
    if (mapId == null || mapId.isEmpty) {
      if (mounted) setState(() { _selectedMapId = null; _isLoading = false; });
      return;
    }
    // Try to get map name from cached maps list, or just use the id
    if (mounted) setState(() => _selectedMapId = mapId);
    try {
      final maps = await ApiService.getMaps();
      final match = maps.firstWhere(
        (m) => (m['id']?.toString() ?? m['map_id']?.toString()) == mapId,
        orElse: () => {},
      );
      if (mounted && match.isNotEmpty) {
        setState(() => _selectedMapName = match['name']?.toString());
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    WsService.instance.removeListener(_onWsMessage);
    super.dispose();
  }

  // Track which AGVs have been notified for charging (avoid duplicates)
  final Set<String> _notifiedCharging = {};

  void _onWsMessage(Map<String, dynamic> _) =>
      Future.delayed(const Duration(milliseconds: 300), _fetchAgvs);

  Future<void> _fetchAgvs() async {
    if (!mounted) return;
    if (_selectedMapId == null) return;
    try {
      final data = await ApiService.getAgvList();
      if (!mounted) return;
      final all = List<Map<String, dynamic>>.from(data['agvs'] ?? []);
      final agvs = all
          .where((a) => a['map_id']?.toString() == _selectedMapId)
          .toList();
      if (!_nodeLabelMap.containsKey(_selectedMapId)) {
        _buildNodeLabelMap(_selectedMapId!);
      }

      // Detect AGV arriving at charging station (polling fallback for WS)
      for (final agv in agvs) {
        final agvId = agv['agv_id']?.toString() ?? '';
        final lifecycle = agv['task_lifecycle']?.toString() ?? '';
        if (lifecycle == 'charging' && !_notifiedCharging.contains(agvId)) {
          _notifiedCharging.add(agvId);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Row(children: [
                  const Icon(Icons.check_circle, color: Colors.white, size: 20),
                  const SizedBox(width: 10),
                  Expanded(child: Text(
                    '$agvId — Giao hàng hoàn tất, xe đã về trạm sạc',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  )),
                ]),
                backgroundColor: const Color(0xFF2E7D32),
                duration: const Duration(seconds: 5),
                behavior: SnackBarBehavior.floating,
              ),
            );
          }
        } else if (lifecycle != 'charging') {
          _notifiedCharging.remove(agvId);
        }
      }

      setState(() {
        _agvs = agvs;
        _lastUpdated = DateFormat('HH:mm:ss').format(DateTime.now());
        _isLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _buildNodeLabelMap(String mapId) async {
    final labels = <String, String>{};
    try {
      final team = await _getTeamNodes(mapId);
      for (final t in team) {
        final id = t['node_id']?.toString() ?? '';
        final teamNum = t['team']?.toString() ?? '';
        final name = t['name']?.toString() ?? '';
        if (id.isNotEmpty) {
          labels[id] = name.isNotEmpty ? 'Tổ $teamNum — $name' : 'Tổ $teamNum';
        }
      }
      final nodes = await _getNodes(mapId);
      for (final n in nodes) {
        final id = n['name_id']?.toString() ?? '';
        if (id.isEmpty || labels.containsKey(id)) continue;
        final name = (n['name']?.toString() ?? '').trim();
        final lower = name.toLowerCase();
        if (lower.contains('sạc') || lower.contains('charge') || lower.contains('sac')) {
          labels[id] = 'Trạm sạc';
        } else if (lower.contains('chờ') || lower.contains('wait') || lower.contains('cho') || lower.contains('standby')) {
          labels[id] = 'Khu chờ';
        } else if (name.isNotEmpty && name != id) {
          labels[id] = name;
        }
      }
    } catch (_) {}
    if (mounted) setState(() => _nodeLabelMap[mapId] = labels);
  }

  String _locationLabel(Map<String, dynamic> agv) {
    final node = agv['current_node']?.toString() ?? '';
    if (node.isEmpty || node == 'null') return '—';
    final mapId = agv['map_id']?.toString() ?? '';
    final label = _nodeLabelMap[mapId]?[node];
    return label ?? 'Node $node';
  }

  IconData _locationIcon(Map<String, dynamic> agv) {
    final label = _locationLabel(agv);
    if (label.startsWith('Tổ')) return Icons.factory;
    if (label == 'Trạm sạc') return Icons.battery_charging_full;
    if (label == 'Khu chờ') return Icons.pause_circle_outline;
    return Icons.location_on;
  }

  Future<List<Map<String, dynamic>>> _getNodes(String? mapId) async {
    if (mapId == null || mapId.isEmpty) return [];
    if (_mapNodes.containsKey(mapId)) return _mapNodes[mapId]!;
    try {
      final data = await ApiService.getMapDetail(mapId);
      final nodes =
          List<Map<String, dynamic>>.from(data['robot_points'] ?? []);
      _mapNodes[mapId] = nodes;
      return nodes;
    } catch (_) {
      return [];
    }
  }

  Future<List<Map<String, dynamic>>> _getTeamNodes(String? mapId) async {
    if (mapId == null || mapId.isEmpty) return [];
    if (_teamNodes.containsKey(mapId)) return _teamNodes[mapId]!;
    try {
      final nodes = await ApiService.getTeamNodes(mapId);
      _teamNodes[mapId] = nodes;
      return nodes;
    } catch (_) {
      return [];
    }
  }

  // ── Status helpers ──────────────────────────────────────────────────────────

  String _statusLabel(Map<String, dynamic> agv) {
    if (agv['connection'] == 'OFFLINE') return 'Offline';
    if (agv['driving'] == true) return 'Đang chạy';
    if (agv['paused'] == true) return 'Tạm dừng';
    if (agv['is_busy'] == true) return 'Bận';
    return 'Sẵn sàng';
  }

  Color _statusColor(Map<String, dynamic> agv) {
    if (agv['connection'] == 'OFFLINE') return Colors.grey;
    if (agv['driving'] == true) return const Color(0xFF2196F3);
    if (agv['paused'] == true) return Colors.orange;
    if (agv['is_busy'] == true) return Colors.amber[700]!;
    return const Color(0xFF4CAF50);
  }

  // ── Actions ─────────────────────────────────────────────────────────────────

  Future<void> _showSendOrderDialog(Map<String, dynamic> agv) async {
    final agvId = agv['agv_id']?.toString() ?? '';
    final mapId = agv['map_id']?.toString();
    final Set<String> selectedTeamNodes = {};
    String? selectedExtraNode;
    List<Map<String, dynamic>> teamNodes = [];
    List<Map<String, dynamic>> allNodes = [];
    bool loading = true;

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setS) {
          if (loading) {
            Future.wait([_getTeamNodes(mapId), _getNodes(mapId)]).then((r) {
              if (ctx.mounted) setS(() { teamNodes = r[0]; allNodes = r[1]; loading = false; });
            });
          }
          final teamIds = teamNodes.map((t) => t['node_id']?.toString()).toSet();
          final extraNodes = allNodes.where((n) => !teamIds.contains(n['name_id']?.toString())).toList();
          final total = selectedTeamNodes.length + (selectedExtraNode != null ? 1 : 0);

          return Dialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(ctx).size.height * 0.8, maxWidth: 480),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.fromLTRB(20, 16, 16, 12),
                    decoration: const BoxDecoration(
                      gradient: LinearGradient(colors: [Color(0xFF1565C0), Color(0xFF42A5F5)]),
                      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                    ),
                    child: Row(children: [
                      const Icon(Icons.send, color: Colors.white, size: 20),
                      const SizedBox(width: 8),
                      Expanded(child: Text('Gửi lệnh — $agvId',
                          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold))),
                      if (mapId != null)
                        Text('Map $mapId', style: const TextStyle(color: Colors.white70, fontSize: 11)),
                    ]),
                  ),
                  Flexible(
                    child: loading
                        ? const SizedBox(height: 100, child: Center(child: CircularProgressIndicator()))
                        : SingleChildScrollView(
                            padding: const EdgeInsets.all(16),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              if (teamNodes.isNotEmpty) ...[
                                Row(children: [
                                  const Icon(Icons.factory, size: 16, color: Color(0xFF1565C0)),
                                  const SizedBox(width: 6),
                                  const Text('Điểm giao hàng theo Tổ',
                                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Color(0xFF1565C0))),
                                  const Spacer(),
                                  Text('chọn nhiều', style: TextStyle(fontSize: 10, color: Colors.grey[500])),
                                ]),
                                const SizedBox(height: 8),
                                ...teamNodes.map((t) {
                                  final nodeId = t['node_id']?.toString() ?? '';
                                  final teamNum = t['team']?.toString() ?? '';
                                  final name = t['name']?.toString() ?? '';
                                  final checked = selectedTeamNodes.contains(nodeId);
                                  return InkWell(
                                    onTap: () => setS(() => checked ? selectedTeamNodes.remove(nodeId) : selectedTeamNodes.add(nodeId)),
                                    borderRadius: BorderRadius.circular(8),
                                    child: Container(
                                      margin: const EdgeInsets.only(bottom: 6),
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                                      decoration: BoxDecoration(
                                        color: checked ? const Color(0xFF1565C0).withOpacity(0.08) : Colors.grey[50],
                                        borderRadius: BorderRadius.circular(8),
                                        border: Border.all(color: checked ? const Color(0xFF1565C0) : Colors.grey[300]!),
                                      ),
                                      child: Row(children: [
                                        Container(
                                          width: 28, height: 28,
                                          decoration: BoxDecoration(
                                            color: checked ? const Color(0xFF1565C0) : Colors.grey[200],
                                            borderRadius: BorderRadius.circular(6),
                                          ),
                                          child: Center(child: Text(teamNum,
                                              style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold,
                                                  color: checked ? Colors.white : Colors.grey[600]))),
                                        ),
                                        const SizedBox(width: 10),
                                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                          Text('Tổ $teamNum', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13,
                                              color: checked ? const Color(0xFF1565C0) : Colors.black87)),
                                          if (name.isNotEmpty) Text(name, style: TextStyle(fontSize: 11, color: Colors.grey[500])),
                                        ])),
                                        Text('Node $nodeId', style: TextStyle(fontSize: 10, color: Colors.grey[400])),
                                        const SizedBox(width: 6),
                                        Icon(checked ? Icons.check_box : Icons.check_box_outline_blank,
                                            color: checked ? const Color(0xFF1565C0) : Colors.grey[400], size: 20),
                                      ]),
                                    ),
                                  );
                                }),
                                const SizedBox(height: 12),
                                const Divider(),
                                const SizedBox(height: 4),
                              ],
                              Row(children: [
                                const Icon(Icons.place, size: 16, color: Colors.grey),
                                const SizedBox(width: 6),
                                Text(teamNodes.isEmpty ? 'Chọn điểm đến' : 'Điểm khác (tuỳ chọn)',
                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                              ]),
                              const SizedBox(height: 8),
                              (extraNodes.isEmpty && allNodes.isEmpty)
                                  ? Text('Không tìm thấy node nào.', style: TextStyle(color: Colors.red[300]))
                                  : DropdownButtonFormField<String>(
                                      isExpanded: true,
                                      decoration: InputDecoration(
                                        hintText: 'Chọn node...',
                                        border: const OutlineInputBorder(),
                                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                                        suffixIcon: selectedExtraNode != null
                                            ? IconButton(icon: const Icon(Icons.clear, size: 18),
                                                onPressed: () => setS(() => selectedExtraNode = null))
                                            : null,
                                      ),
                                      value: selectedExtraNode,
                                      items: (extraNodes.isEmpty ? allNodes : extraNodes).map((n) {
                                        final id = n['name_id']?.toString() ?? '';
                                        final name = n['name']?.toString() ?? '';
                                        return DropdownMenuItem(value: id,
                                            child: Text(name.isNotEmpty ? '$id — $name' : id, overflow: TextOverflow.ellipsis));
                                      }).toList(),
                                      onChanged: (v) => setS(() => selectedExtraNode = v),
                                    ),
                            ]),
                          ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.grey[200]!))),
                    child: Row(children: [
                      if (total > 0)
                        Text('Đã chọn $total điểm', style: const TextStyle(fontSize: 12, color: Color(0xFF1565C0))),
                      const Spacer(),
                      TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Hủy')),
                      const SizedBox(width: 8),
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF1565C0), foregroundColor: Colors.white),
                        icon: const Icon(Icons.send, size: 16),
                        label: Text(total > 1 ? 'Gửi $total lệnh' : 'Gửi lệnh'),
                        onPressed: (loading || total == 0) ? null : () {
                          // Giữ lại team node objects để hiện tên Tổ trong notification
                          final selectedTeamObjs = teamNodes
                              .where((t) => selectedTeamNodes.contains(t['node_id']?.toString()))
                              .toList();
                          final dests = [
                            ...selectedTeamObjs.map((t) => t['node_id']!.toString()),
                            if (selectedExtraNode != null) selectedExtraNode!,
                          ];
                          Navigator.pop(ctx);
                          _sendMultipleOrders(agvId, dests, mapId,
                              teamNodeObjects: selectedTeamObjs);
                        },
                      ),
                    ]),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  // Sinh session ID ngắn gọn cho 1 lượt gửi lệnh
  String _newSessionId() {
    final r = Random();
    final chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    return List.generate(12, (_) => chars[r.nextInt(chars.length)]).join();
  }

  // Build display label cho 1 team node
  String _teamLabel(Map<String, dynamic> t) {
    final num  = t['team']?.toString() ?? '';
    final name = (t['name']?.toString() ?? '').trim();
    if (num.isEmpty) return 'Node ${t['node_id'] ?? '?'}';
    return name.isNotEmpty ? 'Tổ $num — $name' : 'Tổ $num';
  }

  void _showDeliveryNotification(String agvId, String destDescription) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(children: [
          const Icon(Icons.local_shipping, color: Colors.white, size: 22),
          const SizedBox(width: 10),
          Expanded(child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('$agvId — Đang đi cấp hàng',
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
              Text(destDescription,
                style: const TextStyle(fontSize: 12, color: Colors.white70)),
            ],
          )),
        ]),
        backgroundColor: const Color(0xFF1565C0),
        duration: const Duration(seconds: 5),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  Future<void> _sendMultipleOrders(
    String agvId,
    List<String> dests,
    String? mapId, {
    List<Map<String, dynamic>> teamNodeObjects = const [],
  }) async {
    if (dests.isEmpty) return;
    final sessionId = _newSessionId();

    // Build human-readable label for notification
    final labels = <String>[];
    for (final d in dests) {
      final t = teamNodeObjects.firstWhere(
        (x) => x['node_id']?.toString() == d,
        orElse: () => {},
      );
      labels.add(t.isNotEmpty ? _teamLabel(t) : 'Node $d');
    }
    final destDesc = labels.join(', ');
    final sessionLabel = 'Mobile → $destDesc';

    if (dests.length == 1) {
      await _sendOrder(agvId, dests.first, mapId,
          addCharge: true, sessionId: sessionId, sessionLabel: sessionLabel,
          teamLabel: labels.first);
      return;
    }

    _showSnack('Đang gửi ${dests.length} lệnh…', Colors.blue);
    int ok = 0, fail = 0;
    for (final dest in dests) {
      try {
        await ApiService.dispatchCommand(
          agvId: agvId,
          command: 'go_to',
          destNode: dest,
          mapId: mapId,
          sessionId: sessionId,
          sessionLabel: sessionLabel,
        );
        ok++;
      } catch (_) { fail++; }
    }
    // Tự về sạc sau khi hoàn thành hết lệnh giao hàng
    try {
      await ApiService.dispatchCommand(
        agvId: agvId,
        command: 'go_charge',
        mapId: mapId,
        sessionId: sessionId,
        sessionLabel: sessionLabel,
      );
    } catch (_) {}

    if (ok > 0) {
      _showDeliveryNotification(agvId, destDesc);
    } else {
      _showSnack('$ok thành công, $fail thất bại', Colors.orange);
    }
    _fetchAgvs();
  }

  Future<void> _sendOrder(String agvId, String dest, String? mapId,
      {bool addCharge = true, String? sessionId, String? sessionLabel,
       String? teamLabel}) async {
    _showSnack('Đang gửi lệnh…', Colors.blue);
    try {
      final sid = sessionId ?? _newSessionId();
      // teamLabel hoặc fallback node id
      final destDisplay = teamLabel ?? 'Node $dest';
      final slbl = sessionLabel ?? 'Mobile → $destDisplay';
      final r = await ApiService.dispatchCommand(
        agvId: agvId,
        command: 'go_to',
        destNode: dest,
        mapId: mapId,
        sessionId: sid,
        sessionLabel: slbl,
      );
      if (addCharge) {
        await ApiService.dispatchCommand(
          agvId: agvId,
          command: 'go_charge',
          mapId: mapId,
          sessionId: sid,
          sessionLabel: slbl,
        );
      }
      final s = r['status']?.toString() ?? '';
      if (s == 'dispatched' || s == 'queued') {
        _showDeliveryNotification(agvId, destDisplay);
      } else {
        _showSnack('$agvId: $s', Colors.orange);
      }
      _fetchAgvs();
    } on ApiException catch (e) {
      _showSnack('Lỗi API: ${e.message}', Colors.red);
    } catch (e) {
      _showSnack('Lỗi: $e', Colors.red);
    }
  }

  Future<void> _cancelOrder(String agvId) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Hủy lệnh'),
        content: Text('Hủy toàn bộ lệnh của $agvId?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Không')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Hủy lệnh', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.cancelOrder(agvId);
      _showSnack('Đã hủy lệnh của $agvId', Colors.orange);
      _fetchAgvs();
    } on ApiException catch (e) {
      _showSnack('Lỗi: ${e.message}', Colors.red);
    }
  }

  Future<void> _goCharge(String agvId) async {
    try {
      await ApiService.goCharge(agvId);
      _showSnack('$agvId → trạm sạc', Colors.green);
      _fetchAgvs();
    } on ApiException catch (e) { _showSnack('Lỗi: ${e.message}', Colors.red); }
  }

  Future<void> _goWait(String agvId) async {
    try {
      await ApiService.goWait(agvId);
      _showSnack('$agvId → khu chờ', Colors.green);
      _fetchAgvs();
    } on ApiException catch (e) { _showSnack('Lỗi: ${e.message}', Colors.red); }
  }

  void _showSnack(String msg, Color color) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: color, duration: const Duration(seconds: 4)),
    );
  }

  // ── Build ───────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final online = _agvs.where((a) => a['connection'] == 'ONLINE').length;
    final driving = _agvs.where((a) => a['driving'] == true).length;
    final factoryLabel = _selectedMapName ?? (_selectedMapId != null ? 'Map $_selectedMapId' : null);

    return Scaffold(
      backgroundColor: const Color(0xFFF0F4F8),
      appBar: AppBar(
        elevation: 0,
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              colors: [Color(0xFF1565C0), Color(0xFF1E88E5)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Quản lý AGV',
                style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 17)),
            if (factoryLabel != null)
              Text(factoryLabel,
                  style: const TextStyle(color: Colors.white70, fontSize: 11)),
          ],
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          if (WsService.instance.isConnected)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 18, horizontal: 4),
              child: Icon(Icons.wifi, color: Colors.greenAccent, size: 16),
            ),
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: () { setState(() => _isLoading = true); _fetchAgvs(); },
          ),
        ],
      ),
      body: _selectedMapId == null
          ? _buildNoFactoryPlaceholder()
          : Column(
        children: [
          // ── Summary bar ──
          Container(
            color: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            child: Row(children: [
              _StatChip(label: 'Tổng', value: '${_agvs.length}', color: Colors.blueGrey),
              const SizedBox(width: 8),
              _StatChip(label: 'Online', value: '$online', color: const Color(0xFF4CAF50)),
              const SizedBox(width: 8),
              _StatChip(label: 'Đang chạy', value: '$driving', color: const Color(0xFF2196F3)),
              const Spacer(),
              Icon(Icons.access_time, size: 12, color: Colors.grey[400]),
              const SizedBox(width: 3),
              Text(_lastUpdated, style: TextStyle(fontSize: 11, color: Colors.grey[400])),
            ]),
          ),
          const SizedBox(height: 1),

          // ── List ──
          Expanded(
            child: _isLoading && _agvs.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : _agvs.isEmpty
                    ? Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                        Icon(Icons.precision_manufacturing_outlined, size: 56, color: Colors.grey[300]),
                        const SizedBox(height: 12),
                        Text('Không có AGV nào thuộc nhà máy này', style: TextStyle(color: Colors.grey[400], fontSize: 15)),
                      ]))
                    : RefreshIndicator(
                        onRefresh: _fetchAgvs,
                        child: ListView.builder(
                          padding: const EdgeInsets.fromLTRB(12, 12, 12, 20),
                          itemCount: _agvs.length,
                          itemBuilder: (ctx, i) {
                            final agv = _agvs[i];
                            final mapId = agv['map_id']?.toString() ?? '';
                            // Hiện nhãn điểm đến của lệnh đang chạy
                            final runningCmd = agv['running_cmd'] as Map<String, dynamic>?;
                            final destNode = runningCmd?['dest_node']?.toString() ?? '';
                            final runningDestLabel = destNode.isNotEmpty
                                ? (_nodeLabelMap[mapId]?[destNode] ?? 'Node $destNode')
                                : null;
                            return _AgvCard(
                              agv: agv,
                              statusLabel: _statusLabel(agv),
                              statusColor: _statusColor(agv),
                              locationLabel: _locationLabel(agv),
                              locationIcon: _locationIcon(agv),
                              runningDestLabel: runningDestLabel,
                              onSendOrder: () => _showSendOrderDialog(agv),
                              onCancel: () => _cancelOrder(agv['agv_id']?.toString() ?? ''),
                              onCharge: () => _goCharge(agv['agv_id']?.toString() ?? ''),
                              onWait: () => _goWait(agv['agv_id']?.toString() ?? ''),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildNoFactoryPlaceholder() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.factory_outlined, size: 72, color: Colors.grey[300]),
            const SizedBox(height: 20),
            const Text(
              'Chưa chọn nhà máy',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E)),
            ),
            const SizedBox(height: 10),
            Text(
              'Vui lòng vào Cài đặt và chọn nhà máy\nđể xem danh sách AGV.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 14, color: Colors.grey[500], height: 1.5),
            ),
            const SizedBox(height: 28),
            ElevatedButton.icon(
              icon: const Icon(Icons.settings),
              label: const Text('Mở Cài đặt'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF1565C0),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              onPressed: () => Navigator.pop(context),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Stat chip ─────────────────────────────────────────────────────────────────

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _StatChip({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
          color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(20)),
      child: Row(children: [
        Text(label, style: TextStyle(fontSize: 11, color: color)),
        const SizedBox(width: 5),
        Text(value, style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: color)),
      ]),
    );
  }
}

// ── AGV Card ──────────────────────────────────────────────────────────────────

class _AgvCard extends StatefulWidget {
  final Map<String, dynamic> agv;
  final String statusLabel;
  final Color statusColor;
  final String locationLabel;
  final IconData locationIcon;
  final String? runningDestLabel;   // nhãn điểm đến hiện tại (e.g. "Tổ 3 — Cắt 2")
  final VoidCallback onSendOrder;
  final VoidCallback onCancel;
  final VoidCallback onCharge;
  final VoidCallback onWait;

  const _AgvCard({
    required this.agv,
    required this.statusLabel,
    required this.statusColor,
    required this.locationLabel,
    required this.locationIcon,
    this.runningDestLabel,
    required this.onSendOrder,
    required this.onCancel,
    required this.onCharge,
    required this.onWait,
  });

  @override
  State<_AgvCard> createState() => _AgvCardState();
}

class _AgvCardState extends State<_AgvCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final agv = widget.agv;
    final agvId = agv['agv_id']?.toString() ?? '';
    final agvType = agv['agv_type']?.toString() ?? '';
    final battery = (agv['battery'] as num?)?.toInt();
    final isOffline = agv['connection'] == 'OFFLINE';
    final isDriving = agv['driving'] == true;
    final queueSize = (agv['queue_size'] as num?)?.toInt() ?? 0;
    final batteryLow = agv['battery_low'] == true;
    final runningCmd = agv['running_cmd'] as Map<String, dynamic>?;

    final batteryColor = batteryLow
        ? Colors.red
        : battery != null && battery > 50
            ? const Color(0xFF4CAF50)
            : Colors.orange;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
              color: widget.statusColor.withOpacity(0.08),
              blurRadius: 8,
              offset: const Offset(0, 2)),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Left accent bar
              Container(width: 4, color: widget.statusColor),

              // Content
              Expanded(
                child: Column(
                  children: [
                    // ── Header ──
                    InkWell(
                      onTap: () => setState(() => _expanded = !_expanded),
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(14, 12, 12, 10),
                        child: Row(children: [
                          // Status dot
                          Container(
                            width: 9, height: 9,
                            decoration: BoxDecoration(
                              color: widget.statusColor,
                              shape: BoxShape.circle,
                              boxShadow: [BoxShadow(color: widget.statusColor.withOpacity(0.4), blurRadius: 4)],
                            ),
                          ),
                          const SizedBox(width: 10),

                          // Name + type
                          Expanded(
                            child: Row(children: [
                              Text(agvId,
                                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF1A1A2E))),
                              const SizedBox(width: 7),
                              _TypeBadge(agvType),
                              if (isDriving) ...[
                                const SizedBox(width: 6),
                                _StatusBadge(label: 'Đang chạy', color: const Color(0xFF2196F3)),
                              ] else if (!isOffline) ...[
                                const SizedBox(width: 6),
                                _StatusBadge(label: widget.statusLabel, color: widget.statusColor),
                              ],
                            ]),
                          ),

                          // Queue badge
                          if (queueSize > 0) ...[
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                              decoration: BoxDecoration(
                                color: Colors.orange.withOpacity(0.15),
                                borderRadius: BorderRadius.circular(10),
                                border: Border.all(color: Colors.orange.withOpacity(0.4)),
                              ),
                              child: Row(children: [
                                const Icon(Icons.queue, size: 11, color: Colors.orange),
                                const SizedBox(width: 3),
                                Text('$queueSize', style: const TextStyle(fontSize: 11, color: Colors.orange, fontWeight: FontWeight.bold)),
                              ]),
                            ),
                            const SizedBox(width: 6),
                          ],

                          Icon(_expanded ? Icons.expand_less : Icons.expand_more,
                              color: Colors.grey[400], size: 20),
                        ]),
                      ),
                    ),

                    // ── Info row ──
                    Container(
                      padding: const EdgeInsets.fromLTRB(14, 6, 14, 10),
                      child: Row(children: [
                        // Location
                        Icon(widget.locationIcon, size: 13, color: Colors.grey[500]),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(widget.locationLabel,
                              style: TextStyle(fontSize: 12, color: Colors.grey[600], fontWeight: FontWeight.w500),
                              overflow: TextOverflow.ellipsis),
                        ),

                        // Battery
                        if (battery != null) ...[
                          const SizedBox(width: 8),
                          Icon(batteryLow ? Icons.battery_alert : Icons.battery_full,
                              size: 13, color: batteryColor),
                          const SizedBox(width: 3),
                          SizedBox(
                            width: 40,
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(3),
                              child: LinearProgressIndicator(
                                value: battery / 100.0,
                                minHeight: 6,
                                backgroundColor: Colors.grey[200],
                                valueColor: AlwaysStoppedAnimation(batteryColor),
                              ),
                            ),
                          ),
                          const SizedBox(width: 4),
                          Text('$battery%',
                              style: TextStyle(fontSize: 11, color: batteryColor, fontWeight: FontWeight.w600)),
                        ],
                      ]),
                    ),

                    // ── Running command + delivery destination ──
                    if (runningCmd != null || widget.runningDestLabel != null)
                      Container(
                        margin: const EdgeInsets.fromLTRB(14, 0, 14, 8),
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1565C0).withOpacity(0.06),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFF1565C0).withOpacity(0.18)),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (runningCmd != null)
                              Row(children: [
                                const Icon(Icons.play_arrow, size: 13, color: Color(0xFF2196F3)),
                                const SizedBox(width: 5),
                                Expanded(
                                  child: Text(
                                    runningCmd['command_label']?.toString() ?? runningCmd['command']?.toString() ?? '',
                                    style: const TextStyle(fontSize: 11, color: Color(0xFF2196F3)),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              ]),
                            // Delivery destination badge
                            if (widget.runningDestLabel != null) ...[
                              if (runningCmd != null) const SizedBox(height: 4),
                              Row(children: [
                                const Icon(Icons.local_shipping, size: 13, color: Color(0xFF1565C0)),
                                const SizedBox(width: 5),
                                const Text('Đang đi cấp: ',
                                    style: TextStyle(fontSize: 11, color: Color(0xFF1565C0), fontWeight: FontWeight.w500)),
                                Expanded(
                                  child: Text(
                                    widget.runningDestLabel!,
                                    style: const TextStyle(
                                      fontSize: 12,
                                      color: Color(0xFF1565C0),
                                      fontWeight: FontWeight.bold,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              ]),
                            ],
                          ],
                        ),
                      ),


                    // ── Actions (expanded) ──
                    if (_expanded)
                      Container(
                        padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF8FAFF),
                          border: Border(top: BorderSide(color: Colors.grey[100]!)),
                        ),
                        child: Row(children: [
                          _ActionBtn(label: 'Gửi lệnh', icon: Icons.send, color: const Color(0xFF1565C0),
                              onPressed: isOffline ? null : widget.onSendOrder),
                          const SizedBox(width: 6),
                          _ActionBtn(label: 'Hủy lệnh', icon: Icons.cancel_outlined, color: Colors.red,
                              onPressed: isOffline ? null : widget.onCancel),
                          const SizedBox(width: 6),
                          _ActionBtn(label: 'Về sạc', icon: Icons.battery_charging_full, color: const Color(0xFF4CAF50),
                              onPressed: isOffline ? null : widget.onCharge),
                          const SizedBox(width: 6),
                          _ActionBtn(label: 'Khu chờ', icon: Icons.pause_circle_outline, color: Colors.orange,
                              onPressed: isOffline ? null : widget.onWait),
                        ]),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Sub-widgets ───────────────────────────────────────────────────────────────

class _TypeBadge extends StatelessWidget {
  final String type;
  const _TypeBadge(this.type);

  @override
  Widget build(BuildContext context) {
    final isLine = type == 'LINE';
    final color = isLine ? const Color(0xFF7B1FA2) : const Color(0xFF00796B);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
          color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(5)),
      child: Text(type, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.bold)),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final String label;
  final Color color;
  const _StatusBadge({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
          color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(10)),
      child: Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
    );
  }
}

class _ActionBtn extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onPressed;
  const _ActionBtn({required this.label, required this.icon, required this.color, this.onPressed});

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    return Expanded(
      child: Material(
        color: disabled ? Colors.grey[100] : color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(9),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(9),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 9),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(9),
              border: Border.all(color: disabled ? Colors.grey[200]! : color.withOpacity(0.25)),
            ),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(icon, size: 18, color: disabled ? Colors.grey[400] : color),
              const SizedBox(height: 3),
              Text(label, style: TextStyle(fontSize: 10, color: disabled ? Colors.grey[400] : color,
                  fontWeight: FontWeight.w600)),
            ]),
          ),
        ),
      ),
    );
  }
}
