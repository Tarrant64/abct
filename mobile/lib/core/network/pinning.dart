import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

String sha256OfPem(String pem) {
  final normalized = pem.replaceAll('\r\n', '\n');
  final bytes = utf8.encode(normalized);
  final hash = sha256.convert(bytes);
  return base64.encode(hash.bytes);
}

HttpClient createPinnedHttpClient(List<String> allowedPins) {
  final context = SecurityContext(withTrustedRoots: false);
  final client = HttpClient(context: context);
  client.badCertificateCallback = (cert, host, port) {
    if (allowedPins.isEmpty) {
      return false;
    }
    final pin = sha256OfPem(cert.pem);
    return allowedPins.contains(pin);
  };
  return client;
}
