import 'package:app_tot/callAGVscreen.dart';
import 'package:app_tot/product_count.dart';
import 'package:flutter/material.dart';
import 'package:app_tot/login_screen.dart';
import 'package:app_tot/dashboard_screen.dart' hide LoginScreen;
import 'package:app_tot/task_execute_screen.dart';
import 'splash_screen.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Transportation Control System',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        scaffoldBackgroundColor: Colors.blue,
      ),
      home: const LoginScreen(),
      //home: const CallAGVScreen(),
      //home: const OrderListScreen(),
      routes: {
        '/dashboard': (context) => const DashboardScreen(),
        '/task-execute': (context) => const TaskExecutedScreen(),
      },
    );
  }
}