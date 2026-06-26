import 'package:flutter/material.dart';

class CheckGoodsDetailScreen extends StatefulWidget {
  final Map<String, dynamic> item;
  final int receivedQuantity;
  final int totalQuantity;
  final Function(int) onConfirm; // Thay đổi để nhận số lượng từ TextField

  const CheckGoodsDetailScreen({
    Key? key,
    required this.item,
    required this.receivedQuantity,
    required this.totalQuantity,
    required this.onConfirm,
  }) : super(key: key);

  @override
  _CheckGoodsDetailScreenState createState() => _CheckGoodsDetailScreenState();
}

class _CheckGoodsDetailScreenState extends State<CheckGoodsDetailScreen> {
  late List<bool> isChecked;
  final TextEditingController _quantityController = TextEditingController();

  @override
  void initState() {
    super.initState();
    // Khởi tạo 4 checkbox cho các thông tin: Mã Hàng, Kích Cỡ, Màu, Số Lượng Thực Nhận
    isChecked = List<bool>.filled(4, false);
    _quantityController.text = '0'; // Giá trị mặc định
  }

  bool get allChecked => isChecked.every((checked) => checked);

  @override
  void dispose() {
    _quantityController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final materialCode = widget.item['materialCode'] ?? 'Không có';
    final size = widget.item['size'] ?? 'Không có';
    final color = widget.item['color'] ?? 'Không có';
    final totalQuantity = widget.totalQuantity;
    final receivedQuantity = widget.receivedQuantity;

    return WillPopScope(
      onWillPop: () async {
        Navigator.pop(context);
        return true;
      },
      child: Scaffold(
        backgroundColor: Colors.grey[100],
        appBar: AppBar(
          leading: IconButton(
            icon: const Icon(Icons.arrow_back, color: Colors.white),
            onPressed: () => Navigator.pop(context),
          ),
          title: const Text(
            'Chi Tiết Nhận Hàng',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
          ),
          backgroundColor: Colors.blue[800],
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
        body: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildTextFieldWithCheck('Mã Hàng', materialCode, 0),
                const SizedBox(height: 16.0),
                _buildTextFieldWithCheck('Kích Cỡ', size, 1),
                const SizedBox(height: 16.0),
                _buildTextFieldWithCheck('Màu', color, 2),
                const SizedBox(height: 16.0),
                _buildTextFieldWithoutCheck('Tổng Số Lượng', totalQuantity.toString()),
                const SizedBox(height: 16.0),
                _buildTextFieldWithCheckAndQuantity('Số Lượng Thực Nhận', receivedQuantity.toString(), 3),
                const SizedBox(height: 20),
                Center(
                  child: ElevatedButton(
                    onPressed: allChecked
                        ? () {
                            final quantityToAdd = int.tryParse(_quantityController.text) ?? 0;
                            if (quantityToAdd <= 0) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Vui lòng nhập số lượng hợp lệ!')),
                              );
                              return;
                            }
                            widget.onConfirm(quantityToAdd);
                            Navigator.pop(context, true);
                          }
                        : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blue,
                      padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 15),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10.0),
                      ),
                    ),
                    child: const Text(
                      'Xác nhận',
                      style: TextStyle(fontSize: 18, color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTextFieldWithCheck(String label, String value, int index) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextField(
            enabled: false,
            style: const TextStyle(color: Colors.black, fontSize: 18),
            decoration: InputDecoration(
              labelText: label,
              labelStyle: const TextStyle(fontSize: 18),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10.0),
              ),
              filled: true,
              fillColor: Colors.white,
            ),
            controller: TextEditingController(text: value),
          ),
        ),
        const SizedBox(width: 10),
        Checkbox(
          value: isChecked[index],
          onChanged: (value) {
            setState(() {
              isChecked[index] = value ?? false;
            });
          },
        ),
      ],
    );
  }

  Widget _buildTextFieldWithoutCheck(String label, String value) {
    return TextField(
      enabled: false,
      style: const TextStyle(color: Colors.black, fontSize: 18),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(fontSize: 18),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10.0),
        ),
        filled: true,
        fillColor: Colors.white,
      ),
      controller: TextEditingController(text: value),
    );
  }

  Widget _buildTextFieldWithCheckAndQuantity(String label, String value, int index) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextField(
            enabled: false,
            style: const TextStyle(color: Colors.black, fontSize: 18),
            decoration: InputDecoration(
              labelText: label,
              labelStyle: const TextStyle(fontSize: 18),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10.0),
              ),
              filled: true,
              fillColor: Colors.white,
            ),
            controller: TextEditingController(text: value),
          ),
        ),
        const SizedBox(width: 10),
        Checkbox(
          value: isChecked[index],
          onChanged: (value) {
            setState(() {
              isChecked[index] = value ?? false;
            });
          },
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 80,
          child: TextField(
            controller: _quantityController,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Số lượng',
              border: OutlineInputBorder(),
            ),
          ),
        ),
      ],
    );
  }
}