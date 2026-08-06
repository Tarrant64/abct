class JsonUtils {
  static Map<String, dynamic> map(dynamic value) {
    if (value is Map<String, dynamic>) {
      return value;
    }
    if (value is Map) {
      return value.map((key, val) => MapEntry('$key', val));
    }
    return const <String, dynamic>{};
  }

  static List<Map<String, dynamic>> listOfMaps(dynamic value) {
    if (value is! List) {
      return const <Map<String, dynamic>>[];
    }
    return value.map(map).toList();
  }

  static String string(
    Map<String, dynamic> json,
    String key, {
    String fallback = '',
  }) {
    final value = json[key];
    if (value == null) return fallback;
    return '$value';
  }

  static String? optionalString(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value == null) return null;
    final text = '$value'.trim();
    return text.isEmpty ? null : text;
  }

  static double doubleValue(
    Map<String, dynamic> json,
    String key, {
    double fallback = 0,
  }) {
    final value = json[key];
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value) ?? fallback;
    return fallback;
  }

  static int intValue(
    Map<String, dynamic> json,
    String key, {
    int fallback = 0,
  }) {
    final value = json[key];
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value) ?? fallback;
    return fallback;
  }

  static bool boolValue(
    Map<String, dynamic> json,
    String key, {
    bool fallback = false,
  }) {
    final value = json[key];
    if (value is bool) return value;
    if (value is num) return value != 0;
    if (value is String) {
      final lower = value.toLowerCase();
      if (lower == 'true' || lower == '1') return true;
      if (lower == 'false' || lower == '0') return false;
    }
    return fallback;
  }

  static DateTime? dateTime(
    Map<String, dynamic> json,
    String key,
  ) {
    final value = optionalString(json, key);
    if (value == null) return null;
    return DateTime.tryParse(value);
  }

  static List<double> doubleList(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value is! List) return const <double>[];
    return value
        .map((e) => e is num ? e.toDouble() : 0.0)
        .toList()
        .cast<double>();
  }

  static Map<String, double> stringToDoubleMap(dynamic value) {
    final input = map(value);
    final out = <String, double>{};
    for (final entry in input.entries) {
      final val = entry.value;
      if (val is num) {
        out[entry.key] = val.toDouble();
      } else if (val is String) {
        final parsed = double.tryParse(val);
        if (parsed != null) {
          out[entry.key] = parsed;
        }
      }
    }
    return out;
  }
}
