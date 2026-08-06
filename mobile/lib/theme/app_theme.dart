import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Identifies a named theme variant.
enum AppThemeName {
  light('Light'),
  dark('Dark'),
  oceanDepths('Ocean Depths'),
  sunsetHorizon('Sunset Horizon'),
  cypherpunk('Cypherpunk');

  const AppThemeName(this.displayName);
  final String displayName;
}

class AppTheme {
  static ThemeData light() {
    const seed = Color(0xFF0C9A8D);
    final colorScheme = ColorScheme.fromSeed(
      seedColor: seed,
      brightness: Brightness.light,
      surface: const Color(0xFFF7F5F1),
    );

    return _buildTheme(colorScheme, Brightness.light, fillColor: Colors.white);
  }

  static ThemeData dark() {
    const primary = Color(0xFF22D486);
    const background = Color(0xFF0B0B0B);
    const surface = Color(0xFF151515);

    const colorScheme = ColorScheme(
      brightness: Brightness.dark,
      primary: primary,
      onPrimary: Colors.black,
      secondary: Color(0xFF4BE3A1),
      onSecondary: Colors.black,
      error: Color(0xFFFF6B6B),
      onError: Colors.black,
      surface: surface,
      onSurface: Color(0xFFE9E9E9),
      surfaceContainerHighest: Color(0xFF1F1F1F),
      onSurfaceVariant: Color(0xFFBDBDBD),
      outline: Color(0xFF2A2A2A),
      outlineVariant: Color(0xFF333333),
      tertiary: Color(0xFF6AE9C0),
      onTertiary: Colors.black,
      scrim: Colors.black,
    );

    return _buildTheme(colorScheme, Brightness.dark,
        scaffoldBg: background, fillColor: const Color(0xFF1A1A1A));
  }

  static ThemeData oceanDepths() {
    const primary = Color(0xFF00B4D8);
    const background = Color(0xFF0A1929);
    const surface = Color(0xFF0D2137);

    const colorScheme = ColorScheme(
      brightness: Brightness.dark,
      primary: primary,
      onPrimary: Colors.black,
      secondary: Color(0xFF48CAE4),
      onSecondary: Colors.black,
      error: Color(0xFFFF6B6B),
      onError: Colors.black,
      surface: surface,
      onSurface: Color(0xFFCAF0F8),
      surfaceContainerHighest: Color(0xFF112B44),
      onSurfaceVariant: Color(0xFF90E0EF),
      outline: Color(0xFF1B3A5C),
      outlineVariant: Color(0xFF1B3A5C),
      tertiary: Color(0xFF0096C7),
      onTertiary: Colors.white,
      scrim: Colors.black,
    );

    return _buildTheme(colorScheme, Brightness.dark,
        scaffoldBg: background, fillColor: const Color(0xFF0F2A3F));
  }

  static ThemeData sunsetHorizon() {
    const primary = Color(0xFFFF6B35);
    const background = Color(0xFF1A0A2E);
    const surface = Color(0xFF241440);

    const colorScheme = ColorScheme(
      brightness: Brightness.dark,
      primary: primary,
      onPrimary: Colors.white,
      secondary: Color(0xFFFF9E6D),
      onSecondary: Colors.black,
      error: Color(0xFFFF6B6B),
      onError: Colors.black,
      surface: surface,
      onSurface: Color(0xFFEDE0D4),
      surfaceContainerHighest: Color(0xFF2E1A50),
      onSurfaceVariant: Color(0xFFD4A373),
      outline: Color(0xFF3D2466),
      outlineVariant: Color(0xFF3D2466),
      tertiary: Color(0xFFFFB347),
      onTertiary: Colors.black,
      scrim: Colors.black,
    );

    return _buildTheme(colorScheme, Brightness.dark,
        scaffoldBg: background, fillColor: const Color(0xFF1F1038));
  }

  static ThemeData cypherpunk() {
    const primary = Color(0xFF00D4FF);
    const background = Color(0xFF030308);
    const surface = Color(0xFF0C0C24);

    const colorScheme = ColorScheme(
      brightness: Brightness.dark,
      primary: primary,
      onPrimary: Colors.black,
      secondary: Color(0xFFD946EF),
      onSecondary: Colors.black,
      error: Color(0xFFD946EF),
      onError: Colors.black,
      surface: surface,
      onSurface: Color(0xFFE0F0FF),
      surfaceContainerHighest: Color(0xFF14143A),
      onSurfaceVariant: Color(0xFF8EC8FF),
      outline: Color(0xFF1A0A3A),
      outlineVariant: Color(0xFF1A0A3A),
      tertiary: Color(0xFF7C3AED),
      onTertiary: Colors.white,
      scrim: Colors.black,
    );

    return _buildTheme(colorScheme, Brightness.dark,
        scaffoldBg: background, fillColor: const Color(0xFF08081A));
  }

  /// Returns the [ThemeData] for the given named theme.
  static ThemeData forName(AppThemeName name) {
    switch (name) {
      case AppThemeName.light:
        return light();
      case AppThemeName.dark:
        return dark();
      case AppThemeName.oceanDepths:
        return oceanDepths();
      case AppThemeName.sunsetHorizon:
        return sunsetHorizon();
      case AppThemeName.cypherpunk:
        return cypherpunk();
    }
  }

  static ThemeData _buildTheme(
    ColorScheme colorScheme,
    Brightness brightness, {
    Color? scaffoldBg,
    Color? fillColor,
  }) {
    final isDark = brightness == Brightness.dark;
    final textTheme = isDark
        ? GoogleFonts.spaceGroteskTextTheme(
            ThemeData(brightness: Brightness.dark).textTheme)
        : GoogleFonts.spaceGroteskTextTheme();

    final borderColor = colorScheme.outlineVariant;

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: scaffoldBg ?? colorScheme.surface,
      textTheme: textTheme,
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: fillColor ?? Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: borderColor),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: borderColor),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: colorScheme.primary, width: 1.5),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}
