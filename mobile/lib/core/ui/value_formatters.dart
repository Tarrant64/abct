class ValueFormatters {
  static String usd(num value, {int decimals = 2}) {
    final sign = value < 0 ? '-' : '';
    final abs = value.abs();
    return '$sign\$${_grouped(abs, decimals: decimals)}';
  }

  static String percent(num value, {int decimals = 1}) {
    return '${value.toStringAsFixed(decimals)}%';
  }

  static String number(num value, {int decimals = 2}) {
    return _grouped(value, decimals: decimals);
  }

  static String tokenAmount(num value) {
    final abs = value.abs();
    int decimals;
    if (abs >= 1000) {
      decimals = 2;
    } else if (abs >= 1) {
      decimals = 4;
    } else if (abs >= 0.001) {
      decimals = 6;
    } else {
      decimals = 8;
    }
    return _grouped(value, decimals: decimals);
  }

  static String compactUsd(num value) {
    final abs = value.abs();
    final sign = value < 0 ? '-' : '';
    if (abs >= 1000000000) {
      return '$sign\$${(abs / 1000000000).toStringAsFixed(2)}B';
    }
    if (abs >= 1000000) {
      return '$sign\$${(abs / 1000000).toStringAsFixed(2)}M';
    }
    if (abs >= 1000) {
      return '$sign\$${(abs / 1000).toStringAsFixed(1)}K';
    }
    return usd(value);
  }

  // Refresh/sync stamp: "MM/DD h:mm AM/PM TZ" in device-local time
  // (e.g. "10/18 4:32 PM CDT"). timeZoneName is the OS-reported
  // abbreviation (CDT/CST/EDT/PST...), matching the web app's format.
  static String timestamp(String? isoText) {
    if (isoText == null || isoText.isEmpty) {
      return 'Unknown';
    }
    final dt = DateTime.tryParse(isoText);
    if (dt == null) {
      return isoText;
    }

    final local = dt.toLocal();
    final mm = local.month.toString().padLeft(2, '0');
    final dd = local.day.toString().padLeft(2, '0');
    final h12 = local.hour % 12 == 0 ? 12 : local.hour % 12;
    final min = local.minute.toString().padLeft(2, '0');
    final amPm = local.hour < 12 ? 'AM' : 'PM';
    final tz = local.timeZoneName.isNotEmpty ? local.timeZoneName : _utcOffset(local);
    return '$mm/$dd $h12:$min $amPm $tz';
  }

  /// Fallback zone label when the OS reports no abbreviation: "UTC-5".
  static String _utcOffset(DateTime local) {
    final offset = local.timeZoneOffset;
    if (offset == Duration.zero) return 'UTC';
    final sign = offset.isNegative ? '-' : '+';
    final hours = offset.inHours.abs();
    final minutes = offset.inMinutes.remainder(60).abs();
    return minutes == 0
        ? 'UTC$sign$hours'
        : 'UTC$sign$hours:${minutes.toString().padLeft(2, '0')}';
  }

  static String titleCase(String value) {
    if (value.isEmpty) return value;
    return value
        .split(RegExp(r'[_\s-]+'))
        .where((part) => part.isNotEmpty)
        .map((part) => '${part[0].toUpperCase()}${part.substring(1).toLowerCase()}')
        .join(' ');
  }

  static String shortenAddress(String value, {int edge = 6}) {
    if (value.length <= edge * 2) return value;
    return '${value.substring(0, edge)}...${value.substring(value.length - edge)}';
  }

  static String _grouped(num value, {int decimals = 2}) {
    final abs = value.abs().toStringAsFixed(decimals);
    final parts = abs.split('.');
    final intPart = parts[0].replaceAllMapped(
      RegExp(r'\B(?=(\d{3})+(?!\d))'),
      (_) => ',',
    );
    final decimalPart = decimals > 0 ? '.${parts[1]}' : '';
    final sign = value < 0 ? '-' : '';
    return '$sign$intPart$decimalPart';
  }
}
