enum ConnectionType {
  local,
  cloudflare;

  String get displayName => switch (this) {
        local => 'Local',
        cloudflare => 'Cloudflare Tunnel',
      };
}

class ConnectionProfile {
  ConnectionProfile({
    required this.name,
    required this.baseUrl,
    this.connectionType = ConnectionType.cloudflare,
    this.accessClientId = '',
    this.accessClientSecret = '',
    this.certPins = const [],
  });

  final String name;
  final String baseUrl;
  final ConnectionType connectionType;
  final String accessClientId;
  final String accessClientSecret;
  final List<String> certPins;

  Map<String, dynamic> toJson() => {
        'name': name,
        'baseUrl': baseUrl,
        'connectionType': connectionType.name,
        'accessClientId': accessClientId,
        'accessClientSecret': accessClientSecret,
        'certPins': certPins,
      };

  static ConnectionProfile fromJson(Map<String, dynamic> json) {
    final typeStr = json['connectionType'] as String?;
    final type = ConnectionType.values.where((e) => e.name == typeStr).firstOrNull ??
        ConnectionType.cloudflare;

    return ConnectionProfile(
      name: json['name'] as String? ?? 'Default',
      baseUrl: json['baseUrl'] as String? ?? '',
      connectionType: type,
      accessClientId: json['accessClientId'] as String? ?? '',
      accessClientSecret: json['accessClientSecret'] as String? ?? '',
      certPins: (json['certPins'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}
