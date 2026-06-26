class TeamMapping {
  final String label;
  final int line;

  TeamMapping({
    required this.label,
    required this.line,
  });

  Map<String, dynamic> toJson() => {
        'label': label,
        'line': line,
      };

  factory TeamMapping.fromJson(Map<String, dynamic> json) {
    return TeamMapping(
      label: json['label']?.toString() ?? '',
      line: int.tryParse(json['line'].toString()) ?? 0,
    );
  }

  TeamMapping copyWith({
    String? label,
    int? line,
  }) {
    return TeamMapping(
      label: label ?? this.label,
      line: line ?? this.line,
    );
  }
}