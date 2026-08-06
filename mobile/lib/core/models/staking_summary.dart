import 'json_utils.dart';

class StakingSummary {
  StakingSummary({
    required this.totalStakedUsd,
    required this.totalRewardsUsd,
    required this.positions,
    this.lastUpdated,
  });

  final double totalStakedUsd;
  final double totalRewardsUsd;
  final List<StakingPosition> positions;
  final DateTime? lastUpdated;

  factory StakingSummary.fromJson(Map<String, dynamic> json) {
    final data = JsonUtils.map(json['data']);
    final stakingPositions = _listOfMapsFromAny(
      [json, data],
      ['positions', 'staking_positions', 'items'],
    ).map(StakingPosition.fromJson).toList()
      ..sort(
        (a, b) => (b.delegatedUsd > 0 ? b.delegatedUsd : b.delegatedAmount)
            .compareTo(a.delegatedUsd > 0 ? a.delegatedUsd : a.delegatedAmount),
      );

    final totalStakedUsd = _doubleFromAny(
      [json, data],
      [
        'total_staked_usd',
        'total_delegated_usd',
        'total_stake_usd',
        'staked_usd',
        'total_value_usd',
      ],
    );
    final totalRewardsUsd = _doubleFromAny(
      [json, data],
      [
        'total_rewards_usd',
        'rewards_usd',
        'total_reward_usd',
      ],
    );

    final summedStakedUsd = stakingPositions.fold<double>(
      0,
      (sum, position) => sum + position.delegatedUsd,
    );
    final summedRewardsUsd = stakingPositions.fold<double>(
      0,
      (sum, position) => sum + position.rewardsUsd,
    );

    return StakingSummary(
      totalStakedUsd: totalStakedUsd > 0 ? totalStakedUsd : summedStakedUsd,
      totalRewardsUsd: totalRewardsUsd > 0 ? totalRewardsUsd : summedRewardsUsd,
      positions: stakingPositions,
      lastUpdated: JsonUtils.dateTime(json, 'last_updated') ??
          JsonUtils.dateTime(data, 'last_updated'),
    );
  }
}

class StakingPosition {
  StakingPosition({
    required this.blockchain,
    required this.stakeKey,
    required this.poolId,
    required this.poolName,
    required this.poolTicker,
    required this.stakedSymbol,
    required this.delegatedAmount,
    required this.delegatedUsd,
    required this.rewardsLifetime,
    required this.rewardsUsd,
    required this.apy,
    required this.active,
    required this.logoUrl,
    this.protocol = '',
    this.positionKind = '',
    this.priced = true,
  });

  final String blockchain;
  final String stakeKey;
  final String poolId;
  final String poolName;
  final String poolTicker;
  /// The actual token being staked (e.g. "INDY", "STRIKE", "LQ").
  /// Empty for traditional ADA delegation.
  final String stakedSymbol;
  final double delegatedAmount;
  final double delegatedUsd;
  final double rewardsLifetime;
  final double rewardsUsd;
  final double apy;
  final bool active;
  final String logoUrl;

  /// Protocol identifier from the backend (e.g. "indigo", "strike").
  /// Falls back to the blockchain name for native delegations that carry
  /// no explicit protocol field.
  final String protocol;

  /// Backend position kind (e.g. "delegation", "vault"); may be empty on
  /// older payloads.
  final String positionKind;

  /// False when the backend priced this position via a fallback source
  /// (e.g. Strike vault share-price estimates) rather than a market quote.
  final bool priced;

  /// Native chain delegation (one of possibly many stake-key rows) as
  /// opposed to a DeFi protocol position.
  bool get isNativeDelegation =>
      positionKind.toLowerCase() == 'delegation' ||
      (positionKind.isEmpty && stakedSymbol.isEmpty);

  factory StakingPosition.fromJson(Map<String, dynamic> json) {
    final position = JsonUtils.map(json['position']);
    final metrics = JsonUtils.map(json['metrics']);
    final amounts = JsonUtils.map(json['amounts']);
    final pool = JsonUtils.map(json['pool']);
    final sources = [json, position, metrics, amounts, pool];

    final blockchain = _stringFromAny(
      sources,
      ['blockchain', 'chain', 'network'],
      fallback: 'unknown',
    );

    return StakingPosition(
      blockchain: blockchain,
      stakeKey: _stringFromAny(
        sources,
        ['stake_key', 'stake_address', 'wallet_address'],
      ),
      poolId: _stringFromAny(sources, ['pool_id', 'validator_id', 'id']),
      poolName: _stringFromAny(
        sources,
        ['pool_name', 'name', 'protocol_name', 'protocol'],
        fallback: 'Staking Position',
      ),
      poolTicker: _stringFromAny(
        sources,
        ['pool_ticker', 'ticker', 'symbol'],
      ),
      stakedSymbol: _stringFromAny(
        sources,
        ['staked_symbol', 'staked_token', 'token_symbol'],
      ),
      delegatedAmount: _doubleFromAny(
        sources,
        [
          'delegated_amount',
          'staked_amount',
          'amount_staked',
          'delegated',
          'amount',
          'balance',
        ],
      ),
      delegatedUsd: _doubleFromAny(
        sources,
        [
          'delegated_usd',
          'staked_usd',
          'staked_value_usd',
          'value_usd',
          'usd_value',
          'amount_usd',
        ],
      ),
      rewardsLifetime: _doubleFromAny(
        sources,
        [
          'rewards_lifetime',
          'reward_amount',
          'total_rewards',
          'rewards',
        ],
      ),
      rewardsUsd: _doubleFromAny(
        sources,
        [
          'rewards_usd',
          'reward_usd',
          'total_rewards_usd',
          'rewards_value_usd',
        ],
      ),
      apy: _doubleFromAny(
        sources,
        ['apy', 'apr', 'yield', 'estimated_apy'],
      ),
      active: _boolFromAny(
        sources,
        ['active', 'is_active', 'enabled'],
        fallback: true,
      ),
      logoUrl: _stringFromAny(
        sources,
        ['logo_url', 'icon_url', 'logo'],
      ),
      protocol: _stringFromAny(
        sources,
        ['protocol', 'protocol_id', 'platform'],
        fallback: blockchain,
      ),
      positionKind: _stringFromAny(
        sources,
        ['position_kind', 'kind', 'position_type'],
      ),
      priced: _boolFromAny(sources, ['priced'], fallback: true),
    );
  }
}

double _doubleFromAny(
  List<Map<String, dynamic>> sources,
  List<String> keys, {
  double fallback = 0,
}) {
  for (final source in sources) {
    for (final key in keys) {
      if (!source.containsKey(key)) continue;
      final parsed = _toDouble(source[key]);
      if (parsed != null) return parsed;
    }
  }
  return fallback;
}

String _stringFromAny(
  List<Map<String, dynamic>> sources,
  List<String> keys, {
  String fallback = '',
}) {
  for (final source in sources) {
    for (final key in keys) {
      final raw = source[key];
      if (raw == null) continue;
      final text = '$raw'.trim();
      if (text.isNotEmpty) return text;
    }
  }
  return fallback;
}

bool _boolFromAny(
  List<Map<String, dynamic>> sources,
  List<String> keys, {
  bool fallback = false,
}) {
  for (final source in sources) {
    for (final key in keys) {
      if (!source.containsKey(key)) continue;
      final raw = source[key];
      if (raw is bool) return raw;
      if (raw is num) return raw != 0;
      if (raw is String) {
        final normalized = raw.trim().toLowerCase();
        if (normalized == 'true' || normalized == '1') return true;
        if (normalized == 'false' || normalized == '0') return false;
      }
    }
  }
  return fallback;
}

List<Map<String, dynamic>> _listOfMapsFromAny(
  List<Map<String, dynamic>> sources,
  List<String> keys,
) {
  for (final source in sources) {
    for (final key in keys) {
      if (!source.containsKey(key)) continue;
      final list = JsonUtils.listOfMaps(source[key]);
      if (list.isNotEmpty) return list;
    }
  }
  return const <Map<String, dynamic>>[];
}

double? _toDouble(dynamic value) {
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value.replaceAll(',', ''));
  if (value is Map) {
    final map = JsonUtils.map(value);
    for (final key in const ['usd', 'value', 'amount', 'total']) {
      if (map.containsKey(key)) {
        final nested = _toDouble(map[key]);
        if (nested != null) return nested;
      }
    }
  }
  return null;
}
