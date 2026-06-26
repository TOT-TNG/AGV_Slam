import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'team_mapping.dart';
import 'services/api_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  _SettingsScreenState createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _name = 'Unknown';
  String _tenPhongBan = 'Unknown';
  String _userId = '';
  String _maChiNhanh = 'Unknown';
  String _siteId = 'default';
  static const String _mappingEditPassword = 'TNG12345';

  // Server URL config
  final _serverUrlCtrl = TextEditingController();
  bool _isTestingServer = false;
  String? _serverTestResult;
  bool _isEditingServerUrl = false;

  // Gateway Key config
  final _gatewayKeyCtrl = TextEditingController();
  bool _isEditingGatewayKey = false;

  // Factory (map) selection
  List<Map<String, dynamic>> _maps = [];
  String? _selectedMapId;
  bool _isLoadingMaps = false;
  String? _mapsLoadError;

  List<TeamMapping> _teamMappings = [];

  bool _isUserInfoLoaded = false;
  bool _isEditingMapping = false;
  String? _successMessage;

  @override
  void initState() {
    super.initState();
    _initializeData();
  }

  String normalizeLatinKey(String input, {bool upper = true}) {
    var s = input.trim();

    s = s.replaceAll('Đ', 'D').replaceAll('đ', 'd');

    const Map<String, String> vietnameseMap = {
      'á':'a','à':'a','ả':'a','ã':'a','ạ':'a',
      'ă':'a','ắ':'a','ằ':'a','ẳ':'a','ẵ':'a','ặ':'a',
      'â':'a','ấ':'a','ầ':'a','ẩ':'a','ẫ':'a','ậ':'a',
      'Á':'A','À':'A','Ả':'A','Ã':'A','Ạ':'A',
      'Ă':'A','Ắ':'A','Ằ':'A','Ẳ':'A','Ẵ':'A','Ặ':'A',
      'Â':'A','Ấ':'A','Ầ':'A','Ẩ':'A','Ẫ':'A','Ậ':'A',

      'é':'e','è':'e','ẻ':'e','ẽ':'e','ẹ':'e',
      'ê':'e','ế':'e','ề':'e','ể':'e','ễ':'e','ệ':'e',
      'É':'E','È':'E','Ẻ':'E','Ẽ':'E','Ẹ':'E',
      'Ê':'E','Ế':'E','Ề':'E','Ể':'E','Ễ':'E','Ệ':'E',

      'í':'i','ì':'i','ỉ':'i','ĩ':'i','ị':'i',
      'Í':'I','Ì':'I','Ỉ':'I','Ĩ':'I','Ị':'I',

      'ó':'o','ò':'o','ỏ':'o','õ':'o','ọ':'o',
      'ô':'o','ố':'o','ồ':'o','ổ':'o','ỗ':'o','ộ':'o',
      'ơ':'o','ớ':'o','ờ':'o','ở':'o','ỡ':'o','ợ':'o',
      'Ó':'O','Ò':'O','Ỏ':'O','Õ':'O','Ọ':'O',
      'Ô':'O','Ố':'O','Ồ':'O','Ổ':'O','Ỗ':'O','Ộ':'O',
      'Ơ':'O','Ớ':'O','Ờ':'O','Ở':'O','Ỡ':'O','Ợ':'O',

      'ú':'u','ù':'u','ủ':'u','ũ':'u','ụ':'u',
      'ư':'u','ứ':'u','ừ':'u','ử':'u','ữ':'u','ự':'u',
      'Ú':'U','Ù':'U','Ủ':'U','Ũ':'U','Ụ':'U',
      'Ư':'U','Ứ':'U','Ừ':'U','Ử':'U','Ữ':'U','Ự':'U',

      'ý':'y','ỳ':'y','ỷ':'y','ỹ':'y','ỵ':'y',
      'Ý':'Y','Ỳ':'Y','Ỷ':'Y','Ỹ':'Y','Ỵ':'Y',
    };

    final buffer = StringBuffer();
    for (final ch in s.split('')) {
      buffer.write(vietnameseMap[ch] ?? ch);
    }

    s = buffer.toString();
    s = s.replaceAll(RegExp(r'\s+'), ' ');

    return upper ? s.toUpperCase() : s;
  }

  Future<void> _initializeData() async {
    await _loadUserInfo();
    await _loadTeamMappings();
    final url = await ApiService.baseUrl;
    final key = await ApiService.gatewayKey;
    final prefs = await SharedPreferences.getInstance();
    if (mounted) {
      _serverUrlCtrl.text = url;
      _gatewayKeyCtrl.text = key ?? '';
      setState(() {
        _selectedMapId = prefs.getString('selected_map_id');
        _isUserInfoLoaded = true;
      });
    }
    _loadMaps();
  }

  Future<void> _loadMaps() async {
    if (mounted) setState(() { _isLoadingMaps = true; _mapsLoadError = null; });
    try {
      final maps = await ApiService.getMaps();
      if (mounted) setState(() { _maps = maps; _isLoadingMaps = false; });
    } catch (_) {
      if (mounted) setState(() {
        _isLoadingMaps = false;
        _mapsLoadError = 'Không tải được danh sách nhà máy.\nKiểm tra kết nối máy chủ.';
      });
    }
  }

  Future<void> _selectMap(String mapId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('selected_map_id', mapId);
    if (mounted) setState(() => _selectedMapId = mapId);
  }

  Future<void> _saveServerUrl() async {
    final url = _serverUrlCtrl.text.trim();
    if (url.isEmpty || !url.startsWith('http')) {
      setState(() => _serverTestResult = 'URL không hợp lệ (phải bắt đầu bằng http://)');
      return;
    }
    setState(() {
      _isTestingServer = true;
      _serverTestResult = null;
    });
    await ApiService.setBaseUrl(url);
    final ok = await ApiService.ping();
    if (mounted) {
      setState(() {
        _isTestingServer = false;
        _isEditingServerUrl = false;
        _serverTestResult = ok ? 'Kết nối thành công!' : 'Không thể kết nối. Kiểm tra IP/port và server.';
      });
    }
  }

  Future<void> _authenticateAndEditServerUrl() async {
    final ok = await _showPasswordDialog();
    if (!ok) return;
    if (mounted) setState(() => _isEditingServerUrl = true);
  }

  Future<bool> _showPasswordDialog() async {
  final passwordController = TextEditingController();
  String? errorText;
  bool obscureText = true;

  final result = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (context) {
      return StatefulBuilder(
        builder: (context, setDialogState) {
          return AlertDialog(
            title: const Text('Xác thực kỹ thuật'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Vui lòng nhập mật khẩu.',
                  style: TextStyle(fontSize: 14),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: passwordController,
                  obscureText: obscureText,
                  autofocus: true,
                  decoration: InputDecoration(
                    labelText: 'Mật khẩu',
                    errorText: errorText,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                    suffixIcon: IconButton(
                      icon: Icon(
                        obscureText ? Icons.visibility_off : Icons.visibility,
                      ),
                      onPressed: () {
                        setDialogState(() {
                          obscureText = !obscureText;
                        });
                      },
                    ),
                  ),
                  onSubmitted: (_) {
                    final input = passwordController.text.trim();
                    if (input == _mappingEditPassword) {
                      Navigator.pop(context, true);
                    } else {
                      setDialogState(() {
                        errorText = 'Mật khẩu không đúng';
                      });
                    }
                  },
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Hủy'),
              ),
              ElevatedButton(
                onPressed: () {
                  final input = passwordController.text.trim();
                  if (input == _mappingEditPassword) {
                    Navigator.pop(context, true);
                  } else {
                    setDialogState(() {
                      errorText = 'Mật khẩu không đúng';
                    });
                  }
                },
                child: const Text('Xác nhận'),
              ),
            ],
          );
        },
      );
    },
  );

  return result == true;
}

  Future<void> _authenticateAndStartEditing() async {
  final ok = await _showPasswordDialog();
  if (!ok) return;

  if (mounted) {
    setState(() {
      _isEditingMapping = true;
    });
  }
}

Future<void> _authenticateAndAddMapping() async {
  final ok = await _showPasswordDialog();
  if (!ok) return;

  if (!_isEditingMapping) {
    setState(() {
      _isEditingMapping = true;
    });
  }

  _addMappingRow();
}

  Future<void> _loadUserInfo() async {
    final prefs = await SharedPreferences.getInstance();

    final rawSiteId = prefs.getString('tenDonVi') ?? '';
    setState(() {
      _name = prefs.getString('name') ?? 'Unknown';
      _tenPhongBan = prefs.getString('tenPhongBan') ?? 'Unknown';
      _userId = prefs.getString('maNS') ?? '';
      _maChiNhanh = prefs.getString('maChiNhanh') ?? 'Unknown';
      _siteId = normalizeLatinKey(rawSiteId, upper: false).trim().isEmpty
          ? 'default'
          : normalizeLatinKey(rawSiteId, upper: false).trim();
    });

    print('Loaded user info - name: "$_name", tenPhongBan: "$_tenPhongBan", userId: "$_userId", maChiNhanh: "$_maChiNhanh", siteId: "$_siteId"');
  }

  String get _mappingPrefsKey {
    final uid = _userId.isEmpty ? 'guest' : _userId;
    final sid = _siteId.isEmpty ? 'default' : _siteId;
    return 'team_mappings_${uid}_$sid';
  }

  Future<void> _loadTeamMappings() async {
    if (_userId.isEmpty) {
      print('UserId empty, cannot load mappings');
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_mappingPrefsKey);

    if (raw == null || raw.isEmpty) {
      setState(() {
        _teamMappings = [];
      });
      print('No saved team mappings');
      return;
    }

    try {
      final List<dynamic> decoded = jsonDecode(raw);
      final mappings = decoded
          .map((e) => TeamMapping.fromJson(Map<String, dynamic>.from(e)))
          .where((e) => e.label.trim().isNotEmpty && e.line >= 1 && e.line <= 50)
          .toList();

      mappings.sort((a, b) => a.line.compareTo(b.line));

      if (mounted) {
        setState(() {
          _teamMappings = mappings;
        });
      }

      //print('Loaded team mappings: ${mappings.map((e) => "${e.label} -> ${e.line}").toList()}');
      print('Loaded team mappings: ${mappings.map((e) => "${e.label} -> ${e.line}").toList()}');
    } catch (e) {
      print('Load team mappings error: $e');
      if (mounted) {
        setState(() {
          _teamMappings = [];
        });
      }
    }
  }

  Future<void> _saveTeamMappings() async {
    if (_userId.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Không tìm thấy thông tin tài khoản! Vui lòng đăng nhập lại.'),
          action: SnackBarAction(
            label: 'Đăng nhập',
            textColor: Colors.blue,
            onPressed: _navigateToLogin,
          ),
        ),
      );
      return;
    }

    final validMappings = _teamMappings
        .where((e) => e.label.trim().isNotEmpty && e.line >= 1 && e.line <= 50)
        .map((e) => TeamMapping(label: e.label.trim(), line: e.line))
        .toList();

    final labelKeys = validMappings
        .map((e) => normalizeLatinKey(e.label, upper: false).trim())
        .toList();

    if (labelKeys.length != labelKeys.toSet().length) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Tên tổ đang bị trùng. Vui lòng kiểm tra lại.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    final lines = validMappings.map((e) => e.line).toList();
    if (lines.length != lines.toSet().length) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Số line đang bị trùng. Vui lòng kiểm tra lại.'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    validMappings.sort((a, b) => a.line.compareTo(b.line));

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _mappingPrefsKey,
      jsonEncode(validMappings.map((e) => e.toJson()).toList()),
    );

    if (mounted) {
      setState(() {
        _teamMappings = validMappings;
        _isEditingMapping = false;
        _successMessage = 'Lưu mapping thành công';
      });
    }

    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _successMessage = null;
        });
      }
    });

    print('Saved team mappings: ${validMappings.map((e) => "${e.label} -> ${e.line}").toList()}');
  }

  void _navigateToLogin() {
    Navigator.pushReplacementNamed(context, '/login');
  }

  void _startEditing() {
    setState(() {
      _isEditingMapping = true;
    });
  }

  void _cancelEditing() async {
    await _loadTeamMappings();
    if (mounted) {
      setState(() {
        _isEditingMapping = false;
      });
    }
  }

  void _addMappingRow() {
    setState(() {
      _teamMappings.add(
        TeamMapping(label: '', line: _getNextAvailableLine()),
      );
      _isEditingMapping = true;
    });
  }

  int _getNextAvailableLine() {
    final used = _teamMappings.map((e) => e.line).toSet();
    for (int i = 1; i <= 50; i++) {
      if (!used.contains(i)) return i;
    }
    return 1;
  }

  void _removeMappingRow(int index) {
    setState(() {
      _teamMappings.removeAt(index);
    });
  }

  void _updateMappingLabel(int index, String value) {
    setState(() {
      _teamMappings[index] = _teamMappings[index].copyWith(label: value);
    });
  }

  void _updateMappingLine(int index, int value) {
    setState(() {
      _teamMappings[index] = _teamMappings[index].copyWith(line: value);
    });
  }

  Widget _buildInfoRow(IconData icon, String label, String value) {
    return Row(
      children: [
        Icon(icon, color: Colors.blue[800], size: 24),
        const SizedBox(width: 12),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: const TextStyle(
                fontSize: 14,
                color: Colors.grey,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              value,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: Colors.black87,
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildMappingRow(int index) {
    final item = _teamMappings[index];
    final textController = TextEditingController(text: item.label)
      ..selection = TextSelection.fromPosition(
        TextPosition(offset: item.label.length),
      );

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 5,
            child: TextFormField(
              controller: textController,
              enabled: _isEditingMapping,
              decoration: InputDecoration(
                labelText: 'Tên hiển thị',
                hintText: 'Ví dụ: 30, 28-2, Tổ ĐH 1',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                filled: true,
                fillColor: _isEditingMapping ? Colors.white : Colors.grey[100],
              ),
              onChanged: (value) => _updateMappingLabel(index, value),
            ),
          ),
          const SizedBox(width: 10),
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Icon(
              Icons.arrow_forward,
              color: Colors.blue[800],
              size: 28,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            flex: 3,
            child: DropdownButtonFormField<int>(
              value: item.line >= 1 && item.line <= 50 ? item.line : null,
              decoration: InputDecoration(
                labelText: 'Line',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                filled: true,
                fillColor: _isEditingMapping ? Colors.white : Colors.grey[100],
              ),
              items: List.generate(50, (i) => i + 1)
                  .map(
                    (line) => DropdownMenuItem<int>(
                      value: line,
                      child: Text('$line'),
                    ),
                  )
                  .toList(),
              onChanged: _isEditingMapping
                  ? (value) {
                      if (value != null) {
                        _updateMappingLine(index, value);
                      }
                    }
                  : null,
            ),
          ),
          const SizedBox(width: 6),
          if (_isEditingMapping)
            IconButton(
              onPressed: () => _removeMappingRow(index),
              icon: const Icon(Icons.delete, color: Colors.red),
            ),
        ],
      ),
    );
  }

  Widget _buildMappingPreview() {
    if (_teamMappings.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Text(
          'Chưa có tổ nào',
          style: TextStyle(fontSize: 15, color: Colors.grey),
        ),
      );
    }

    return Column(
      children: _teamMappings.map((item) {
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Colors.grey.shade300),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  item.label,
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              //Icon(Icons.arrow_forward, color: Colors.blue[700]),
              const SizedBox(width: 8),
              /*Text(
                'line${item.line}',
                style: TextStyle(
                  fontSize: 15,
                  color: Colors.green[700],
                  fontWeight: FontWeight.bold,
                ),
              ),*/
            ],
          ),
        );
      }).toList(),
    );
  }

  Future<void> _saveGatewayKey() async {
    await ApiService.setGatewayKey(_gatewayKeyCtrl.text.trim());
    if (mounted) setState(() => _isEditingGatewayKey = false);
  }

  @override
  void dispose() {
    _serverUrlCtrl.dispose();
    _gatewayKeyCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.grey[100],
      appBar: AppBar(
        backgroundColor: Colors.blue[800],
        title: const Text(
          'CÀI ĐẶT',
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
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: !_isUserInfoLoaded
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Thông tin tài khoản',
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                        color: Colors.black87,
                      ),
                    ),
                    const SizedBox(height: 20),
                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: Padding(
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _buildInfoRow(Icons.person, 'Họ tên', _name),
                            const Divider(height: 20),
                            _buildInfoRow(Icons.group, 'Phòng ban', _tenPhongBan),
                            const Divider(height: 20),
                            _buildInfoRow(Icons.factory, 'Chi nhánh', _maChiNhanh),
                            const Divider(height: 20),
                            _buildInfoRow(Icons.location_city, 'Site', _siteId),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    // ── Server URL section ─────────────────────────────────
                    const Text(
                      'Kết nối máy chủ',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.black87),
                    ),
                    const SizedBox(height: 12),
                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Locked view
                            if (!_isEditingServerUrl) ...[
                              Row(
                                children: [
                                  const Icon(Icons.dns_outlined, color: Colors.blueGrey, size: 20),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        const Text('URL máy chủ AGVmqtt',
                                            style: TextStyle(fontSize: 12, color: Colors.grey)),
                                        const SizedBox(height: 2),
                                        Text(
                                          _serverUrlCtrl.text.isNotEmpty
                                              ? _serverUrlCtrl.text
                                              : '(chưa cấu hình)',
                                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const Icon(Icons.lock_outline, size: 16, color: Colors.grey),
                                ],
                              ),
                              const SizedBox(height: 12),
                              SizedBox(
                                width: double.infinity,
                                child: OutlinedButton.icon(
                                  icon: const Icon(Icons.edit, size: 16),
                                  label: const Text('Sửa địa chỉ'),
                                  onPressed: _authenticateAndEditServerUrl,
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: Colors.blue[800],
                                    side: BorderSide(color: Colors.blue[300]!),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                  ),
                                ),
                              ),
                            ],

                            // Unlocked edit view
                            if (_isEditingServerUrl) ...[
                              Row(
                                children: [
                                  const Icon(Icons.lock_open, size: 16, color: Colors.orange),
                                  const SizedBox(width: 6),
                                  Text('Chế độ chỉnh sửa',
                                      style: TextStyle(fontSize: 12, color: Colors.orange[700], fontWeight: FontWeight.w600)),
                                ],
                              ),
                              const SizedBox(height: 10),
                              TextFormField(
                                controller: _serverUrlCtrl,
                                autofocus: true,
                                decoration: InputDecoration(
                                  labelText: 'URL máy chủ AGVmqtt',
                                  hintText: 'http://192.168.0.86:8000',
                                  prefixIcon: const Icon(Icons.dns_outlined),
                                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                                  filled: true,
                                  fillColor: Colors.white,
                                ),
                                keyboardType: TextInputType.url,
                              ),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: () => setState(() {
                                        _isEditingServerUrl = false;
                                        _serverTestResult = null;
                                      }),
                                      child: const Text('Hủy'),
                                    ),
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: ElevatedButton.icon(
                                      icon: _isTestingServer
                                          ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                                          : const Icon(Icons.wifi_tethering, size: 18),
                                      label: Text(_isTestingServer ? 'Đang kiểm tra…' : 'Lưu & Kiểm tra'),
                                      onPressed: _isTestingServer ? null : _saveServerUrl,
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.blue[800],
                                        foregroundColor: Colors.white,
                                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],

                            // Test result (shown in both states)
                            if (_serverTestResult != null) ...[
                              const SizedBox(height: 10),
                              Row(
                                children: [
                                  Icon(
                                    _serverTestResult!.contains('thành công') ? Icons.check_circle : Icons.error_outline,
                                    color: _serverTestResult!.contains('thành công') ? Colors.green : Colors.red,
                                    size: 16,
                                  ),
                                  const SizedBox(width: 6),
                                  Expanded(
                                    child: Text(
                                      _serverTestResult!,
                                      style: TextStyle(
                                        color: _serverTestResult!.contains('thành công') ? Colors.green[700] : Colors.red[700],
                                        fontSize: 13,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),

                    // ── Gateway Key section ────────────────────────────────
                    const Text(
                      'Gateway Key',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.black87),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Bỏ trống nếu kết nối trực tiếp nội bộ (không qua cloud)',
                      style: TextStyle(fontSize: 13, color: Colors.grey[600]),
                    ),
                    const SizedBox(height: 12),
                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (!_isEditingGatewayKey) ...[
                              Row(
                                children: [
                                  const Icon(Icons.vpn_key_outlined, color: Colors.blueGrey, size: 20),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        const Text('Key nhà máy',
                                            style: TextStyle(fontSize: 12, color: Colors.grey)),
                                        const SizedBox(height: 2),
                                        Text(
                                          _gatewayKeyCtrl.text.isNotEmpty
                                              ? _gatewayKeyCtrl.text
                                              : '(chưa cấu hình — kết nối nội bộ)',
                                          style: TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.w600,
                                            color: _gatewayKeyCtrl.text.isNotEmpty
                                                ? Colors.black87
                                                : Colors.grey,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const Icon(Icons.lock_outline, size: 16, color: Colors.grey),
                                ],
                              ),
                              const SizedBox(height: 12),
                              SizedBox(
                                width: double.infinity,
                                child: OutlinedButton.icon(
                                  icon: const Icon(Icons.edit, size: 16),
                                  label: const Text('Sửa Gateway Key'),
                                  onPressed: () async {
                                    final ok = await _showPasswordDialog();
                                    if (ok && mounted) setState(() => _isEditingGatewayKey = true);
                                  },
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: Colors.blue[800],
                                    side: BorderSide(color: Colors.blue[300]!),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                  ),
                                ),
                              ),
                            ],
                            if (_isEditingGatewayKey) ...[
                              Row(
                                children: [
                                  const Icon(Icons.lock_open, size: 16, color: Colors.orange),
                                  const SizedBox(width: 6),
                                  Text('Chế độ chỉnh sửa',
                                      style: TextStyle(fontSize: 12, color: Colors.orange[700], fontWeight: FontWeight.w600)),
                                ],
                              ),
                              const SizedBox(height: 10),
                              TextFormField(
                                controller: _gatewayKeyCtrl,
                                autofocus: true,
                                decoration: InputDecoration(
                                  labelText: 'Gateway Key',
                                  hintText: 'KEY_TNG_VietDuc',
                                  prefixIcon: const Icon(Icons.vpn_key_outlined),
                                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                                  filled: true,
                                  fillColor: Colors.white,
                                ),
                              ),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: () => setState(() => _isEditingGatewayKey = false),
                                      child: const Text('Hủy'),
                                    ),
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: ElevatedButton.icon(
                                      icon: const Icon(Icons.save, size: 18),
                                      label: const Text('Lưu'),
                                      onPressed: _saveGatewayKey,
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.blue[800],
                                        foregroundColor: Colors.white,
                                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),

                    // ── Factory (map) selection ────────────────────────────
                    const Text(
                      'Nhà máy',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.black87),
                    ),
                    const SizedBox(height: 12),
                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        child: Row(
                          children: [
                            const Icon(Icons.factory_outlined, color: Colors.blueGrey, size: 20),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _isLoadingMaps
                                  ? const Row(children: [
                                      SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                                      SizedBox(width: 10),
                                      Text('Đang tải...', style: TextStyle(color: Colors.grey)),
                                    ])
                                  : _mapsLoadError != null
                                      ? Text(_mapsLoadError!, style: TextStyle(color: Colors.red[400], fontSize: 13))
                                      : DropdownButtonHideUnderline(
                                          child: DropdownButton<String>(
                                            isExpanded: true,
                                            hint: const Text('Chọn nhà máy...'),
                                            value: _selectedMapId,
                                            items: _maps.map((m) {
                                              final id = m['id']?.toString() ?? m['map_id']?.toString() ?? '';
                                              final name = m['name']?.toString() ?? 'Map $id';
                                              return DropdownMenuItem(value: id, child: Text(name));
                                            }).toList(),
                                            onChanged: (v) { if (v != null) _selectMap(v); },
                                          ),
                                        ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.refresh, size: 18),
                              tooltip: 'Tải lại',
                              onPressed: _isLoadingMaps ? null : _loadMaps,
                              color: Colors.blue[700],
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),

                    // ─────────────────────────────────────────────────────────
                    const Text(
                      //'Mapping tổ → line AGV',
                      'Chọn tổ',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: Colors.black87,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Chọn tổ phụ trách',
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.grey[700],
                      ),
                    ),
                    const SizedBox(height: 16),
                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (_successMessage != null)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 12),
                                child: Row(
                                  children: [
                                    const Icon(Icons.check_circle, color: Colors.green),
                                    const SizedBox(width: 8),
                                    Text(
                                      _successMessage!,
                                      style: const TextStyle(
                                        color: Colors.green,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            if (_isEditingMapping) ...[
                              ...List.generate(_teamMappings.length, (index) => _buildMappingRow(index)),
                              const SizedBox(height: 10),
                              Row(
                                children: [
                                  Expanded(
                                    child: ElevatedButton.icon(
                                      onPressed: _addMappingRow,
                                      icon: const Icon(Icons.add),
                                      label: const Text('Thêm dòng'),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.orange,
                                        foregroundColor: Colors.white,
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: _cancelEditing,
                                      child: const Text('Hủy'),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: ElevatedButton(
                                      onPressed: _saveTeamMappings,
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.blue[800],
                                        foregroundColor: Colors.white,
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                      ),
                                      child: const Text('Lưu'),
                                    ),
                                  ),
                                ],
                              ),
                            ] else ...[
                              _buildMappingPreview(),
                              const SizedBox(height: 12),
                              Row(
                                children: [
                                  Expanded(
                                    child: ElevatedButton.icon(
                                      onPressed: _authenticateAndStartEditing,
                                      icon: const Icon(Icons.edit),
                                      label: const Text('Sửa'),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.blue[800],
                                        foregroundColor: Colors.white,
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: ElevatedButton.icon(
                                      onPressed: _authenticateAndAddMapping,
                                      icon: const Icon(Icons.add),
                                      label: const Text('Thêm'),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.orange,
                                        foregroundColor: Colors.white,
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
    );
  }
}