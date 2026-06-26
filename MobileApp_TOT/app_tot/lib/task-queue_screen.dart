import 'dart:async';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'services/api_service.dart';
import 'services/ws_service.dart';

class TaskQueueScreen extends StatefulWidget {
  const TaskQueueScreen({super.key});

  @override
  State<TaskQueueScreen> createState() => _TaskQueueScreenState();
}

class _TaskQueueScreenState extends State<TaskQueueScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  List<Map<String, dynamic>> _tasks = [];
  bool _isLoading = true;
  String _lastUpdated = '';
  Timer? _refreshTimer;

  static const _tabs = ['Tất cả', 'Chờ', 'Đang chạy', 'Hoàn thành', 'Thất bại'];
  static const _statusFilters = ['all', 'pending', 'running', 'done', 'failed'];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: _tabs.length, vsync: this);
    _tabController.addListener(() {
      if (!_tabController.indexIsChanging) _fetchTasks();
    });
    _fetchTasks();
    _refreshTimer = Timer.periodic(const Duration(seconds: 15), (_) => _fetchTasks());
    WsService.instance.addListener(_onWsMessage);
    WsService.instance.start();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _refreshTimer?.cancel();
    WsService.instance.removeListener(_onWsMessage);
    super.dispose();
  }

  void _onWsMessage(Map<String, dynamic> msg) {
    Future.delayed(const Duration(milliseconds: 800), _fetchTasks);
  }

  Future<void> _fetchTasks() async {
    if (!mounted) return;
    final idx = _tabController.index;
    final status = _statusFilters[idx];
    try {
      final tasks = await ApiService.getTasks(limit: 200, status: status == 'all' ? null : status);
      if (!mounted) return;
      setState(() {
        _tasks = tasks;
        _isLoading = false;
        _lastUpdated = DateFormat('HH:mm:ss').format(DateTime.now());
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
    }
  }

  Future<void> _cancelTask(String taskId, String agvId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Hủy task'),
        content: Text('Hủy task của AGV $agvId?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Không')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Hủy', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ApiService.cancelTask(taskId);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã hủy task'), backgroundColor: Colors.orange),
      );
      _fetchTasks();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Lỗi: $e'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F7FA),
      appBar: AppBar(
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              colors: [Color(0xFF1565C0), Color(0xFF42A5F5)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
        ),
        title: const Text('Danh sách lệnh', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: () {
              setState(() => _isLoading = true);
              _fetchTasks();
            },
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: Colors.white,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          tabs: _tabs.map((t) => Tab(text: t)).toList(),
        ),
      ),
      body: Column(
        children: [
          // Stats row
          Container(
            color: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                Text(
                  'Tổng: ${_tasks.length} task',
                  style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 13),
                ),
                const Spacer(),
                Text(
                  'Cập nhật: $_lastUpdated',
                  style: TextStyle(fontSize: 11, color: Colors.grey[500]),
                ),
              ],
            ),
          ),
          // Task list
          Expanded(
            child: _isLoading && _tasks.isEmpty
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _fetchTasks,
                    child: _tasks.isEmpty
                        ? ListView(
                            children: const [
                              SizedBox(height: 80),
                              Center(child: Text('Không có task nào', style: TextStyle(color: Colors.grey))),
                            ],
                          )
                        : ListView.builder(
                            padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
                            itemCount: _tasks.length,
                            itemBuilder: (ctx, i) => _TaskCard(
                              task: _tasks[i],
                              onCancel: _cancelTask,
                            ),
                          ),
                  ),
          ),
        ],
      ),
    );
  }
}

// ── Task Card ─────────────────────────────────────────────────────────────────

class _TaskCard extends StatelessWidget {
  final Map<String, dynamic> task;
  final Future<void> Function(String taskId, String agvId) onCancel;

  const _TaskCard({required this.task, required this.onCancel});

  Color _statusColor(String status) {
    switch (status) {
      case 'running':
        return Colors.blue;
      case 'done':
      case 'completed':
        return Colors.green;
      case 'failed':
        return Colors.red;
      case 'cancelled':
        return Colors.grey;
      case 'pending':
        return Colors.orange;
      default:
        return Colors.blueGrey;
    }
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'running':
        return 'Đang chạy';
      case 'done':
      case 'completed':
        return 'Hoàn thành';
      case 'failed':
        return 'Thất bại';
      case 'cancelled':
        return 'Đã hủy';
      case 'pending':
        return 'Chờ';
      default:
        return status;
    }
  }

  String _formatTs(dynamic ts) {
    if (ts == null) return '—';
    try {
      if (ts is num) {
        return DateFormat('HH:mm:ss dd/MM').format(
          DateTime.fromMillisecondsSinceEpoch((ts * 1000).round()),
        );
      }
      final dt = DateTime.tryParse(ts.toString())?.toLocal();
      if (dt == null) return ts.toString();
      return DateFormat('HH:mm:ss dd/MM').format(dt);
    } catch (_) {
      return ts.toString();
    }
  }

  @override
  Widget build(BuildContext context) {
    final taskId = task['task_id']?.toString() ?? task['cmd_id']?.toString() ?? '';
    final agvId  = task['agv_id']?.toString() ?? '—';
    final dest   = task['destination']?.toString() ?? task['dest_node']?.toString() ?? '—';
    final status = task['status']?.toString() ?? '';
    final cmdLabel  = task['command_label']?.toString() ?? task['command']?.toString() ?? 'go_to';
    final queuedAt  = _formatTs(task['queued_at'] ?? task['created_at']);
    final statusColor = _statusColor(status);
    final canCancel   = status == 'pending' || status == 'queued';

    final operatorName = (task['operator_name'] != null && task['operator_name'].toString().isNotEmpty)
        ? task['operator_name'].toString()
        : null;
    final operatorId = (task['operator_id'] != null && task['operator_id'].toString().isNotEmpty)
        ? task['operator_id'].toString()
        : null;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Left accent bar
            Container(
              width: 4,
              decoration: BoxDecoration(
                color: statusColor,
                borderRadius: const BorderRadius.horizontal(left: Radius.circular(12)),
              ),
            ),

            // ── Task info (left column) ──────────────────────────────────
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(10, 10, 8, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Text(agvId,
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                      const SizedBox(width: 6),
                      Icon(Icons.arrow_forward, size: 13, color: Colors.grey[400]),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(dest,
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
                            overflow: TextOverflow.ellipsis),
                      ),
                    ]),
                    const SizedBox(height: 5),
                    Row(children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                        decoration: BoxDecoration(
                          color: statusColor.withOpacity(0.12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(_statusLabel(status),
                            style: TextStyle(fontSize: 11, color: statusColor, fontWeight: FontWeight.bold)),
                      ),
                      const SizedBox(width: 8),
                      Text(cmdLabel, style: TextStyle(fontSize: 11, color: Colors.grey[500])),
                    ]),
                    const SizedBox(height: 5),
                    Text('Tạo lúc: $queuedAt',
                        style: TextStyle(fontSize: 11, color: Colors.grey[500])),
                  ],
                ),
              ),
            ),

            // ── Operator column (right) ──────────────────────────────────
            if (operatorName != null || operatorId != null)
              Container(
                width: 110,
                decoration: BoxDecoration(
                  color: Colors.blueGrey[50],
                  border: Border(left: BorderSide(color: Colors.grey[200]!)),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Icon(Icons.person, size: 12, color: Colors.blueGrey[400]),
                      const SizedBox(width: 3),
                      Expanded(
                        child: Text(
                          operatorName ?? '—',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: Colors.blueGrey[700],
                          ),
                          overflow: TextOverflow.ellipsis,
                          maxLines: 2,
                        ),
                      ),
                    ]),
                    const SizedBox(height: 4),
                    Row(children: [
                      Icon(Icons.badge_outlined, size: 12, color: Colors.blueGrey[300]),
                      const SizedBox(width: 3),
                      Expanded(
                        child: Text(
                          operatorId ?? '—',
                          style: TextStyle(fontSize: 11, color: Colors.blueGrey[500]),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ]),
                  ],
                ),
              ),

            // Cancel button
            if (canCancel)
              Padding(
                padding: const EdgeInsets.only(right: 4),
                child: Center(
                  child: IconButton(
                    icon: const Icon(Icons.cancel_outlined, color: Colors.red, size: 22),
                    tooltip: 'Hủy task',
                    onPressed: () => onCancel(taskId, agvId),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
