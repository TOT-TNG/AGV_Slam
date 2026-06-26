import 'package:flutter/material.dart';

/// Screen placeholder — chức năng nhận hàng từ hệ thống TNG cũ không khả dụng
/// trong AGVmqtt. Giữ lại class để dashboard không bị lỗi import.
class ReceiveGoodsScreen extends StatelessWidget {
  const ReceiveGoodsScreen({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Nhận hàng')),
      body: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.inventory_2_outlined, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text(
              'Tính năng không khả dụng',
              style: TextStyle(fontSize: 18, color: Colors.grey),
            ),
            SizedBox(height: 8),
            Text(
              'Chức năng này thuộc hệ thống TNG cũ.',
              style: TextStyle(color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}
