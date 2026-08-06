import '../models/portfolio_history.dart';
import '../models/portfolio_summary.dart';
import '../network/api_client.dart';

/// Thin service layer wrapping [ApiClient] with in-memory caching awareness.
///
/// The Dio cache interceptor handles disk-level caching; this layer provides
/// in-memory convenience and a single place to add business logic around
/// portfolio data.
class PortfolioService {
  PortfolioService(this._api);

  final ApiClient _api;

  PortfolioSummary? _cachedSummary;
  DateTime? _summaryCachedAt;

  /// How long the in-memory summary stays fresh.
  static const _memCacheDuration = Duration(minutes: 5);

  /// Get the portfolio summary, optionally forcing a refresh.
  Future<PortfolioSummary> getSummary({bool refresh = false}) async {
    if (!refresh && _cachedSummary != null && _summaryCachedAt != null) {
      final age = DateTime.now().difference(_summaryCachedAt!);
      if (age < _memCacheDuration) {
        return _cachedSummary!;
      }
    }

    final summary = await _api.getPortfolioSummary(refresh: refresh);
    _cachedSummary = summary;
    _summaryCachedAt = DateTime.now();
    return summary;
  }

  /// Get portfolio history for a given range.
  Future<PortfolioHistory> getHistory({required String range}) {
    return _api.getPortfolioHistory(range: range);
  }

  /// Clear the in-memory cache.
  void clearCache() {
    _cachedSummary = null;
    _summaryCachedAt = null;
  }
}
