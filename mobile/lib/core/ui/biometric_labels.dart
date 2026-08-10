import 'dart:io' show Platform;

/// Platform-appropriate name for the device's biometric unlock.
///
/// Apple hardware has a single branded mechanism per platform, so we can name
/// it exactly. Android spans fingerprint, face and iris across OEMs with no
/// user-facing brand to borrow, so it gets the generic term the system
/// settings themselves use.
String get biometricLabel {
  if (Platform.isMacOS) return 'Touch ID';
  if (Platform.isAndroid) return 'Biometric unlock';
  return 'Face ID';
}

/// [biometricLabel] for use inside a sentence. Apple's names are proper nouns
/// and stay capitalized; the Android term is not, and reads as a typo mid-line.
String get biometricLabelInline =>
    Platform.isAndroid ? 'biometric unlock' : biometricLabel;

/// Longer form for switch tiles that name both Apple mechanisms.
String get biometricSettingLabel =>
    Platform.isAndroid ? 'Biometric unlock' : 'Face ID / Touch ID';
