import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:google_fonts/google_fonts.dart';

class OrderListScreen extends StatefulWidget {
  const OrderListScreen({Key? key}) : super(key: key);

  @override
  _OrderListScreenState createState() => _OrderListScreenState();
}

class _OrderListScreenState extends State<OrderListScreen> {
  List<Map<String, dynamic>> _orders = [];
  bool isLoading = true;
  String? errorMessage;

  @override
  void initState() {
    super.initState();
    _fetchOrders();
  }

  Future<void> _fetchOrders() async {
    setState(() {
      isLoading = true;
      errorMessage = null;
    });

    try {
      final today = DateTime.now().toLocal();
      final dateStr = "${today.year}-${today.month.toString().padLeft(2, '0')}-${today.day.toString().padLeft(2, '0')}";
      final url = 'http://appmobile.tng.vn/production/api/cat/lenh_cap_btp?maChiNhanh=12';
      print('Fetching orders from API: $url');

      final response = await http.get(
        Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 10), onTimeout: () {
        throw Exception('Request to add-list API timed out');
      });

      print('API response status: ${response.statusCode}');
      print('API response body: ${response.body}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data == null || data['success'] != true || data['data'] == null || data['data'] is! List) {
          setState(() {
            errorMessage = data['message'] ?? 'Dữ liệu từ server không hợp lệ!';
            isLoading = false;
          });
          return;
        }

        final orders = (data['data'] as List).map<Map<String, dynamic>>((order) {
          final createDate = order['createTime'] != null
              ? DateTime.parse(order['createTime']).toLocal()
              : DateTime.now().toLocal();
          return {
            'materialCode': order['materialCode']?.toString() ?? 'Unknown',
            'color': order['color']?.toString() ?? 'Unknown',
            'size': order['size']?.toString().toUpperCase().replaceAll('YEARS', ' years').replaceAll('EARS', '').replaceAll(' ', '') ?? 'Unknown',
            'team': order['team']?.toString() ?? 'Unknown',
            //'quantity': order['quantity'] != null
                //? int.tryParse(order['quantity'].toString()) ?? 0
                //: 0,
            'createTime': createDate.toString().split('.')[0], // Định dạng: YYYY-MM-DD HH:mm:ss
            'creator': order['creator']?.toString() ?? 'Unknown',
            'status': 'Pending', // Giá trị mặc định
          };
        }).toList();

        setState(() {
          _orders = orders;
          isLoading = false;
        });
        print('Parsed orders: $_orders');
      } else {
        setState(() {
          errorMessage = 'Không thể tải đơn hàng: HTTP ${response.statusCode} - ${response.body}';
          isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        errorMessage = 'Lỗi khi tải đơn hàng: $e';
        isLoading = false;
      });
      print('Error fetching orders: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Danh Sách Đơn Hàng',
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
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: _fetchOrders,
            tooltip: 'Làm mới danh sách',
          ),
        ],
      ),
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : errorMessage != null
              ? Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        errorMessage!,
                        style: GoogleFonts.roboto(
                          color: Colors.red,
                          fontSize: 16,
                          textStyle: const TextStyle(fontStyle: FontStyle.italic),
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16.0),
                      ElevatedButton(
                        onPressed: _fetchOrders,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blue,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8.0),
                          ),
                        ),
                        child: Text(
                          'Thử lại',
                          style: GoogleFonts.roboto(fontSize: 16, color: Colors.white),
                        ),
                      ),
                    ],
                  ),
                )
              : _orders.isEmpty
                  ? Center(
                      child: Text(
                        'Không có đơn hàng để hiển thị',
                        style: GoogleFonts.roboto(fontSize: 16, color: Colors.grey),
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                      itemCount: _orders.length,
                      itemBuilder: (context, index) {
                        final order = _orders[index];
                        final isCompleted = order['status'] == 'Completed';

                        return Card(
                          color: Colors.white,
                          elevation: 5,
                          margin: const EdgeInsets.symmetric(vertical: 8.0),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10.0),
                            side: const BorderSide(color: Colors.grey, width: 1),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.all(16.0),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Mã Hàng: ${order['materialCode']}',
                                  style: GoogleFonts.roboto(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.blue,
                                  ),
                                ),
                                const SizedBox(height: 8.0),
                                Text(
                                  'Màu: ${order['color']}',
                                  style: GoogleFonts.roboto(fontSize: 14, color: Colors.black87),
                                ),
                                Text(
                                  'Kích Cỡ: ${order['size']}',
                                  style: GoogleFonts.roboto(fontSize: 14, color: Colors.black87),
                                ),
                                Text(
                                  'Tổ: ${order['team']}',
                                  style: GoogleFonts.roboto(fontSize: 14, color: Colors.black87),
                                ),
                                Text(
                                  'Số Lượng: ${order['quantity']}',
                                  style: GoogleFonts.roboto(fontSize: 14, color: Colors.black87),
                                ),
                                Text(
                                  'Ngày Tạo: ${order['createTime']}',
                                  style: GoogleFonts.roboto(fontSize: 14, color: Colors.black87),
                                ),
                                Text(
                                  'Người Tạo: ${order['creator']}',
                                  style: GoogleFonts.roboto(fontSize: 14, color: Colors.black87),
                                ),
                                Text(
                                  'Trạng Thái: ${order['status'] == 'Completed' ? 'Hoàn thành' : 'Đang xử lý'}',
                                  style: GoogleFonts.roboto(
                                    fontSize: 14,
                                    color: isCompleted ? Colors.green : Colors.orange,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
    );
  }
}