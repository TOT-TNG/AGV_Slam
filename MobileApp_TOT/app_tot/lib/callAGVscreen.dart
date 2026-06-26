import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';

class CallAGVScreen extends StatefulWidget {
  const CallAGVScreen({super.key});

  @override
  _CallAGVScreenState createState() => _CallAGVScreenState();
}

class _CallAGVScreenState extends State<CallAGVScreen> {
  String? _selectedLocation;
  String? _selectedAGV;
  List<String> _locations = ['Cắt 1', 'Cắt 2', 'Cắt 3'];
  final List<String> _agvs = ['AGV01', 'AGV02', 'AGV03','AGV04'];
  final TextEditingController _newLocationController = TextEditingController();
  List<dynamic> _agvStatuses = [];
  String _lastUpdated = '';
  bool _isAGVReady = false; // Biến kiểm soát trạng thái nút Gọi xe

  @override
  void initState() {
    super.initState();
    _loadLocations();
    _fetchAGVStatus();
  }

  Future<void> _loadLocations() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _locations = prefs.getStringList('locations') ?? ['Cắt 1', 'Cắt 2', 'Cắt 3'];
    });
  }

  Future<void> _saveLocations() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList('locations', _locations);
  }

  Future<void> _fetchAGVStatus() async {
    try {
      final url = 'http://10.9.10.15:7000/api/agv/get-agv-status';
      print('Fetching AGV status from: $url');
      final response = await http.get(Uri.parse(url));

      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body);
        print('AGV status response: ${response.body}');
        if (jsonData['success'] == true) {
          setState(() {
            _agvStatuses = jsonData['data'] ?? [];
            _lastUpdated = DateFormat('HH:mm dd/MM/yyyy').format(DateTime.now());
          });
          _checkAGVStatus(); // Kiểm tra trạng thái AGV sau khi làm mới
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Lỗi khi lấy trạng thái AGV: ${jsonData['message'] ?? 'Unknown error'}')),
          );
        }
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Lỗi khi gọi API trạng thái AGV: ${response.statusCode} - ${response.body}')),
        );
      }
    } catch (e) {
      print('Error fetching AGV status: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Lỗi khi gọi API trạng thái AGV: $e')),
      );
    }
  }

  void _checkAGVStatus() {
    if (_selectedAGV != null) {
      final selectedStatus = _agvStatuses.firstWhere(
        (status) => status['agvName'] == _selectedAGV,
        orElse: () => {'status': 'Unknown'},
      );
      String agvStatus = selectedStatus['status']?.toString() ?? 'Unknown';
      if (agvStatus == 'Idle') {
        setState(() {
          _isAGVReady = true;
        });
      } else {
        setState(() {
          _isAGVReady = false;
        });
        String statusText = agvStatus == 'Waiting' ? 'đang chờ' : 'đang bận';
        showDialog(
          context: context,
          barrierDismissible: false, // Phải nhấn OK để đóng
          builder: (BuildContext context) {
            return AlertDialog(
              title: const Text('Thông báo'),
              content: Text('$_selectedAGV $statusText, không thể sử dụng'),
              actions: [
                TextButton(
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                  child: const Text('OK', style: TextStyle(color: Colors.blue)),
                ),
              ],
            );
          },
        );
      }
    } else {
      setState(() {
        _isAGVReady = false;
      });
    }
  }

  String _normalizeLocation(String location) {
    String cleaned = location.toLowerCase().replaceAll(RegExp(r'[^\w]'), '');
    RegExp regex = RegExp(r'cắt\s*(\d+)', caseSensitive: false);
    var match = regex.firstMatch(cleaned);
    if (match != null) {
      return 'cat${match.group(1)}';
    }
    return cleaned;
  }

  Future<void> _callAGV() async {
    if (_selectedLocation != null && _selectedAGV != null && _isAGVReady) {
      String normalizedLocation = _normalizeLocation(_selectedLocation!);
      print('Sending request to API with location: $normalizedLocation, AGV: $_selectedAGV');

      try {
        final url = 'http://10.9.10.15:7000/api/agv/call-agv/$normalizedLocation';
        print('API URL: $url');
        final response = await http.post(
          Uri.parse(url),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({
            'location': normalizedLocation,
            'agvName': _selectedAGV,
          }),
        );

        if (response.statusCode == 200) {
          
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Lỗi khi gọi API: ${response.statusCode} - ${response.body}')),
          );
        }
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Lỗi khi gọi API: $e')),
        );
      }
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Vui lòng chọn vị trí và AGV sẵn sàng trước khi gọi xe')),
      );
    }
  }

  void _showEditLocationsDialog() {
    List<String> tempLocations = List.from(_locations);
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return StatefulBuilder(
          builder: (BuildContext context, StateSetter setDialogState) {
            return AlertDialog(
              title: const Text('Chỉnh sửa vị trí'),
              content: SizedBox(
                width: double.maxFinite,
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      TextField(
                        controller: _newLocationController,
                        decoration: InputDecoration(
                          hintText: 'Nhập vị trí mới',
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16.0),
                      ElevatedButton(
                        onPressed: () {
                          if (_newLocationController.text.isNotEmpty &&
                              !tempLocations.contains(_newLocationController.text)) {
                            setDialogState(() {
                              tempLocations.add(_newLocationController.text);
                            });
                            _newLocationController.clear();
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blue[800],
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                        ),
                        child: const Text(
                          'Thêm vị trí',
                          style: TextStyle(color: Colors.white),
                        ),
                      ),
                      const SizedBox(height: 16.0),
                      SizedBox(
                        height: 200,
                        child: ListView.builder(
                          shrinkWrap: true,
                          itemCount: tempLocations.length,
                          itemBuilder: (context, index) {
                            return ListTile(
                              title: Text(tempLocations[index]),
                              trailing: IconButton(
                                icon: const Icon(Icons.delete, color: Colors.red),
                                onPressed: () {
                                  setDialogState(() {
                                    tempLocations.removeAt(index);
                                  });
                                },
                              ),
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Hủy', style: TextStyle(color: Colors.grey)),
                ),
                TextButton(
                  onPressed: () {
                    setState(() {
                      _locations = tempLocations;
                      _selectedLocation = _locations.contains(_selectedLocation)
                          ? _selectedLocation
                          : null;
                    });
                    _saveLocations();
                    Navigator.pop(context);
                  },
                  child: Text(
                    'Lưu',
                    style: TextStyle(color: Colors.blue[800]),
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.grey[100],
      appBar: AppBar(
        backgroundColor: Colors.blue[800],
        title: const Text(
          'GỌI XE AGV',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
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
        actions: [
          IconButton(
            icon: Icon(Icons.refresh, color: Colors.white),
            onPressed: _fetchAGVStatus,
            tooltip: 'Làm mới trạng thái AGV',
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Chọn vị trí gọi xe',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Colors.black87,
              ),
            ),
            const SizedBox(height: 16.0),
            Row(
              children: [
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12.0),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(12.0),
                      border: Border.all(color: Colors.blue[800]!, width: 1.5),
                    ),
                    child: DropdownButton<String>(
                      value: _selectedLocation,
                      hint: const Text('Chọn vị trí'),
                      isExpanded: true,
                      icon: Icon(Icons.arrow_drop_down, color: Colors.blue[800]),
                      underline: const SizedBox(),
                      items: _locations.map((String location) {
                        return DropdownMenuItem<String>(
                          value: location,
                          child: Text(
                            location,
                            style: const TextStyle(
                              fontSize: 16,
                              color: Colors.black87,
                            ),
                          ),
                        );
                      }).toList(),
                      onChanged: (String? newValue) {
                        setState(() {
                          _selectedLocation = newValue;
                        });
                      },
                    ),
                  ),
                ),
                const SizedBox(width: 8.0),
                IconButton(
                  icon: Icon(Icons.settings, color: Colors.blue[800]),
                  onPressed: _showEditLocationsDialog,
                ),
              ],
            ),
            const SizedBox(height: 16.0),
            const Text(
              'Chọn AGV',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Colors.black87,
              ),
            ),
            const SizedBox(height: 8.0),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12.0),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12.0),
                border: Border.all(color: Colors.blue[800]!, width: 1.5),
              ),
              child: DropdownButton<String>(
                value: _selectedAGV,
                hint: const Text('Chọn AGV'),
                isExpanded: true,
                icon: Icon(Icons.arrow_drop_down, color: Colors.blue[800]),
                underline: const SizedBox(),
                items: _agvs.map((String agv) {
                  return DropdownMenuItem<String>(
                    value: agv,
                    child: Text(
                      agv,
                      style: const TextStyle(
                        fontSize: 16,
                        color: Colors.black87,
                      ),
                    ),
                  );
                }).toList(),
                onChanged: (String? newValue) {
                  setState(() {
                    _selectedAGV = newValue;
                  });
                  _checkAGVStatus(); // Kiểm tra trạng thái khi chọn AGV
                },
              ),
            ),
            const SizedBox(height: 24.0),
            Center(
              child: ElevatedButton(
                onPressed: _isAGVReady ? _callAGV : null, // Vô hiệu hóa nếu AGV không sẵn sàng
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blue[800],
                  padding: const EdgeInsets.symmetric(
                    horizontal: 32.0,
                    vertical: 12.0,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12.0),
                  ),
                  disabledBackgroundColor: Colors.grey[400], // Màu khi nút bị vô hiệu
                ),
                child: const Text(
                  'Gọi xe',
                  style: TextStyle(
                    fontSize: 18,
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24.0),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Trạng thái AGV',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: Colors.black87,
                  ),
                ),
                IconButton(
                  icon: Icon(Icons.refresh, color: Colors.blue[800]),
                  onPressed: _fetchAGVStatus,
                  tooltip: 'Làm mới trạng thái AGV',
                ),
              ],
            ),
            const SizedBox(height: 8.0),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  'Cập nhật: $_lastUpdated',
                  style: const TextStyle(
                    fontSize: 14,
                    color: Colors.grey,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8.0),
            Expanded(
              child: _agvStatuses.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.info_outline,
                            size: 48,
                            color: Colors.grey[400],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Không có trạng thái AGV nào',
                            style: TextStyle(
                              fontSize: 16,
                              color: Colors.grey[600],
                            ),
                          ),
                        ],
                      ),
                    )
                  : ListView.builder(
                      itemCount: _agvStatuses.length,
                      itemBuilder: (context, index) {
                        var status = _agvStatuses[index];
                        String agvName = status['agvName']?.toString() ?? 'Unknown';
                        String agvStatus = status['status']?.toString() ?? 'Unknown';
                        Color statusColor;
                        String statusText;
                        IconData statusIcon;

                        if (agvStatus == 'Idle') {
                          statusColor = Colors.green;
                          statusText = 'Sẵn sàng';
                          statusIcon = Icons.check_circle;
                        } else if (agvStatus == 'Waiting') {
                          statusColor = Colors.yellow[700]!;
                          statusText = 'Đang chờ';
                          statusIcon = Icons.hourglass_empty;
                        } else {
                          statusColor = Colors.red;
                          statusText = 'Bận';
                          statusIcon = Icons.access_alarm;
                        }

                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4.0),
                          child: Card(
                            elevation: 4,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12.0),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(16.0),
                              child: Row(
                                children: [
                                  Icon(
                                    statusIcon,
                                    color: statusColor,
                                    size: 24,
                                  ),
                                  const SizedBox(width: 12),
                                  Icon(
                                    Icons.directions_car,
                                    color: Colors.blue[800],
                                    size: 24,
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          agvName,
                                          style: const TextStyle(
                                            fontSize: 18,
                                            fontWeight: FontWeight.bold,
                                            color: Colors.black87,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          'Trạng thái: $statusText',
                                          style: TextStyle(
                                            fontSize: 14,
                                            color: statusColor,
                                            fontWeight: FontWeight.w500,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _newLocationController.dispose();
    super.dispose();
  }
}