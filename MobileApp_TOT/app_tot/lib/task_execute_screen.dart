import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';

class TaskExecutedScreen extends StatefulWidget {
  const TaskExecutedScreen({Key? key}) : super(key: key);

  @override
  _TaskExecutedScreenState createState() => _TaskExecutedScreenState();
}

class _TaskExecutedScreenState extends State<TaskExecutedScreen> with TickerProviderStateMixin {
  List<Map<String, dynamic>> _originalTasks = [];
  List<Map<String, dynamic>> _displayedTasks = [];
  TabController? _dateTabController;
  final TextEditingController _searchController = TextEditingController();
  bool isLoading = true;
  String? errorMessage;
  List<String> dateRange = [];
  int fixedDays = 30;
  late String todayDate;
  String? selectedTabDate;
  Set<String> _selectedTeams = {};

  @override
  void initState() {
    super.initState();
    _updateDateRange();
    _updateTabController();
    _fetchTasks();
    _searchController.addListener(() {
      if (mounted) {
        _filterTasks();
      }
    });
  }

  void _updateDateRange() {
    final today = DateTime.now().toLocal();
    todayDate = "${today.year}-${today.month.toString().padLeft(2, '0')}-${today.day.toString().padLeft(2, '0')}";
    dateRange = List.generate(fixedDays, (index) {
      final date = today.add(Duration(days: index));
      return "${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}";
    });
    print('Updated dateRange: $dateRange');
  }

  void _updateTabController() {
    if (dateRange.isEmpty) {
      print('dateRange is empty, skipping TabController update');
      return;
    }

    _dateTabController?.dispose();
    _dateTabController = TabController(
      length: dateRange.length,
      vsync: this,
    );
    _dateTabController!.addListener(() {
      if (!_dateTabController!.indexIsChanging && mounted) {
        setState(() {
          selectedTabDate = dateRange[_dateTabController!.index];
        });
      }
    });
    selectedTabDate = dateRange[_dateTabController!.index];
    print('TabController updated - selected date: $selectedTabDate');
  }

  Future<void> _fetchTasks() async {
    setState(() {
      isLoading = true;
      errorMessage = null;
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('token') ?? '';
      final response = await http.get(
        Uri.parse('http://appmobile.tng.vn/production/api/cat/lenh_cap_btp?maChiNhanh=12'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'JWT $token',
        },
      ).timeout(const Duration(seconds: 10), onTimeout: () {
        throw Exception('Request to lenh_cap_btp API timed out');
      });

      print('API response status: ${response.statusCode}');
      print('API response body: ${response.body}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data is! List) {
          setState(() {
            errorMessage = 'Dữ liệu từ server không hợp lệ!';
          });
          return;
        }

        final tasks = (data as List).map<Map<String, dynamic>>((task) {
          final createDate = task['ngayCap'] != null
              ? DateTime.fromMillisecondsSinceEpoch(task['ngayCap']).toLocal()
              : DateTime.now().toLocal();
          return {
            'lenhCapID': task['lenhCapID']?.toString() ?? 'Unknown',
            'danChuyenID': task['danChuyenID']?.toString() ?? 'Unknown',
            'maHang': task['maHang']?.toString() ?? 'Unknown',
            'tenMau': task['tenMau']?.toString() ?? 'Unknown',
            'tenCo': task['tenCo']?.toString() ?? 'Unknown',
            'tenBoPhan': task['tenBoPhan']?.toString() ?? 'Unknown',
            'soLuongCap': task['soLuongCap'] != null
                ? int.tryParse(task['soLuongCap'].toString()) ?? 0
                : 0,
            'ngayCap': createDate.millisecondsSinceEpoch,
            'soLenhCap': task['soLenhCap']?.toString() ?? 'Unknown',
            'maChiNhanh': task['maChiNhanh']?.toString() ?? '12',
            'po': task['po']?.toString() ?? 'Unknown',
            'raChuyen_HomTruoc': task['raChuyen_HomTruoc'] != null
                ? int.tryParse(task['raChuyen_HomTruoc'].toString()) ?? 0
                : 0,
            'ghiChu': task['ghiChu']?.toString() ?? '',
            'status': 'Pending',
            'deliveryType': 'AGV',
            'isTaskDisabled': false,
            'totalIssuedQuantity': 0,
            'totalQuantity': task['soLuongCap'] ?? 0,
            'deliveryCount': 0,
          };
        }).toList();

        // Lấy trạng thái từ API get-finished-product
        for (var task in tasks) {
          final maHang = task['maHang']?.toString().replaceAll(' ', '-')?.toUpperCase().trim() ?? 'UNKNOWN';
          final tenMau = task['tenMau']?.toString().trim() ?? 'UNKNOWN';
          final tenCo = task['tenCo']?.toString().trim() ?? 'UNKNOWN';
          final tenBoPhan = task['tenBoPhan']?.toString().trim() ?? 'UNKNOWN';

          if (maHang == 'UNKNOWN' || tenMau == 'UNKNOWN' || tenCo == 'UNKNOWN' || tenBoPhan == 'UNKNOWN') {
            print('Invalid task data for fetching status: ${jsonEncode(task)}');
            continue;
          }

          final normalizedTenBoPhan = RegExp(r'^\d+$').hasMatch(tenBoPhan) ? tenBoPhan : RegExp(r'\d+').firstMatch(tenBoPhan)?.group(0) ?? tenBoPhan;

          final queryParameters = {
            'materialCode': maHang,
            'mColors': tenMau,
            'mSizes': tenCo,
            'teamName': normalizedTenBoPhan,
          };

          final uri = Uri.parse('http://103.101.161.216:7000/api/agv/get-finished-product').replace(queryParameters: queryParameters);
          print('Fetching status for task: $uri');

          try {
            final response = await http.get(
              uri,
              headers: {
                'Content-Type': 'application/json',
                'Authorization': 'JWT $token',
              },
            ).timeout(const Duration(seconds: 5));

            print('Status API response for task ${task['maHang']}: ${response.statusCode} - ${response.body}');

            if (response.statusCode == 200) {
              final jsonData = jsonDecode(response.body);
              if (jsonData['success'] == true && jsonData['data'] != null) {
                final records = (jsonData['data'] as List<dynamic>).map((record) {
                  final standardizedRecord = Map<String, dynamic>.from(record);
                  final issuedQuantityStr = standardizedRecord['issuedQuantity']?.toString() ?? '0/0';
                  final parts = issuedQuantityStr.split('/');
                  final issuedQuantity = int.tryParse(parts[0].trim()) ?? 0;
                  final totalQuantity = int.tryParse(parts.length > 1 ? parts[1].trim() : '0') ?? 0;
                  standardizedRecord['issuedQuantity'] = issuedQuantity;
                  standardizedRecord['totalQuantity'] = totalQuantity;
                  standardizedRecord['totalIssuedQuantity'] = int.tryParse(standardizedRecord['totalIssuedQuantity']?.toString() ?? '0') ?? 0;
                  standardizedRecord['mStatus'] = standardizedRecord['mStatus']?.toString() ?? 'Pending';
                  return standardizedRecord;
                }).toList();

                // Tính tổng issuedQuantity từ tất cả các bản ghi
                final totalIssuedQuantity = records.fold<int>(
                  0,
                  (sum, record) => sum + (record['issuedQuantity'] as int),
                );
                final totalQuantity = records.isNotEmpty ? records[0]['totalQuantity'] as int : task['soLuongCap'] ?? 0;
                final deliveryCount = records.length;

                task['totalIssuedQuantity'] = totalIssuedQuantity;
                task['totalQuantity'] = totalQuantity;
                task['status'] = totalIssuedQuantity >= totalQuantity ? 'Completed' : 'Pending';
                task['isTaskDisabled'] = task['status'] == 'Completed';
                task['deliveryCount'] = deliveryCount;
                print('Updated task: ${task['maHang']} - status: ${task['status']}, totalIssuedQuantity: $totalIssuedQuantity, totalQuantity: $totalQuantity, deliveryCount: $deliveryCount');
              }
            }
          } catch (e) {
            print('Error fetching status for task ${task['maHang']}: $e');
            task['status'] = 'Pending';
            task['isTaskDisabled'] = false;
            task['totalIssuedQuantity'] = 0;
            task['totalQuantity'] = task['soLuongCap'] ?? 0;
            task['deliveryCount'] = 0;
          }
        }

        setState(() {
          _originalTasks = tasks;
          _displayedTasks = List.from(_originalTasks);
          _filterTasks();
        });
        print('Parsed tasks: $_originalTasks');
      } else {
        setState(() {
          errorMessage = 'Failed to fetch tasks: HTTP ${response.statusCode}';
        });
      }
    } catch (e) {
      setState(() {
        errorMessage = 'Error fetching tasks: $e';
      });
      print('Error fetching tasks: $e');
    } finally {
      setState(() {
        isLoading = false;
      });
    }
  }

  void _filterTasks() {
    if (!mounted) {
      print('Widget not mounted, aborting _filterTasks');
      return;
    }

    setState(() {
      if (_originalTasks.isEmpty) {
        _displayedTasks = [];
        return;
      }

      List<Map<String, dynamic>> filteredTasks = List.from(_originalTasks);

      if (selectedTabDate != null) {
        filteredTasks = filteredTasks.where((task) {
          if (task['ngayCap'] == null) return false;
          final taskDate = DateTime.fromMillisecondsSinceEpoch(task['ngayCap']).toLocal().toString().split(' ')[0];
          return taskDate == selectedTabDate;
        }).toList();
      }

      if (_selectedTeams.isNotEmpty) {
        filteredTasks = filteredTasks.where((task) {
          final team = task['tenBoPhan']?.toString() ?? 'Unknown';
          return _selectedTeams.contains(team);
        }).toList();
      }

      if (_searchController.text.isNotEmpty) {
        final searchText = _searchController.text.toLowerCase();
        filteredTasks = filteredTasks.where((task) {
          final maHang = task['maHang']?.toLowerCase() ?? '';
          final tenMau = task['tenMau']?.toLowerCase() ?? '';
          final tenCo = task['tenCo']?.toLowerCase() ?? '';
          final tenBoPhan = task['tenBoPhan']?.toLowerCase() ?? '';
          return maHang.contains(searchText) ||
                 tenMau.contains(searchText) ||
                 tenCo.contains(searchText) ||
                 tenBoPhan.contains(searchText);
        }).toList();
      }

      _displayedTasks = filteredTasks;
      print('Filtered tasks count: ${_displayedTasks.length}');
    });
  }

  void _showFilterDialog() {
    final uniqueTeams = getUniqueTeams();
    if (uniqueTeams.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Không có tổ nào để lọc!')),
      );
      return;
    }

    List<bool> isSelected = List.filled(uniqueTeams.length, false);
    for (int i = 0; i < uniqueTeams.length; i++) {
      isSelected[i] = _selectedTeams.contains(uniqueTeams[i]);
    }

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (BuildContext dialogContext, StateSetter setDialogState) {
          return AlertDialog(
            title: const Text('Lọc Theo Tổ'),
            content: SizedBox(
              width: double.maxFinite,
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(context).size.height * 0.3,
                ),
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      ListView.builder(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: uniqueTeams.length > 50 ? 50 : uniqueTeams.length,
                        itemBuilder: (context, index) {
                          final team = uniqueTeams[index];
                          return CheckboxListTile(
                            title: Text(team ?? 'Unknown'),
                            value: isSelected[index],
                            onChanged: (value) {
                              if (value == null) return;
                              setDialogState(() {
                                if (value) {
                                  _selectedTeams.add(team);
                                } else {
                                  _selectedTeams.remove(team);
                                }
                                isSelected[index] = value;
                              });
                              if (mounted) {
                                setState(() {});
                              }
                            },
                          );
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Hủy'),
              ),
              TextButton(
                onPressed: () {
                  _filterTasks();
                  Navigator.pop(context);
                },
                child: const Text('Áp dụng'),
              ),
            ],
          );
        },
      ),
    );
  }

  List<String> getUniqueTeams() {
    if (_originalTasks.isEmpty) {
      return [];
    }
    final teamCount = <String, int>{};
    for (var task in _originalTasks) {
      final team = task['tenBoPhan']?.toString() ?? 'Unknown';
      teamCount[team] = (teamCount[team] ?? 0) + 1;
    }
    print('Unique teams: ${teamCount.keys.toList()}');
    return teamCount.keys.toList();
  }

  bool _hasTasksForDate(String date) {
    return _displayedTasks.any((task) {
      if (task['ngayCap'] == null) return false;
      final taskDate = DateTime.fromMillisecondsSinceEpoch(task['ngayCap']).toLocal().toString().split(' ')[0];
      return taskDate == date;
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    _dateTabController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Giao Hàng',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.blue,
        elevation: 0,
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Colors.blue, Colors.lightBlue],
            ),
          ),
        ),
      ),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Colors.blue, Colors.lightBlue],
              ),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _searchController,
                      decoration: InputDecoration(
                        hintText: 'Tìm kiếm mã hàng, mẫu, kích cỡ, tổ...',
                        prefixIcon: const Icon(Icons.search, color: Colors.grey),
                        filled: true,
                        fillColor: Colors.white,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(15.0),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(15.0),
                          borderSide: BorderSide(color: Colors.grey, width: 1.0),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(15.0),
                          borderSide: BorderSide(color: Colors.blue, width: 2.0),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8.0),
                  IconButton(
                    icon: const Icon(Icons.filter_list, color: Colors.white),
                    onPressed: _showFilterDialog,
                    tooltip: 'Lọc theo tổ',
                    padding: const EdgeInsets.all(12.0),
                  ),
                ],
              ),
            ),
          ),
          if (_originalTasks.isEmpty && !isLoading && errorMessage == null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
              child: ElevatedButton(
                onPressed: _fetchTasks,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blue,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
                child: const Text(
                  'Lấy danh sách đơn hàng',
                  style: TextStyle(fontSize: 16, color: Colors.white),
                ),
              ),
            ),
          if (errorMessage != null)
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    errorMessage!,
                    style: const TextStyle(color: Colors.red, fontSize: 16),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8.0),
                  ElevatedButton(
                    onPressed: _fetchTasks,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blue,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8.0),
                      ),
                    ),
                    child: const Text(
                      'Thử lại',
                      style: TextStyle(fontSize: 16, color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),
          if (isLoading)
            const Flexible(
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_dateTabController != null && dateRange.isNotEmpty)
            Flexible(
              fit: FlexFit.loose,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    color: Colors.blue,
                    child: TabBar(
                      controller: _dateTabController,
                      labelColor: Colors.white,
                      unselectedLabelColor: Colors.white70,
                      indicatorColor: Colors.white,
                      isScrollable: true,
                      tabs: dateRange.map((date) => Tab(text: date)).toList(),
                    ),
                  ),
                  Flexible(
                    fit: FlexFit.loose,
                    child: Container(
                      color: Colors.white,
                      child: TabBarView(
                        controller: _dateTabController,
                        children: dateRange.map((date) {
                          final tasksForDate = _displayedTasks.where((task) {
                            if (task['ngayCap'] == null) return false;
                            final taskDate = DateTime.fromMillisecondsSinceEpoch(task['ngayCap']).toLocal().toString().split(' ')[0];
                            return taskDate == date;
                          }).toList();

                          return tasksForDate.isEmpty
                              ? const Center(child: Text('Không có đơn hàng để hiển thị'))
                              : ListView.builder(
                                  padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                                  itemCount: tasksForDate.length,
                                  itemBuilder: (context, index) {
                                    final task = tasksForDate[index];
                                    final taskDate = DateTime.fromMillisecondsSinceEpoch(task['ngayCap']).toLocal().toString().split(' ')[0];
                                    final isToday = taskDate == todayDate;
                                    final isCompleted = task['status'] == 'Completed';

                                    // Áp dụng làm mờ cho đơn hàng có trạng thái Completed
                                    return Opacity(
                                      opacity: isCompleted ? 0.5 : 1.0,
                                      child: GestureDetector(
                                        onTap: isCompleted
                                            ? null
                                            : () async {
                                                final result = await Navigator.push(
                                                  context,
                                                  MaterialPageRoute(
                                                    builder: (context) => TaskDetailScreen(task: task),
                                                  ),
                                                );
                                                if (result != null && result['status'] != null) {
                                                  setState(() {
                                                    task['status'] = result['status'];
                                                    task['isTaskDisabled'] = result['status'] == 'Completed';
                                                  });
                                                  _filterTasks();
                                                }
                                              },
                                        child: Card(
                                          color: Colors.white,
                                          elevation: 5,
                                          margin: const EdgeInsets.symmetric(vertical: 8.0),
                                          shape: RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(10.0),
                                            side: BorderSide(color: Colors.grey, width: 1),
                                          ),
                                          child: Padding(
                                            padding: const EdgeInsets.all(16.0),
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  'Mã Hàng: ${task['maHang']}',
                                                  style: TextStyle(
                                                    fontSize: 16,
                                                    fontWeight: FontWeight.bold,
                                                    color: isToday ? Colors.blue : Colors.grey,
                                                  ),
                                                ),
                                                const SizedBox(height: 8.0),
                                                Text(
                                                  'Mẫu: ${task['tenMau']}',
                                                  style: TextStyle(
                                                    fontSize: 14,
                                                    color: isToday ? Colors.black : Colors.grey,
                                                  ),
                                                ),
                                                Text(
                                                  'Kích Cỡ: ${task['tenCo']}',
                                                  style: TextStyle(
                                                    fontSize: 14,
                                                    color: isToday ? Colors.black : Colors.grey,
                                                  ),
                                                ),
                                                Text(
                                                  'Tổ Cấp: ${task['tenBoPhan']}',
                                                  style: TextStyle(
                                                    fontSize: 14,
                                                    color: isToday ? Colors.black : Colors.grey,
                                                  ),
                                                ),
                                                Text(
                                                  'Số Lượng: ${task['soLuongCap']}',
                                                  style: TextStyle(
                                                    fontSize: 14,
                                                    color: isToday ? Colors.black : Colors.grey,
                                                  ),
                                                ),
                                                Text(
                                                  'Trạng thái: ${task['status'] == 'Completed' ? 'Hoàn thành' : 'Đang xử lý'}',
                                                  style: TextStyle(
                                                    fontSize: 14,
                                                    color: isCompleted ? Colors.green : Colors.orange,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                        ),
                                      ),
                                    );
                                  },
                                );
                        }).toList(),
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class TaskDetailScreen extends StatefulWidget {
  final Map<String, dynamic> task;

  const TaskDetailScreen({Key? key, required this.task}) : super(key: key);

  @override
  _TaskDetailScreenState createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends State<TaskDetailScreen> {
  String? selectedDeliveryType;
  String? _selectedAGV;
  bool isTaskDisabled = false;
  bool _isSaving = false;
  bool _isLoading = true;
  String? loggedInUserName;
  List<String> _locations = ['Cắt 1', 'Cắt 2', 'Cắt 3', '11'];
  List<String> _availableAGVs = [];
  String? _agvError;
  final TextEditingController _quantityController = TextEditingController();
  int _issuedQuantity = 0;
  int _totalQuantity = 0;
  String _status = 'Pending';

  @override
  void initState() {
    super.initState();
    _loadUserName();
    _loadLocations();
    _fetchAGVNames();
    selectedDeliveryType = widget.task['deliveryType']?.toString() ?? 'AGV';
    isTaskDisabled = widget.task['isTaskDisabled'] ?? false;
    _totalQuantity = int.tryParse(widget.task['totalQuantity']?.toString() ?? '0') ?? 0;
    _issuedQuantity = int.tryParse(widget.task['issuedQuantity']?.toString() ?? '0') ?? 0;
    _status = widget.task['status']?.toString() ?? 'Pending';
    print('Initial totalQuantity: $_totalQuantity, issuedQuantity: $_issuedQuantity, status: $_status');
    _fetchIssuedQuantity();
    _quantityController.addListener(() {
      setState(() {});
    });
  }

  Future<void> _loadUserName() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      loggedInUserName = prefs.getString('name') ?? 'Unknown';
    });
    print('Loaded user name: $loggedInUserName');
  }

  Future<void> _loadLocations() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _locations = prefs.getStringList('locations') ?? ['Cắt 1', 'Cắt 2', 'Cắt 3', '11'];
    });
    print('Loaded locations: $_locations');
  }

  Future<void> _fetchAGVNames() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('token') ?? '';
      final response = await http.get(
        Uri.parse('http://103.101.161.216:7000/api/agv/get-agv-status'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'JWT $token',
        },
      ).timeout(const Duration(seconds: 10));

      print('AGV names API response: ${response.statusCode} - ${response.body}');

      if (response.statusCode == 200) {
        final jsonData = jsonDecode(response.body);
        if (jsonData['success'] != true) {
          setState(() {
            _agvError = 'Lỗi từ server: ${jsonData['message'] ?? 'Không có thông tin lỗi'}';
            _isLoading = false;
          });
          print('AGV API error: ${jsonData['message'] ?? 'No error message'}');
          return;
        }

        if (jsonData['data'] is! List) {
          setState(() {
            _agvError = 'Dữ liệu AGV không đúng định dạng';
            _isLoading = false;
          });
          print('Invalid AGV data format: Expected "data" to be a List');
          return;
        }

        final agvNames = (jsonData['data'] as List)
            .where((agv) => agv['agvName'] != null && agv['agvName'].toString().trim().isNotEmpty)
            .map((agv) => agv['agvName'].toString().trim())
            .toList();

        setState(() {
          _availableAGVs = agvNames;
          if (_availableAGVs.isNotEmpty && selectedDeliveryType == 'AGV') {
            _selectedAGV = _availableAGVs[0];
          }
          _agvError = agvNames.isEmpty ? 'Không có AGV nào khả dụng' : null;
          _isLoading = false;
        });
        print('Fetched AGV names: $_availableAGVs');
      } else {
        setState(() {
          _agvError = 'Lỗi khi lấy danh sách AGV: HTTP ${response.statusCode}';
          _isLoading = false;
        });
        print('Failed to fetch AGV names: HTTP ${response.statusCode}');
      }
    } catch (e) {
      setState(() {
        _agvError = 'Lỗi khi lấy danh sách AGV: $e';
        _isLoading = false;
      });
      print('Error fetching AGV names: $e');
    }
  }

  Future<void> _fetchIssuedQuantity() async {
    try {
      final maHang = widget.task['maHang']?.toString().replaceAll(' ', '-')?.toUpperCase().trim() ?? 'UNKNOWN';
      final tenMau = widget.task['tenMau']?.toString().trim() ?? 'UNKNOWN';
      final tenCo = widget.task['tenCo']?.toString().trim() ?? 'UNKNOWN';
      final tenBoPhan = widget.task['tenBoPhan']?.toString().trim() ?? 'UNKNOWN';

      if (maHang == 'UNKNOWN' || tenMau == 'UNKNOWN' || tenCo == 'UNKNOWN' || tenBoPhan == 'UNKNOWN') {
        print('Invalid task data for fetching issued quantity: ${jsonEncode(widget.task)}');
        setState(() {
          _isLoading = false;
        });
        return;
      }

      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('token') ?? '';
      final normalizedTenBoPhan = RegExp(r'^\d+$').hasMatch(tenBoPhan) ? tenBoPhan : RegExp(r'\d+').firstMatch(tenBoPhan)?.group(0) ?? tenBoPhan;

      final queryParameters = {
        'materialCode': maHang,
        'mColors': tenMau,
        'mSizes': tenCo,
        'teamName': normalizedTenBoPhan,
      };

      final uri = Uri.parse('http://103.101.161.216:7000/api/agv/get-finished-product').replace(queryParameters: queryParameters);
      print('Fetching issued quantity: $uri');

      final response = await http.get(
        uri,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'JWT $token',
        },
      ).timeout(const Duration(seconds: 10));

      print('Issued quantity API response: ${response.statusCode} - ${response.body}');

      if (response.statusCode == 200) {
        final jsonData = jsonDecode(response.body);
        if (jsonData['success'] == true && jsonData['data'] != null) {
          final records = (jsonData['data'] as List<dynamic>).map((record) {
            final standardizedRecord = Map<String, dynamic>.from(record);
            final issuedQuantityStr = standardizedRecord['issuedQuantity']?.toString() ?? '0';
            final issuedQuantity = RegExp(r'^\d+').hasMatch(issuedQuantityStr)
                ? int.tryParse(RegExp(r'^\d+').firstMatch(issuedQuantityStr)!.group(0)!) ?? 0
                : 0;
            standardizedRecord['issuedQuantity'] = issuedQuantity;
            standardizedRecord['totalQuantity'] = (standardizedRecord['totalQuantity'] as num?)?.toInt() ?? 0;
            standardizedRecord['totalIssuedQuantity'] = int.tryParse(standardizedRecord['totalIssuedQuantity']?.toString() ?? '0') ?? 0;
            standardizedRecord['mStatus'] = standardizedRecord['mStatus']?.toString() ?? 'Pending';
            standardizedRecord['confirmTime'] = standardizedRecord['confirmedTime']?.toString();
            return standardizedRecord;
          }).toList();

          final totalIssuedQuantity = records.isNotEmpty && records[0]['totalIssuedQuantity'] > 0
              ? records[0]['totalIssuedQuantity'] as int
              : records.fold<int>(
                  0,
                  (sum, record) => sum + (record['issuedQuantity'] as int),
                );

          final newTotalQuantity = records.isNotEmpty && records[0]['totalQuantity'] > 0
              ? records[0]['totalQuantity'] as int
              : _totalQuantity;

          setState(() {
            _issuedQuantity = totalIssuedQuantity;
            _totalQuantity = newTotalQuantity;
            _status = _issuedQuantity >= _totalQuantity ? 'Completed' : 'Pending';
            isTaskDisabled = _issuedQuantity >= _totalQuantity;
            widget.task['status'] = _status;
            widget.task['isTaskDisabled'] = isTaskDisabled;
            widget.task['issuedQuantity'] = _issuedQuantity;
            widget.task['totalQuantity'] = _totalQuantity;
            _isLoading = false;
          });
          print('Fetched: issuedQuantity=$_issuedQuantity, totalQuantity=$_totalQuantity, status=$_status, records=${jsonEncode(records)}');
        } else {
          print('Failed to fetch issued quantity: ${jsonData['message'] ?? 'No data'}');
          setState(() {
            _isLoading = false;
          });
        }
      } else {
        print('Failed to fetch issued quantity: HTTP ${response.statusCode}');
        setState(() {
          _isLoading = false;
        });
      }
    } catch (e) {
      print('Error fetching issued quantity: $e');
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _handleSaveData() async {
    if (_isSaving || isTaskDisabled) {
      print('Saving in progress or task is disabled, ignoring save');
      return;
    }
    final tenBoPhan = widget.task['tenBoPhan']?.toString().trim();
    if (tenBoPhan == null || tenBoPhan.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Tên bộ phận không hợp lệ'), backgroundColor: Colors.red),
      );
      return;
    }
    final inputQuantity = int.tryParse(_quantityController.text) ?? 0;
    if (inputQuantity <= 0 || inputQuantity > _totalQuantity - _issuedQuantity) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Số lượng cấp phải từ 1 đến ${_totalQuantity - _issuedQuantity}'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }
    if (selectedDeliveryType == 'AGV' && _selectedAGV == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Vui lòng chọn một AGV'), backgroundColor: Colors.red),
      );
      return;
    }

    final tenBoPhanRaw = tenBoPhan;
    final tenBoPhanNormalized = RegExp(r'^\d+$').hasMatch(tenBoPhanRaw)
        ? tenBoPhanRaw
        : RegExp(r'\d+').firstMatch(tenBoPhanRaw)?.group(0) ?? tenBoPhanRaw;
    if (tenBoPhanNormalized.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Tên bộ phận không chứa số hợp lệ'), backgroundColor: Colors.red),
      );
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    final creator = prefs.getString('name')?.trim();
    if (creator == null || creator.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Không tìm thấy thông tin người dùng'), backgroundColor: Colors.red),
      );
      return;
    }

    print('Saving data for tenBoPhan: $tenBoPhanRaw, normalized: $tenBoPhanNormalized');

    setState(() {
      _isSaving = true;
    });

    final maHang = widget.task['maHang']?.toString().replaceAll(' ', '-')?.trim() ?? 'UNKNOWN';
    final tenMau = widget.task['tenMau']?.toString().trim() ?? 'UNKNOWN';
    final tenCo = widget.task['tenCo']?.toString().trim() ?? 'UNKNOWN';
    final totalQuantity = _totalQuantity;

    if (maHang == 'UNKNOWN' || tenMau == 'UNKNOWN' || tenCo == 'UNKNOWN') {
      print('Invalid task data: maHang=$maHang, tenMau=$tenMau, tenCo=$tenCo, tenBoPhan=$tenBoPhanRaw, normalized tenBoPhan=$tenBoPhanNormalized');
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Dữ liệu đơn hàng không hợp lệ'), backgroundColor: Colors.red),
      );
      setState(() {
        _isSaving = false;
      });
      return;
    }

    final requestBody = {
      'materialCode': maHang,
      'mColors': tenMau,
      'mSizes': tenCo,
      'teamName': tenBoPhanNormalized,
      'totalQuantity': totalQuantity,
      'issuedQuantity': inputQuantity,
      'deliveryType': selectedDeliveryType ?? 'AGV',
      'agv': selectedDeliveryType == 'AGV' ? _selectedAGV : null,
      'mStatus': 'Pending',
      'creator': creator,
    };

    print('Request body: ${jsonEncode(requestBody)}');

    try {
      final token = prefs.getString('token') ?? '';
      final response = await http.post(
        Uri.parse('http://103.101.161.216:7000/api/agv/update-finished-product'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'JWT $token',
        },
        body: jsonEncode(requestBody),
      ).timeout(const Duration(seconds: 20));

      print('Update finished product response: ${response.statusCode} - ${response.body}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['success'] == true) {
          print('Update finished product successful');
          await _fetchIssuedQuantity();
          setState(() {
            _isSaving = false;
            widget.task['status'] = _status;
            widget.task['isTaskDisabled'] = _status == 'Completed';
          });
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Lưu dữ liệu thành công'),
              backgroundColor: Colors.green,
            ),
          );
          Navigator.pop(context, {
            'status': widget.task['status'],
            'isTaskDisabled': widget.task['isTaskDisabled'],
          });
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Lưu dữ liệu thất bại: ${data['message'] ?? 'Unknown error'}'), backgroundColor: Colors.red),
          );
          setState(() {
            _isSaving = false;
          });
        }
      } else {
        final errorData = jsonDecode(response.body);
        print('Error details: ${errorData['errors'] ?? errorData['message']}');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Lưu dữ liệu thất bại: ${errorData['title'] ?? 'Server trả về mã ${response.statusCode}'}'),
            backgroundColor: Colors.red,
          ),
        );
        setState(() {
          _isSaving = false;
        });
      }
    } catch (e) {
      print('Error updating finished product: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Lỗi khi lưu dữ liệu: $e'), backgroundColor: Colors.red),
      );
      setState(() {
        _isSaving = false;
      });
    }
  }

  @override
  void dispose() {
    _quantityController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    print('Building TaskDetailScreen - issuedQuantity: $_issuedQuantity, totalQuantity: $_totalQuantity, status: $_status');
    final size = widget.task['tenCo']?.toString() ?? 'Không có';
    final status = _status == 'Completed' ? 'Hoàn thành' : 'Đang xử lý';

    if (_isLoading) {
      return Scaffold(
        appBar: AppBar(
          leading: IconButton(
            icon: const Icon(Icons.arrow_back, color: Colors.white),
            onPressed: () => Navigator.pop(context),
          ),
          title: Text(
            'Chi Tiết Đơn Hàng: ${widget.task['maHang'] ?? 'UNKNOWN'}',
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
          ),
          backgroundColor: Colors.blue,
          elevation: 0,
          flexibleSpace: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Colors.blue, Colors.lightBlue],
              ),
            ),
          ),
        ),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          'Chi Tiết Đơn Hàng: ${widget.task['maHang'] ?? 'UNKNOWN'}',
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.blue,
        elevation: 0,
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Colors.blue, Colors.lightBlue],
            ),
          ),
        ),
      ),
      body: Scrollbar(
        thumbVisibility: true,
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Opacity(
              opacity: isTaskDisabled ? 0.5 : 1.0,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextField(
                    enabled: false,
                    style: const TextStyle(color: Colors.black, fontSize: 18),
                    decoration: InputDecoration(
                      labelText: 'Mã Hàng',
                      labelStyle: const TextStyle(fontSize: 18),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      filled: true,
                      fillColor: Colors.white,
                    ),
                    controller: TextEditingController(text: widget.task['maHang']?.toString() ?? 'Không có'),
                  ),
                  const SizedBox(height: 16.0),
                  TextField(
                    enabled: false,
                    style: const TextStyle(color: Colors.black, fontSize: 18),
                    decoration: InputDecoration(
                      labelText: 'Mẫu',
                      labelStyle: const TextStyle(fontSize: 18),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      filled: true,
                      fillColor: Colors.white,
                    ),
                    controller: TextEditingController(text: widget.task['tenMau']?.toString() ?? 'Không có'),
                  ),
                  const SizedBox(height: 16.0),
                  TextField(
                    enabled: false,
                    style: const TextStyle(color: Colors.black, fontSize: 18),
                    decoration: InputDecoration(
                      labelText: 'Tổ Cấp',
                      labelStyle: const TextStyle(fontSize: 18),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      filled: true,
                      fillColor: Colors.white,
                    ),
                    controller: TextEditingController(text: widget.task['tenBoPhan']?.toString() ?? 'Không có'),
                  ),
                  const SizedBox(height: 16.0),
                  Row(
                    children: [
                      Expanded(
                        flex: 2,
                        child: TextField(
                          enabled: false,
                          style: const TextStyle(color: Colors.black, fontSize: 18),
                          decoration: InputDecoration(
                            labelText: 'Kích Cỡ',
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10.0),
                            ),
                            filled: true,
                            fillColor: Colors.white,
                          ),
                          controller: TextEditingController(text: size),
                        ),
                      ),
                      const SizedBox(width: 8.0),
                      Expanded(
                        flex: 1,
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 16.0, horizontal: 8.0),
                          alignment: Alignment.center,
                          child: Text(
                            _status == 'Completed' ? 'Đã hết' : '(Tổng số lượng: $_totalQuantity)',
                            style: const TextStyle(color: Colors.black, fontSize: 18),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16.0),
                  Row(
                    children: [
                      Expanded(
                        flex: 2,
                        child: TextField(
                          controller: _quantityController,
                          enabled: !isTaskDisabled,
                          style: const TextStyle(color: Colors.black, fontSize: 18),
                          decoration: InputDecoration(
                            labelText: 'Số lượng cấp *',
                            labelStyle: const TextStyle(fontSize: 18),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10.0),
                            ),
                            filled: true,
                            fillColor: Colors.white,
                            hintText: 'Nhập số lượng từ 1 đến ${_totalQuantity - _issuedQuantity}',
                            errorText: _quantityController.text.isNotEmpty &&
                                    (int.tryParse(_quantityController.text) == null ||
                                        int.parse(_quantityController.text) <= 0 ||
                                        int.parse(_quantityController.text) > _totalQuantity - _issuedQuantity)
                                ? 'Số lượng phải từ 1 đến ${_totalQuantity - _issuedQuantity}'
                                : null,
                          ),
                          keyboardType: TextInputType.number,
                        ),
                      ),
                      const SizedBox(width: 8.0),
                      Expanded(
                        flex: 1,
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 16.0, horizontal: 8.0),
                          alignment: Alignment.center,
                          child: Text(
                            '(Số lượng đã cấp: $_issuedQuantity)',
                            style: const TextStyle(color: Colors.black, fontSize: 18),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16.0),
                  DropdownButtonFormField<String>(
                    value: selectedDeliveryType,
                    decoration: InputDecoration(
                      labelText: 'Kiểu cấp hàng',
                      labelStyle: const TextStyle(fontSize: 18),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      filled: true,
                      fillColor: Colors.white,
                    ),
                    items: const [
                      DropdownMenuItem(value: 'AGV', child: Text('AGV')),
                      DropdownMenuItem(value: 'Thủ công', child: Text('Thủ công')),
                    ],
                    onChanged: isTaskDisabled
                        ? null
                        : (value) {
                            if (value != null) {
                              setState(() {
                                selectedDeliveryType = value;
                                if (value != 'AGV') {
                                  _selectedAGV = null;
                                } else if (_selectedAGV == null && _availableAGVs.isNotEmpty) {
                                  _selectedAGV = _availableAGVs[0];
                                }
                              });
                              print('Delivery type changed to: $value');
                            }
                          },
                  ),
                  if (selectedDeliveryType == 'AGV') ...[
                    const SizedBox(height: 16.0),
                    DropdownButtonFormField<String>(
                      value: _selectedAGV,
                      decoration: InputDecoration(
                        labelText: 'Chọn AGV *',
                        hintText: 'Chọn AGV',
                        labelStyle: const TextStyle(fontSize: 18),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10.0),
                        ),
                        filled: true,
                        fillColor: Colors.white,
                        errorText: _agvError,
                      ),
                      items: _availableAGVs
                          .map((agv) => DropdownMenuItem(value: agv, child: Text(agv)))
                          .toList(),
                      onChanged: isTaskDisabled || _availableAGVs.isEmpty
                          ? null
                          : (value) {
                              if (value != null) {
                                setState(() {
                                  _selectedAGV = value;
                                });
                                print('Selected AGV: $value');
                              }
                            },
                    ),
                  ],
                  const SizedBox(height: 16.0),
                  TextField(
                    enabled: false,
                    style: const TextStyle(color: Colors.black, fontSize: 18),
                    decoration: InputDecoration(
                      labelText: 'Trạng Thái',
                      labelStyle: const TextStyle(fontSize: 18),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                      filled: true,
                      fillColor: Colors.white,
                    ),
                    controller: TextEditingController(text: status),
                  ),
                  const SizedBox(height: 20.0),
                  Center(
                    child: ElevatedButton(
                      onPressed: isTaskDisabled || _isSaving
                          ? null
                          : _handleSaveData,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.blue,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 32.0, vertical: 12.0),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8.0),
                        ),
                      ),
                      child: _isSaving
                          ? const CircularProgressIndicator(color: Colors.white)
                          : const Text(
                              'Lưu Dữ Liệu',
                              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                            ),
                    ),
                  ),
                  const SizedBox(height: 20.0),
                ],
              ),
            ),
          ),
        ),
      ),
      backgroundColor: Colors.white,
    );
  }
}