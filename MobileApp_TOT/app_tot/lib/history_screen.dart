import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:excel/excel.dart' as excel;
import 'dart:io' as io;

class OrderHistory {
  final int id;
  final String materialCode;
  final String color;
  final String size;
  final String team;
  final int totalQuantity;
  final int issuedQuantity;
  final int receivedQuantity;
  final String status;
  final String? confirmTime;
  final String? issuedTime;

  const OrderHistory({
    required this.id,
    required this.materialCode,
    required this.color,
    required this.size,
    required this.team,
    required this.totalQuantity,
    required this.issuedQuantity,
    required this.receivedQuantity,
    required this.status,
    this.confirmTime,
    this.issuedTime,
  });

  factory OrderHistory.fromJson(Map<String, dynamic> json) {
    return OrderHistory(
      id: 0, // Không có trong Finished_Product, mặc định là 0
      materialCode: json['materialCode']?.toString() ?? 'Unknown',
      color: json['mColors']?.toString() ?? 'Unknown',
      size: json['mSizes']?.toString() ?? 'Unknown',
      team: json['team']?.toString() ?? 'Unknown',
      totalQuantity: int.tryParse(json['totalQuantity']?.toString() ?? '0') ?? 0,
      issuedQuantity: int.tryParse(json['issuedQuantity']?.toString() ?? '0') ?? 0,
      receivedQuantity: 0, // Không có trong Finished_Product, mặc định là 0
      status: json['mStatus']?.toString() ?? 'Unknown',
      confirmTime: json['confirmedTime']?.toString(),
      issuedTime: json['issuedTime']?.toString(),
    );
  }
}

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  _HistoryScreenState createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> with SingleTickerProviderStateMixin {
  List<OrderHistory> historyData = [];
  List<OrderHistory> filteredHistoryData = [];
  bool isLoading = true;
  String errorMessage = '';
  DateTimeRange? selectedDateRange;
  String searchMaterialCode = '';
  String searchColor = '';
  String searchSize = '';
  String searchTeam = '';
  String? searchStatus;
  final DateFormat dateFormat = DateFormat('dd/MM/yyyy HH:mm');
  final DateFormat headerDateFormat = DateFormat('dd/MM/yyyy');

  // Controllers for filter fields
  late TextEditingController materialCodeController;
  late TextEditingController colorController;
  late TextEditingController sizeController;
  late TextEditingController teamController;

  // Danh sách gợi ý
  late List<String> materialCodeOptions;
  late List<String> colorOptions;
  late List<String> sizeOptions;
  late List<String> teamOptions;

  // Animation cho biểu tượng check_circle
  late AnimationController _animationController;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    materialCodeController = TextEditingController();
    colorController = TextEditingController();
    sizeController = TextEditingController();
    teamController = TextEditingController();
    materialCodeOptions = [];
    colorOptions = [];
    sizeOptions = [];
    teamOptions = [];
    // Mặc định lọc theo ngày hôm nay
    final now = DateTime.now();
    selectedDateRange = DateTimeRange(
      start: DateTime(now.year, now.month, now.day, 0, 0, 0),
      end: DateTime(now.year, now.month, now.day, 23, 59, 59, 999),
    );
    // Khởi tạo animation
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _scaleAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeOutBack),
    );
    _animationController.forward();
    fetchHistory();
  }

  Future<void> fetchHistory() async {
    if (!mounted) return;
    setState(() {
      isLoading = true;
      errorMessage = '';
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString('token') ?? '';
      if (token.isEmpty) {
        if (mounted) {
          setState(() {
            isLoading = false;
            errorMessage = 'Token rỗng. Vui lòng đăng nhập lại.';
          });
        }
        return;
      }

      final startDate = selectedDateRange?.start ?? DateTime.now();
      final endDate = selectedDateRange?.end ?? DateTime.now();
      final startOfDay = DateTime(startDate.year, startDate.month, startDate.day, 0, 0, 0);
      final endOfDay = DateTime(endDate.year, endDate.month, endDate.day, 23, 59, 59, 999);
      final uri = Uri.parse('http://103.101.161.216:7000/api/agv/get-delivery-history').replace(
        queryParameters: {
          if (searchMaterialCode.isNotEmpty) 'materialCode': searchMaterialCode,
          if (searchColor.isNotEmpty) 'mColors': searchColor,
          if (searchSize.isNotEmpty) 'mSizes': searchSize,
          if (searchTeam.isNotEmpty) 'team': searchTeam,
          if (searchStatus != null) 'mStatus': searchStatus,
          'startTime': startOfDay.toUtc().toIso8601String(),
          'endTime': endOfDay.toUtc().toIso8601String(),
        },
      );

      print('Fetching delivery history: $uri');

      final response = await http.get(
        uri,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'JWT $token',
        },
      ).timeout(const Duration(seconds: 30));

      print('API response: ${response.statusCode} - ${response.body}');

      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['success'] == true) {
          final List<OrderHistory> parsedData = (data['data'] as List)
              .map((item) => OrderHistory.fromJson(item))
              .toList();

          if (mounted) {
            setState(() {
              historyData = parsedData;
              filteredHistoryData = List.from(parsedData);
              materialCodeOptions = historyData.map((e) => e.materialCode).toSet().toList();
              colorOptions = historyData.map((e) => e.color).toSet().toList();
              sizeOptions = historyData.map((e) => e.size).toSet().toList();
              teamOptions = historyData.map((e) => e.team).toSet().toList();
              isLoading = false;
            });
            _animationController.forward(from: 0.0); // Reset animation
            print('Fetched ${parsedData.length} records');
          }
        } else {
          if (mounted) {
            setState(() {
              isLoading = false;
              errorMessage = data['message'] ?? 'Không tìm thấy dữ liệu lịch sử.';
            });
            print('API error: ${data['message']}');
          }
        }
      } else if (response.statusCode == 401) {
        if (mounted) {
          setState(() {
            isLoading = false;
            errorMessage = 'Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.';
          });
          print('Unauthorized: HTTP 401');
        }
      } else {
        if (mounted) {
          setState(() {
            isLoading = false;
            errorMessage = 'Lỗi tải dữ liệu: ${response.statusCode} - ${response.body}';
          });
          print('Failed to fetch data: HTTP ${response.statusCode}');
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          isLoading = false;
          errorMessage = 'Lỗi kết nối: $e';
        });
        print('Error fetching history: $e');
      }
    }
  }

  Future<void> exportOrderHistoryToExcel() async {
    try {
      final directory = await getApplicationDocumentsDirectory();
      var excelFile = excel.Excel.createExcel();
      var sheet = excelFile['OrderHistory'];

      sheet.appendRow([
        'Material Code',
        'Color',
        'Size',
        'Team',
        'Total Quantity',
        'Issued Quantity',
        'Received Quantity',
        'Status',
        'Confirm Time',
        'Issued Time',
      ]);

      if (filteredHistoryData.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Không có dữ liệu để xuất.')),
        );
        return;
      }

      for (var item in filteredHistoryData) {
        sheet.appendRow([
          item.materialCode,
          item.color,
          item.size,
          item.team,
          item.totalQuantity.toString(),
          item.issuedQuantity.toString(),
          item.receivedQuantity.toString(),
          item.status,
          item.confirmTime ?? '',
          item.issuedTime ?? '',
        ]);
      }

      final filePath = '${directory.path}/OrderHistory_${DateTime.now().millisecondsSinceEpoch}.xlsx';
      var fileBytes = excelFile.encode();
      if (fileBytes == null) {
        throw Exception('Failed to encode Excel file');
      }
      await io.File(filePath).writeAsBytes(fileBytes);

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Xuất file Excel thành công: $filePath\nMở File Manager để xem.'),
          duration: const Duration(seconds: 5),
        ),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Lỗi khi xuất Excel: $e')),
      );
    }
  }

  Future<void> _pickDateRange() async {
    final now = DateTime.now();
    final DateTimeRange? picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2020),
      lastDate: DateTime(2025, 12, 31), // Cho phép chọn đến cuối 2025
      initialDateRange: selectedDateRange ?? DateTimeRange(
        start: DateTime(now.year, now.month, now.day, 0, 0, 0),
        end: DateTime(now.year, now.month, now.day, 23, 59, 59, 999),
      ),
      builder: (context, child) {
        return Theme(
          data: ThemeData.light().copyWith(
            colorScheme: const ColorScheme.light(
              primary: Colors.blue,
              onPrimary: Colors.white,
              surface: Colors.white,
              onSurface: Colors.black,
            ),
            textTheme: const TextTheme(
              headlineMedium: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, fontFamily: 'Roboto'),
              bodyMedium: TextStyle(fontSize: 16, fontFamily: 'Roboto', color: Colors.black), // Đảm bảo chữ đen
            ),
            dialogBackgroundColor: Colors.white,
            textButtonTheme: TextButtonThemeData(
              style: TextButton.styleFrom(
                foregroundColor: Colors.blue, // Nút trong dialog màu xanh
                textStyle: const TextStyle(fontFamily: 'Roboto', color: Colors.black),
              ),
            ),
          ),
          child: child!,
        );
      },
    );

    if (picked != null && mounted) {
      setState(() {
        selectedDateRange = DateTimeRange(
          start: DateTime(picked.start.year, picked.start.month, picked.start.day, 0, 0, 0),
          end: DateTime(picked.end.year, picked.end.month, picked.end.day, 23, 59, 59, 999),
        );
        fetchHistory();
      });
    }
  }

  void applyFilters() {
    setState(() {
      searchMaterialCode = materialCodeController.text.trim();
      searchColor = colorController.text.trim();
      searchSize = sizeController.text.trim();
      searchTeam = teamController.text.trim();
      fetchHistory();
    });
    Navigator.pop(context);
  }

  void clearFilters() {
    if (!mounted) return;
    setState(() {
      final now = DateTime.now();
      selectedDateRange = DateTimeRange(
        start: DateTime(now.year, now.month, now.day, 0, 0, 0),
        end: DateTime(now.year, now.month, now.day, 23, 59, 59, 999),
      );
      searchMaterialCode = '';
      searchColor = '';
      searchSize = '';
      searchTeam = '';
      searchStatus = null;
      materialCodeController.clear();
      colorController.clear();
      sizeController.clear();
      teamController.clear();
      fetchHistory();
    });
    Navigator.pop(context);
  }

  void showFilterDialog() {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text(
            selectedDateRange == null
                ? 'Lọc Lịch Sử Đơn Hàng'
                : 'Lọc Đơn Hàng (${headerDateFormat.format(selectedDateRange!.start)} - ${headerDateFormat.format(selectedDateRange!.end)})',
            style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.blue, fontFamily: 'Roboto'),
          ),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Thông tin đơn hàng',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.grey, fontFamily: 'Roboto'),
                ),
                const SizedBox(height: 12),
                Autocomplete<String>(
                  optionsBuilder: (TextEditingValue textEditingValue) {
                    return textEditingValue.text.isEmpty
                        ? materialCodeOptions
                        : materialCodeOptions.where((option) => option.toLowerCase().contains(textEditingValue.text.toLowerCase()));
                  },
                  onSelected: (String selection) {
                    setState(() {
                      searchMaterialCode = selection;
                      materialCodeController.text = selection;
                    });
                  },
                  fieldViewBuilder: (BuildContext context, TextEditingController fieldController, FocusNode focusNode, VoidCallback onFieldSubmitted) {
                    fieldController.text = materialCodeController.text;
                    return TextField(
                      controller: fieldController,
                      focusNode: focusNode,
                      decoration: InputDecoration(
                        labelText: 'Mã Hàng',
                        labelStyle: const TextStyle(color: Colors.blue, fontFamily: 'Roboto'),
                        prefixIcon: const Icon(Icons.search, color: Colors.blue),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                        filled: true,
                        fillColor: Colors.grey[100],
                      ),
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.black),
                      onSubmitted: (value) {
                        onFieldSubmitted();
                        setState(() {
                          searchMaterialCode = fieldController.text.trim();
                        });
                      },
                    );
                  },
                ),
                const SizedBox(height: 12),
                Autocomplete<String>(
                  optionsBuilder: (TextEditingValue textEditingValue) {
                    return textEditingValue.text.isEmpty
                        ? colorOptions
                        : colorOptions.where((option) => option.toLowerCase().contains(textEditingValue.text.toLowerCase()));
                  },
                  onSelected: (String selection) {
                    setState(() {
                      searchColor = selection;
                      colorController.text = selection;
                    });
                  },
                  fieldViewBuilder: (BuildContext context, TextEditingController fieldController, FocusNode focusNode, VoidCallback onFieldSubmitted) {
                    fieldController.text = colorController.text;
                    return TextField(
                      controller: fieldController,
                      focusNode: focusNode,
                      decoration: InputDecoration(
                        labelText: 'Màu',
                        labelStyle: const TextStyle(color: Colors.blue, fontFamily: 'Roboto'),
                        prefixIcon: const Icon(Icons.color_lens, color: Colors.blue),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                        filled: true,
                        fillColor: Colors.grey[100],
                      ),
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.black),
                      onSubmitted: (value) {
                        onFieldSubmitted();
                        setState(() {
                          searchColor = fieldController.text.trim();
                        });
                      },
                    );
                  },
                ),
                const SizedBox(height: 12),
                Autocomplete<String>(
                  optionsBuilder: (TextEditingValue textEditingValue) {
                    return textEditingValue.text.isEmpty
                        ? sizeOptions
                        : sizeOptions.where((option) => option.toLowerCase().contains(textEditingValue.text.toLowerCase()));
                  },
                  onSelected: (String selection) {
                    setState(() {
                      searchSize = selection;
                      sizeController.text = selection;
                    });
                  },
                  fieldViewBuilder: (BuildContext context, TextEditingController fieldController, FocusNode focusNode, VoidCallback onFieldSubmitted) {
                    fieldController.text = sizeController.text;
                    return TextField(
                      controller: fieldController,
                      focusNode: focusNode,
                      decoration: InputDecoration(
                        labelText: 'Kích Thước',
                        labelStyle: const TextStyle(color: Colors.blue, fontFamily: 'Roboto'),
                        prefixIcon: const Icon(Icons.straighten, color: Colors.blue),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                        filled: true,
                        fillColor: Colors.grey[100],
                      ),
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.black),
                      onSubmitted: (value) {
                        onFieldSubmitted();
                        setState(() {
                          searchSize = fieldController.text.trim();
                        });
                      },
                    );
                  },
                ),
                const SizedBox(height: 12),
                Autocomplete<String>(
                  optionsBuilder: (TextEditingValue textEditingValue) {
                    return textEditingValue.text.isEmpty
                        ? teamOptions
                        : teamOptions.where((option) => option.toLowerCase().contains(textEditingValue.text.toLowerCase()));
                  },
                  onSelected: (String selection) {
                    setState(() {
                      searchTeam = selection;
                      teamController.text = selection;
                    });
                  },
                  fieldViewBuilder: (BuildContext context, TextEditingController fieldController, FocusNode focusNode, VoidCallback onFieldSubmitted) {
                    fieldController.text = teamController.text;
                    return TextField(
                      controller: fieldController,
                      focusNode: focusNode,
                      decoration: InputDecoration(
                        labelText: 'Tổ',
                        labelStyle: const TextStyle(color: Colors.blue, fontFamily: 'Roboto'),
                        prefixIcon: const Icon(Icons.group, color: Colors.blue),
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                        filled: true,
                        fillColor: Colors.grey[100],
                      ),
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.black),
                      onSubmitted: (value) {
                        onFieldSubmitted();
                        setState(() {
                          searchTeam = fieldController.text.trim();
                        });
                      },
                    );
                  },
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: searchStatus,
                  hint: const Text(
                    'Trạng Thái',
                    style: TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.blue),
                  ),
                  decoration: InputDecoration(
                    prefixIcon: const Icon(Icons.check_circle_outline, color: Colors.blue),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    filled: true,
                    fillColor: Colors.grey[100],
                  ),
                  style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.black),
                  dropdownColor: Colors.white,
                  items: <String?>['Pending', 'Completed', null].map((String? value) {
                    return DropdownMenuItem<String>(
                      value: value,
                      child: Text(
                        value ?? 'Tất cả',
                        style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.black),
                      ),
                    );
                  }).toList(),
                  onChanged: (String? newValue) {
                    setState(() {
                      searchStatus = newValue;
                    });
                  },
                ),
                const SizedBox(height: 16),
                const Text(
                  'Thời gian',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.grey, fontFamily: 'Roboto'),
                ),
                const SizedBox(height: 12),
                ElevatedButton(
                  onPressed: _pickDateRange,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blue[700],
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    minimumSize: const Size(double.infinity, 0),
                    elevation: 4,
                  ),
                  child: Text(
                    selectedDateRange == null
                        ? 'Chọn Khoảng Thời Gian'
                        : 'Từ ${headerDateFormat.format(selectedDateRange!.start)} đến ${headerDateFormat.format(selectedDateRange!.end)}',
                    style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600, color: Colors.white),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    ElevatedButton(
                      onPressed: applyFilters,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.blue[700],
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                        elevation: 4,
                      ),
                      child: const Text(
                        'Áp Dụng',
                        style: TextStyle(fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600, color: Colors.white),
                      ),
                    ),
                    ElevatedButton(
                      onPressed: clearFilters,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.red[300],
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                        elevation: 4,
                      ),
                      child: const Text(
                        'Xóa Lọc',
                        style: TextStyle(fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600, color: Colors.white),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void showOrderDetails(OrderHistory item) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            'Chi Tiết Đơn Hàng: ${item.materialCode}',
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: Colors.blue,
              fontFamily: 'Roboto',
            ),
          ),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    const Icon(Icons.color_lens, size: 20, color: Colors.blue),
                    const SizedBox(width: 8),
                    Text(
                      'Màu: ${item.color}',
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Icon(Icons.straighten, size: 20, color: Colors.blue),
                    const SizedBox(width: 8),
                    Text(
                      'Kích Thước: ${item.size}',
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Icon(Icons.group, size: 20, color: Colors.blue),
                    const SizedBox(width: 8),
                    Text(
                      'Tổ: ${item.team}',
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Icon(Icons.production_quantity_limits, size: 20, color: Colors.blue),
                    const SizedBox(width: 8),
                    Text(
                      'Số lượng: ${item.issuedQuantity}',
                      style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Icon(
                      item.status == 'Completed' ? Icons.check_circle : Icons.pending,
                      size: 20,
                      color: item.status == 'Completed' ? Colors.green : Colors.orange,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Trạng Thái: ${item.status}',
                      style: TextStyle(
                        fontSize: 14,
                        fontFamily: 'Roboto',
                        fontWeight: FontWeight.w600,
                        color: item.status == 'Completed' ? Colors.green : Colors.orange,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                if (item.issuedTime != null)
                  Row(
                    children: [
                      const Icon(Icons.schedule, size: 20, color: Colors.grey),
                      const SizedBox(width: 8),
                      Text(
                        'Phát Hành: ${dateFormat.format(DateTime.parse(item.issuedTime!))}',
                        style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.grey),
                      ),
                    ],
                  ),
                const SizedBox(height: 12),
                if (item.confirmTime != null)
                  Row(
                    children: [
                      const Icon(Icons.verified, size: 20, color: Colors.grey),
                      const SizedBox(width: 8),
                      Text(
                        'Xác Nhận: ${dateFormat.format(DateTime.parse(item.confirmTime!))}',
                        style: const TextStyle(fontSize: 14, fontFamily: 'Roboto', color: Colors.grey),
                      ),
                    ],
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text(
                'Đóng',
                style: TextStyle(color: Colors.blue, fontSize: 14, fontFamily: 'Roboto', fontWeight: FontWeight.w600),
              ),
            ),
          ],
        );
      },
    );
  }

  @override
  void dispose() {
    materialCodeController.dispose();
    colorController.dispose();
    sizeController.dispose();
    teamController.dispose();
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final textScaleFactor = screenWidth < 360 ? 0.9 : 1.0; // Responsive font size

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Lịch Sử Đơn Hàng',
          style: TextStyle(fontFamily: 'Roboto', fontWeight: FontWeight.bold),
        ),
        flexibleSpace: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [Colors.blue[800]!, Colors.blue[600]!],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
        ),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, size: 28),
            onPressed: fetchHistory,
            tooltip: 'Làm mới',
            splashRadius: 24,
          ),
          IconButton(
            icon: const Icon(Icons.filter_list, size: 28),
            onPressed: showFilterDialog,
            tooltip: 'Lọc dữ liệu',
            splashRadius: 24,
          ),
          IconButton(
            icon: const Icon(Icons.download, size: 28),
            onPressed: () async {
              await exportOrderHistoryToExcel();
            },
            tooltip: 'Xuất Excel',
            splashRadius: 24,
          ),
          /*IconButton(
            icon: const Icon(Icons.home,color: Colors.white),
            onPressed: () => Navigator.pop(context)
          ,)*/
        ],
      ),
      backgroundColor: Colors.grey[100],
      body: RefreshIndicator(
        onRefresh: fetchHistory,
        color: Colors.blue,
        child: isLoading
            ? const Center(child: CircularProgressIndicator(color: Colors.blue))
            : errorMessage.isNotEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          errorMessage,
                          style: TextStyle(
                            fontSize: 14 * textScaleFactor,
                            color: Colors.red,
                            fontFamily: 'Roboto',
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: fetchHistory,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.blue,
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                            elevation: 4,
                          ),
                          child: Text(
                            'Thử lại',
                            style: TextStyle(fontSize: 14 * textScaleFactor, fontFamily: 'Roboto', fontWeight: FontWeight.w600),
                          ),
                        ),
                      ],
                    ),
                  )
                : Column(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(16),
                        margin: const EdgeInsets.only(bottom: 8),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          boxShadow: [
                            BoxShadow(
                              color: Colors.grey.withOpacity(0.2),
                              spreadRadius: 2,
                              blurRadius: 4,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        width: double.infinity,
                        child: Text(
                          selectedDateRange == null
                              ? 'Đơn hàng ngày ${headerDateFormat.format(DateTime.now())}'
                              : 'Đơn hàng từ ${headerDateFormat.format(selectedDateRange!.start)} đến ${headerDateFormat.format(selectedDateRange!.end)}',
                          style: TextStyle(
                            fontSize: 18 * textScaleFactor,
                            fontWeight: FontWeight.bold,
                            color: Colors.blue[800],
                            fontFamily: 'Roboto',
                          ),
                        ),
                      ),
                      Expanded(
                        child: ListView.builder(
                          padding: const EdgeInsets.all(12.0),
                          physics: const BouncingScrollPhysics(),
                          itemCount: filteredHistoryData.length,
                          itemBuilder: (context, index) {
                            final item = filteredHistoryData[index];
                            return Card(
                              elevation: 4,
                              margin: const EdgeInsets.symmetric(vertical: 12.0, horizontal: 8.0),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: Container(
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    colors: item.status == 'Completed'
                                        ? [Colors.green[50]!, Colors.green[100]!]
                                        : [Colors.white, Colors.grey[50]!],
                                    begin: Alignment.topLeft,
                                    end: Alignment.bottomRight,
                                  ),
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Stack(
                                  children: [
                                    InkWell(
                                      onTap: () => showOrderDetails(item),
                                      borderRadius: BorderRadius.circular(16),
                                      splashColor: Colors.blue.withOpacity(0.2),
                                      highlightColor: Colors.blue.withOpacity(0.1),
                                      child: Padding(
                                        padding: const EdgeInsets.all(16.0),
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              'Mã Hàng: ${item.materialCode}',
                                              style: TextStyle(
                                                fontSize: 18 * textScaleFactor,
                                                fontWeight: FontWeight.bold,
                                                color: Colors.blue[800],
                                                fontFamily: 'Roboto',
                                              ),
                                            ),
                                            const SizedBox(height: 12),
                                            Row(
                                              children: [
                                                const Icon(Icons.color_lens, size: 20, color: Colors.blue),
                                                const SizedBox(width: 8),
                                                Text(
                                                  'Màu: ${item.color}',
                                                  style: TextStyle(
                                                    fontSize: 14 * textScaleFactor,
                                                    fontFamily: 'Roboto',
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                                ),
                                              ],
                                            ),
                                            const SizedBox(height: 12),
                                            Row(
                                              children: [
                                                const Icon(Icons.straighten, size: 20, color: Colors.blue),
                                                const SizedBox(width: 8),
                                                Text(
                                                  'Kích Thước: ${item.size}',
                                                  style: TextStyle(
                                                    fontSize: 14 * textScaleFactor,
                                                    fontFamily: 'Roboto',
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                                ),
                                              ],
                                            ),
                                            const SizedBox(height: 12),
                                            Row(
                                              children: [
                                                const Icon(Icons.group, size: 20, color: Colors.blue),
                                                const SizedBox(width: 8),
                                                Text(
                                                  'Tổ: ${item.team}',
                                                  style: TextStyle(
                                                    fontSize: 14 * textScaleFactor,
                                                    fontFamily: 'Roboto',
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                                ),
                                              ],
                                            ),
                                            const SizedBox(height: 12),
                                            Row(
                                              children: [
                                                const Icon(Icons.production_quantity_limits, size: 20, color: Colors.blue),
                                                const SizedBox(width: 8),
                                                Text(
                                                  'Số lượng: ${item.issuedQuantity}',
                                                  style: TextStyle(
                                                    fontSize: 14 * textScaleFactor,
                                                    fontFamily: 'Roboto',
                                                    fontWeight: FontWeight.w600,
                                                  ),
                                                ),
                                              ],
                                            ),
                                            const SizedBox(height: 12),
                                            Row(
                                              children: [
                                                Icon(
                                                  item.status == 'Completed' ? Icons.check_circle : Icons.pending,
                                                  size: 20,
                                                  color: item.status == 'Completed' ? Colors.green : Colors.orange,
                                                ),
                                                const SizedBox(width: 8),
                                                Text(
                                                  'Trạng Thái: ${item.status}',
                                                  style: TextStyle(
                                                    fontSize: 14 * textScaleFactor,
                                                    fontFamily: 'Roboto',
                                                    fontWeight: FontWeight.w600,
                                                    color: item.status == 'Completed' ? Colors.green : Colors.orange,
                                                  ),
                                                ),
                                              ],
                                            ),
                                            const SizedBox(height: 12),
                                            if (item.issuedTime != null)
                                              Row(
                                                children: [
                                                  const Icon(Icons.schedule, size: 20, color: Colors.grey),
                                                  const SizedBox(width: 8),
                                                  Text(
                                                    'Phát Hành: ${dateFormat.format(DateTime.parse(item.issuedTime!))}',
                                                    style: TextStyle(
                                                      fontSize: 14 * textScaleFactor,
                                                      fontFamily: 'Roboto',
                                                      color: Colors.grey,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            const SizedBox(height: 12),
                                            if (item.confirmTime != null)
                                              Row(
                                                children: [
                                                  const Icon(Icons.verified, size: 20, color: Colors.grey),
                                                  const SizedBox(width: 8),
                                                  Text(
                                                    'Xác Nhận: ${dateFormat.format(DateTime.parse(item.confirmTime!))}',
                                                    style: TextStyle(
                                                      fontSize: 14 * textScaleFactor,
                                                      fontFamily: 'Roboto',
                                                      color: Colors.grey,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                          ],
                                        ),
                                      ),
                                    ),
                                    if (item.status == 'Completed')
                                      Positioned(
                                        top: 12,
                                        right: 12,
                                        child: ScaleTransition(
                                          scale: _scaleAnimation,
                                          child: const Icon(
                                            Icons.check_circle,
                                            color: Colors.green,
                                            size: 28,
                                          ),
                                        ),
                                      ),
                                  ],
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
}