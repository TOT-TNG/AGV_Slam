import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
  final _usernameCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  late AnimationController _animCtrl;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  bool _obscureText = true;
  bool _rememberPassword = false;
  bool _isLoading = false;

  static const _hrLoginUrl =
      'http://appmobile.tng.vn/production/api/auth/login';

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 500));
    _fadeAnim =
        CurvedAnimation(parent: _animCtrl, curve: Curves.easeInOut);
    _slideAnim = Tween<Offset>(
            begin: const Offset(0.3, 0.0), end: Offset.zero)
        .animate(
            CurvedAnimation(parent: _animCtrl, curve: Curves.easeInOut));
    _animCtrl.forward();
    _loadSaved();
  }

  Future<void> _loadSaved() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _usernameCtrl.text = prefs.getString('username') ?? '';
      _rememberPassword = prefs.getBool('remember_password') ?? false;
      if (_rememberPassword) {
        _passwordCtrl.text = prefs.getString('password') ?? '';
      }
    });
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isLoading = true);

    try {
      // ── Bước 1: xác thực với server nhân sự ─────────────────────────
      final hrResp = await http
          .post(
            Uri.parse(_hrLoginUrl),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'username': _usernameCtrl.text.trim(),
              'password': _passwordCtrl.text,
            }),
          )
          .timeout(const Duration(seconds: 10));

      if (!mounted) return;

      if (hrResp.statusCode != 200) {
        final body = jsonDecode(hrResp.body);
        final msg = hrResp.statusCode == 401
            ? 'Tài khoản hoặc mật khẩu không đúng'
            : (body['message'] ?? 'Đăng nhập thất bại: ${hrResp.statusCode}');
        _showError(msg);
        return;
      }

      final hrJson = jsonDecode(hrResp.body) as Map<String, dynamic>;
      if (!hrJson.containsKey('token') || hrJson['token'] == null) {
        _showError(hrJson['message'] ?? 'Đăng nhập thất bại: không nhận được token');
        return;
      }

      // ── Bước 2: lưu thông tin nhân sự ───────────────────────────────
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('username', _usernameCtrl.text.trim());
      await prefs.setString('token', hrJson['token'] ?? '');
      await prefs.setBool('remember_password', _rememberPassword);
      if (_rememberPassword) {
        await prefs.setString('password', _passwordCtrl.text);
      } else {
        await prefs.remove('password');
      }

      final user = (hrJson['user'] as Map<String, dynamic>?) ?? {};
      // ignore: avoid_print
      print('[LOGIN] HR response keys: ${hrJson.keys.toList()} | user keys: ${user.keys.toList()}');
      // ignore: avoid_print
      print('[LOGIN] name=${user['name'] ?? hrJson['name']} | maNS=${user['maNS'] ?? hrJson['maNS']}');
      await prefs.setString('name', user['name'] ?? hrJson['name'] ?? _usernameCtrl.text.trim());
      await prefs.setString('maNS', user['maNS'] ?? hrJson['maNS'] ?? '');
      await prefs.setString('maChiNhanh', user['maChiNhanh'] ?? hrJson['maChiNhanh'] ?? '');
      await prefs.setString('tenDonVi', user['tenDonVi'] ?? hrJson['tenDonVi'] ?? '');
      await prefs.setString('tenPhongBan', user['tenPhongBan'] ?? hrJson['tenPhongBan'] ?? '');

      if (!mounted) return;
      Navigator.pushReplacementNamed(context, '/dashboard');
    } on http.ClientException catch (e) {
      _showError('Không thể kết nối đến server nhân sự:\n$e');
    } catch (e) {
      _showError('Lỗi: $e');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showError(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(msg),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 5)),
    );
  }

  @override
  void dispose() {
    _animCtrl.dispose();
    _usernameCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;

    return Scaffold(
      body: Stack(
        children: [
          // Background gradient
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Colors.blue, Colors.lightBlue],
              ),
            ),
          ),

          // Title
          Positioned(
            top: 60,
            left: 20,
            right: 20,
            child: FadeTransition(
              opacity: _fadeAnim,
              child: Text(
                'Hệ thống giao nhận hàng',
                style: TextStyle(
                  fontSize: screenWidth * 0.07,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          ),

          // Login card
          Positioned.fill(
            top: 160,
            bottom: 50,
            child: SingleChildScrollView(
              child: Center(
                child: FadeTransition(
                  opacity: _fadeAnim,
                  child: SlideTransition(
                    position: _slideAnim,
                    child: Card(
                      elevation: 8,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(20)),
                      margin: const EdgeInsets.symmetric(horizontal: 20),
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Form(
                          key: _formKey,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Text(
                                'Đăng Nhập',
                                style: TextStyle(
                                  fontSize: 22,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 2.0,
                                ),
                                textAlign: TextAlign.center,
                              ),
                              const SizedBox(height: 24),

                              // ── Tài khoản ──
                              TextFormField(
                                controller: _usernameCtrl,
                                decoration: InputDecoration(
                                  labelText: 'Tài khoản',
                                  prefixIcon: const Icon(Icons.person),
                                  border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(10)),
                                  filled: true,
                                  fillColor: Colors.grey[200],
                                ),
                                validator: (v) => (v == null || v.trim().isEmpty)
                                    ? 'Vui lòng nhập tài khoản'
                                    : null,
                              ),
                              const SizedBox(height: 16),

                              // ── Mật khẩu ──
                              TextFormField(
                                controller: _passwordCtrl,
                                obscureText: _obscureText,
                                decoration: InputDecoration(
                                  labelText: 'Mật khẩu',
                                  prefixIcon: const Icon(Icons.lock),
                                  suffixIcon: IconButton(
                                    icon: Icon(_obscureText
                                        ? Icons.visibility_off
                                        : Icons.visibility,
                                        color: Colors.grey),
                                    onPressed: () =>
                                        setState(() => _obscureText = !_obscureText),
                                  ),
                                  border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(10)),
                                  filled: true,
                                  fillColor: Colors.grey[200],
                                ),
                                validator: (v) => (v == null || v.isEmpty)
                                    ? 'Vui lòng nhập mật khẩu'
                                    : null,
                              ),

                              // ── Lưu mật khẩu ──
                              Row(
                                children: [
                                  Checkbox(
                                    value: _rememberPassword,
                                    onChanged: (v) => setState(
                                        () => _rememberPassword = v ?? false),
                                  ),
                                  const Text('Lưu mật khẩu'),
                                ],
                              ),

                              const SizedBox(height: 28),

                              // ── Đăng nhập button ──
                              SizedBox(
                                width: double.infinity,
                                child: ElevatedButton(
                                  onPressed: _isLoading ? null : _login,
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.blue,
                                    padding: const EdgeInsets.symmetric(
                                        vertical: 15),
                                    shape: RoundedRectangleBorder(
                                        borderRadius:
                                            BorderRadius.circular(10)),
                                  ),
                                  child: _isLoading
                                      ? const SizedBox(
                                          width: 22,
                                          height: 22,
                                          child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              color: Colors.white),
                                        )
                                      : const Text(
                                          'ĐĂNG NHẬP',
                                          style: TextStyle(
                                              fontSize: 18,
                                              color: Colors.white),
                                        ),
                                ),
                              ),
                              const SizedBox(height: 16),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),

          // Footer
          const Positioned(
            bottom: 20,
            left: 0,
            right: 0,
            child: Text(
              'Copyright by TOT-TNG',
              style: TextStyle(
                  fontSize: 12,
                  color: Colors.white,
                  fontStyle: FontStyle.italic),
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
  }
}
