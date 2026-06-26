import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';

class AGVActivityStatsScreen extends StatefulWidget {
  const AGVActivityStatsScreen({super.key});

  @override
  _AGVActivityStatsScreenState createState() => _AGVActivityStatsScreenState();
}

class AGVTime {
  final String agvName;
  final String totalTime;
  final int commandCount;

  AGVTime({required this.agvName, required this.totalTime, required this.commandCount});

  factory AGVTime.fromJson(Map<String, dynamic> json) {
    return AGVTime(
      agvName: json['agvName']?.toString() ?? 'Unknown',
      totalTime: json['totalTime']?.toString() ?? '00:00:00',
      commandCount: json['commandCount'] as int? ?? 0,
    );
  }

  double getTotalHours() {
    if (totalTime == "00:00:00") return 0.0;
    try {
      final parts = totalTime.split(':');
      final hours = int.parse(parts[0]);
      final minutes = int.parse(parts[1]);
      final seconds = int.parse(parts[2]);
      final result = hours + (minutes / 60.0) + (seconds / 3600.0);
      return result.isFinite ? result : 0.0;
    } catch (e) {
      print('Lỗi parse TotalTime: $totalTime, $e');
      return 0.0;
    }
  }
}

class _AGVActivityStatsScreenState extends State<AGVActivityStatsScreen> {
  List<AGVTime> _agvData = [];
  bool _isLoading = false;
  String _lastUpdated = '';
  String _selectedPeriod = 'Ngày';
  DateTime? _startDate;
  DateTime? _endDate;
  String _errorMessage = '';
  int _touchedIndex = -1;

  final Map<String, String> _periodToApiValue = {
    'Ngày': 'daily',
    'Tuần': 'weekly',
    'Tháng': 'monthly',
    'Tùy chọn': 'custom',
  };

  Future<void> _fetchAGVTime() async {
    setState(() {
      _isLoading = true;
      _errorMessage = '';
    });

    try {
      final queryParameters = <String, String>{};
      queryParameters['period'] = _periodToApiValue[_selectedPeriod]!;
      if (_selectedPeriod == 'Tùy chọn' && _startDate != null && _endDate != null) {
        queryParameters['startDate'] = DateFormat('yyyy-MM-dd').format(_startDate!);
        queryParameters['endDate'] = DateFormat('yyyy-MM-dd').format(_endDate!);
      }

      final uri = Uri.parse('http://103.101.161.216:7000/api/agv/agv-time').replace(queryParameters: queryParameters);
      final response = await http.get(uri).timeout(const Duration(seconds: 10));

      print('API Response: ${response.body}');
      if (response.statusCode == 200) {
        final jsonData = jsonDecode(response.body);
        if (jsonData['success'] == true) {
          final data = (jsonData['data'] as List<dynamic>?)?.map((item) => AGVTime.fromJson(item)).toList() ?? [];
          print('Parsed AGV Data: ${data.map((e) => {'agvName': e.agvName, 'totalTime': e.totalTime, 'commandCount': e.commandCount}).toList()}');
          setState(() {
            _agvData = data;
            _lastUpdated = DateFormat('HH:mm dd/MM/yyyy').format(DateTime.now());
            _isLoading = false;
          });
        } else {
          setState(() {
            _errorMessage = jsonData['message']?.toString() ?? 'Lỗi không xác định';
            _isLoading = false;
          });
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Lỗi: $_errorMessage'), backgroundColor: Colors.red),
          );
        }
      } else {
        setState(() {
          _errorMessage = 'Lỗi khi gọi API: ${response.statusCode}';
          _isLoading = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_errorMessage), backgroundColor: Colors.red),
        );
      }
    } catch (e) {
      print('Lỗi khi gọi API: $e');
      setState(() {
        _errorMessage = 'Lỗi: $e';
        _isLoading = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_errorMessage), backgroundColor: Colors.red),
      );
    }
  }

  Future<void> _selectDate(BuildContext context, bool isStartDate) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime(2030),
    );
    if (picked != null) {
      setState(() {
        if (isStartDate) {
          _startDate = picked;
        } else {
          _endDate = picked;
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // Danh sách màu cho các AGV
    final List<Color> colors = [
      Colors.blue[800]!,
      Colors.green[800]!,
      Colors.red[800]!,
      Colors.purple[800]!,
      Colors.orange[800]!,
      Colors.teal[800]!,
      Colors.amber[800]!,
    ];
    final List<Color> lightColors = [
      Colors.blue[300]!,
      Colors.green[300]!,
      Colors.red[300]!,
      Colors.purple[300]!,
      Colors.orange[300]!,
      Colors.teal[300]!,
      Colors.amber[300]!,
    ];

    return Scaffold(
      backgroundColor: Colors.grey[100],
      appBar: AppBar(
        backgroundColor: Colors.blue[800],
        leading: IconButton(
          //icon: const Icon(Icons.arrow_back, color: Colors.white),
          icon: const Icon(Icons.home, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Thống Kê Thời Gian Hoạt Động AGV',
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
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: _fetchAGVTime,
            tooltip: 'Làm mới dữ liệu',
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Cập nhật: $_lastUpdated',
                          style: const TextStyle(
                            fontSize: 14,
                            color: Colors.grey,
                            fontStyle: FontStyle.italic,
                          ),
                        ),
                        Container(
                          width: 150,
                          child: Card(
                            elevation: 2,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 4.0),
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                  colors: [Colors.white, Colors.grey[100]!],
                                ),
                                borderRadius: BorderRadius.circular(8.0),
                              ),
                              child: DropdownButton<String>(
                                value: _selectedPeriod,
                                items: ['Ngày', 'Tuần', 'Tháng', 'Tùy chọn']
                                    .map((period) => DropdownMenuItem(
                                          value: period,
                                          child: Text(
                                            period,
                                            style: TextStyle(fontSize: 14),
                                          ),
                                        ))
                                    .toList(),
                                onChanged: (value) {
                                  setState(() {
                                    _selectedPeriod = value!;
                                    _startDate = null;
                                    _endDate = null;
                                  });
                                  if (_selectedPeriod != 'Tùy chọn') {
                                    _fetchAGVTime();
                                  }
                                },
                                underline: SizedBox(),
                                isExpanded: false,
                                iconSize: 20,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    if (_selectedPeriod == 'Tùy chọn') ...[
                      Card(
                        elevation: 4,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        child: Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [Colors.white, Colors.grey[100]!],
                            ),
                            borderRadius: BorderRadius.circular(12.0),
                          ),
                          padding: const EdgeInsets.all(16.0),
                          child: Column(
                            children: [
                              Row(
                                children: [
                                  Expanded(
                                    child: TextButton(
                                      onPressed: () => _selectDate(context, true),
                                      child: Text(
                                        _startDate == null
                                            ? 'Chọn ngày bắt đầu'
                                            : DateFormat('dd/MM/yyyy').format(_startDate!),
                                        style: TextStyle(color: Colors.black87),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: TextButton(
                                      onPressed: () => _selectDate(context, false),
                                      child: Text(
                                        _endDate == null
                                            ? 'Chọn ngày kết thúc'
                                            : DateFormat('dd/MM/yyyy').format(_endDate!),
                                        style: TextStyle(color: Colors.black87),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              ElevatedButton(
                                onPressed: (_startDate != null && _endDate != null) ? _fetchAGVTime : null,
                                child: const Text('Lấy dữ liệu'),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.blue[800],
                                  foregroundColor: Colors.white,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],
                    if (_errorMessage.isNotEmpty)
                      Text(
                        _errorMessage,
                        style: const TextStyle(color: Colors.red, fontSize: 14),
                      ),
                    // Card 1: Biểu đồ cột (BarChart)
                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                            colors: [Colors.white, Colors.grey[100]!],
                          ),
                          borderRadius: BorderRadius.circular(12.0),
                        ),
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Thời gian hoạt động AGV',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                color: Colors.black87,
                              ),
                            ),
                            const SizedBox(height: 16),
                            SizedBox(
                              height: 400,
                              child: _agvData.isEmpty
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
                                            'Không có dữ liệu AGV',
                                            style: TextStyle(
                                              fontSize: 16,
                                              color: Colors.grey[600],
                                            ),
                                          ),
                                        ],
                                      ),
                                    )
                                  : Row(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        // Trục Y cố định
                                        SizedBox(
                                          width: 40,
                                          height: 360, // 400 - reservedSize của bottomTitles
                                          child: Column(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: List.generate(
                                              4, // Số nhãn: 0h, 15h, 30h, 45h
                                              (index) {
                                                final maxY = _agvData.isNotEmpty
                                                    ? (_agvData
                                                                .map((e) => e.getTotalHours())
                                                                .reduce((a, b) => a > b ? a : b) *
                                                            1.3)
                                                        .ceil()
                                                        .toDouble()
                                                    : 10.0;
                                                final value = (maxY / 3 * (3 - index)).toInt();
                                                return Text(
                                                  '${value}h',
                                                  style: TextStyle(fontSize: 12, color: Colors.black87),
                                                  textAlign: TextAlign.right,
                                                );
                                              },
                                            ),
                                          ),
                                        ),
                                        // Lưới biểu đồ và trục X cuộn ngang
                                        Expanded(
                                          child: SingleChildScrollView(
                                            scrollDirection: Axis.horizontal,
                                            child: ConstrainedBox(
                                              constraints: BoxConstraints(
                                                minWidth: MediaQuery.of(context).size.width - 72, // Card width - padding - trục Y
                                                maxWidth: MediaQuery.of(context).size.width - 72,
                                              ),
                                              child: BarChart(
                                                BarChartData(
                                                  alignment: BarChartAlignment.spaceAround,
                                                  maxY: _agvData.isNotEmpty
                                                      ? (_agvData
                                                                  .map((e) => e.getTotalHours())
                                                                  .reduce((a, b) => a > b ? a : b) *
                                                              1.3)
                                                          .ceil()
                                                          .toDouble()
                                                      : 10.0,
                                                  minY: 0,
                                                  barGroups: _agvData.asMap().entries.map((entry) {
                                                    final index = entry.key;
                                                    final agv = entry.value;
                                                    return BarChartGroupData(
                                                      x: index,
                                                      barRods: [
                                                        BarChartRodData(
                                                          toY: agv.getTotalHours(),
                                                          gradient: LinearGradient(
                                                            colors: [
                                                              index == 0
                                                                  ? Colors.blue[800]!
                                                                  : index == 1
                                                                      ? Colors.green[800]!
                                                                      : index == 2
                                                                          ? Colors.red[800]!
                                                                          : colors[index % colors.length],
                                                              index == 0
                                                                  ? Colors.blue[300]!
                                                                  : index == 1
                                                                      ? Colors.green[300]!
                                                                      : index == 2
                                                                          ? Colors.red[300]!
                                                                          : lightColors[index % colors.length],
                                                            ],
                                                            begin: Alignment.bottomCenter,
                                                            end: Alignment.topCenter,
                                                          ),
                                                          width: 25,
                                                          borderRadius: BorderRadius.circular(8),
                                                          backDrawRodData: BackgroundBarChartRodData(
                                                            show: true,
                                                            toY: 0,
                                                            color: Colors.grey[200],
                                                          ),
                                                          rodStackItems: [
                                                            BarChartRodStackItem(
                                                              0,
                                                              agv.getTotalHours(),
                                                              index == 0
                                                                  ? Colors.blue[800]!
                                                                  : index == 1
                                                                      ? Colors.green[800]!
                                                                      : index == 2
                                                                          ? Colors.red[800]!
                                                                          : colors[index % colors.length],
                                                              BorderSide(color: Colors.white, width: 1),
                                                            ),
                                                          ],
                                                        ),
                                                      ],
                                                      showingTooltipIndicators: [0],
                                                    );
                                                  }).toList(),
                                                  titlesData: FlTitlesData(
                                                    leftTitles: AxisTitles(
                                                      sideTitles: SideTitles(showTitles: false), // Tắt trục Y trong BarChart
                                                    ),
                                                    bottomTitles: AxisTitles(
                                                      sideTitles: SideTitles(
                                                        showTitles: true,
                                                        reservedSize: 40,
                                                        getTitlesWidget: (value, meta) {
                                                          final index = value.toInt();
                                                          if (index >= 0 && index < _agvData.length) {
                                                            return Padding(
                                                              padding: const EdgeInsets.only(top: 12.0),
                                                              child: Text(
                                                                _agvData[index].agvName,
                                                                style: TextStyle(
                                                                  fontSize: 14,
                                                                  fontWeight: FontWeight.bold,
                                                                ),
                                                              ),
                                                            );
                                                          }
                                                          return Text('');
                                                        },
                                                      ),
                                                    ),
                                                    topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                                                    rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                                                  ),
                                                  barTouchData: BarTouchData(
                                                    enabled: true,
                                                    touchTooltipData: BarTouchTooltipData(
                                                      getTooltipColor: (group) => Colors.black87,
                                                      tooltipPadding: const EdgeInsets.all(8),
                                                      getTooltipItem: (group, groupIndex, rod, rodIndex) {
                                                        final index = group.x;
                                                        if (index >= 0 && index < _agvData.length) {
                                                          final agv = _agvData[index];
                                                          return BarTooltipItem(
                                                            '${agv.agvName}\n${agv.totalTime}',
                                                            TextStyle(
                                                              color: Colors.white,
                                                              fontWeight: FontWeight.bold,
                                                              fontSize: 10,
                                                            ),
                                                          );
                                                        }
                                                        return BarTooltipItem('', TextStyle(color: Colors.white));
                                                      },
                                                    ),
                                                  ),
                                                  borderData: FlBorderData(
                                                    show: true,
                                                    border: Border.all(color: Colors.grey[300]!, width: 1),
                                                  ),
                                                  gridData: FlGridData(
                                                    show: true,
                                                    drawHorizontalLine: true,
                                                    horizontalInterval: 15,
                                                    getDrawingHorizontalLine: (value) => FlLine(
                                                      color: Colors.grey[300],
                                                      strokeWidth: 1,
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    // Card 2: Biểu đồ tròn (PieChart)
                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                            colors: [Colors.white, Colors.grey[100]!],
                          ),
                          borderRadius: BorderRadius.circular(12.0),
                        ),
                        padding: const EdgeInsets.all(16.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Tần suất hoạt động',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                color: Colors.black87,
                              ),
                            ),
                            const SizedBox(height: 16),
                            SizedBox(
                              height: 200,
                              child: _agvData.isEmpty
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
                                            'Không có dữ liệu số lệnh',
                                            style: TextStyle(
                                              fontSize: 16,
                                              color: Colors.grey[600],
                                            ),
                                          ),
                                        ],
                                      ),
                                    )
                                  : Stack(
                                      alignment: Alignment.center,
                                      children: [
                                        PieChart(
                                          PieChartData(
                                            pieTouchData: PieTouchData(
                                              touchCallback: (FlTouchEvent event, pieTouchResponse) {
                                                setState(() {
                                                  if (!event.isInterestedForInteractions ||
                                                      pieTouchResponse == null ||
                                                      pieTouchResponse.touchedSection == null) {
                                                    _touchedIndex = -1;
                                                    return;
                                                  }
                                                  _touchedIndex = pieTouchResponse.touchedSection!.touchedSectionIndex;
                                                });
                                              },
                                            ),
                                            borderData: FlBorderData(show: false),
                                            sectionsSpace: 2,
                                            centerSpaceRadius: 40,
                                            sections: _agvData.asMap().entries.map((entry) {
                                              final index = entry.key;
                                              final agv = entry.value;
                                              final totalCommands = _agvData.fold<int>(0, (sum, item) => sum + item.commandCount);
                                              final percentage = totalCommands > 0 ? (agv.commandCount / totalCommands) * 100 : 0.0;
                                              final isTouched = index == _touchedIndex;

                                              return PieChartSectionData(
                                                color: index == 0
                                                    ? Colors.blue[800]!
                                                    : index == 1
                                                        ? Colors.green[800]!
                                                        : index == 2
                                                            ? Colors.red[800]!
                                                            : colors[index % colors.length],
                                                value: agv.commandCount.toDouble(),
                                                title: '${percentage.toStringAsFixed(2)}%',
                                                showTitle: true,
                                                titleStyle: const TextStyle(
                                                  fontSize: 10,
                                                  fontWeight: FontWeight.bold,
                                                  color: Colors.white,
                                                ),
                                                radius: isTouched ? 70 : 60,
                                                titlePositionPercentageOffset: 0.55,
                                                badgeWidget: isTouched
                                                    ? Container(
                                                        padding: const EdgeInsets.all(8),
                                                        color: Colors.black87,
                                                        child: Text(
                                                          '${agv.agvName}\n${percentage.toStringAsFixed(2)}%\n${agv.commandCount} commands',
                                                          style: const TextStyle(
                                                            fontSize: 10,
                                                            fontWeight: FontWeight.bold,
                                                            color: Colors.white,
                                                          ),
                                                          textAlign: TextAlign.center,
                                                        ),
                                                      )
                                                    : null,
                                              );
                                            }).toList(),
                                          ),
                                        ),
                                        Text(
                                          '${_agvData.fold<int>(0, (sum, item) => sum + item.commandCount)} Chuyến',
                                          style: const TextStyle(
                                            fontSize: 11,
                                            fontWeight: FontWeight.bold,
                                            color: Colors.black87,
                                          ),
                                        ),
                                      ],
                                    ),
                            ),
                            const SizedBox(height: 16),
                            Wrap(
                              spacing: 16,
                              runSpacing: 8,
                              children: _agvData.asMap().entries.map((entry) {
                                final index = entry.key;
                                final agv = entry.value;
                                return Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Container(
                                      width: 16,
                                      height: 16,
                                      color: index == 0
                                          ? Colors.blue[800]!
                                          : index == 1
                                              ? Colors.green[800]!
                                              : index == 2
                                                  ? Colors.red[800]!
                                                  : colors[index % colors.length],
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      '${agv.agvName}: ${agv.commandCount} Chuyến',
                                      style: const TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.bold,
                                        color: Colors.black,
                                      ),
                                    ),
                                  ],
                                );
                              }).toList(),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}