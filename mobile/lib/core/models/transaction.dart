import 'json_utils.dart';

class TransactionHistory {
  TransactionHistory({
    required this.transactions,
    required this.totalCount,
    required this.days,
  });

  final List<Transaction> transactions;
  final int totalCount;
  final int days;

  factory TransactionHistory.fromJson(Map<String, dynamic> json) {
    final rawList =
        json['transactions'] ?? json['items'] ?? json['data'] ?? [];
    final txList = JsonUtils.listOfMaps(rawList)
        .map(Transaction.fromJson)
        .toList()
      ..sort((a, b) => b.txTime.compareTo(a.txTime));

    return TransactionHistory(
      transactions: txList,
      totalCount:
          JsonUtils.intValue(json, 'total_count', fallback: txList.length),
      days: JsonUtils.intValue(json, 'days', fallback: 30),
    );
  }
}

class Transaction {
  Transaction({
    required this.txHash,
    required this.blockchain,
    required this.direction,
    required this.amount,
    required this.symbol,
    required this.valueUsd,
    required this.fromAddress,
    required this.toAddress,
    required this.txTime,
    required this.fee,
    required this.feeSymbol,
  });

  final String txHash;
  final String blockchain;
  final String direction;
  final double amount;
  final String symbol;
  final double valueUsd;
  final String fromAddress;
  final String toAddress;
  final DateTime txTime;
  final double fee;
  final String feeSymbol;

  factory Transaction.fromJson(Map<String, dynamic> json) {
    return Transaction(
      txHash: JsonUtils.string(json, 'tx_hash'),
      blockchain: JsonUtils.string(json, 'blockchain'),
      direction: JsonUtils.string(json, 'direction', fallback: 'unknown'),
      amount: JsonUtils.doubleValue(json, 'amount'),
      symbol: JsonUtils.string(json, 'symbol'),
      valueUsd: JsonUtils.doubleValue(json, 'value_usd'),
      fromAddress: JsonUtils.string(json, 'from_address'),
      toAddress: JsonUtils.string(json, 'to_address'),
      txTime: _parseTxTime(json),
      fee: JsonUtils.doubleValue(json, 'fee'),
      feeSymbol: JsonUtils.string(json, 'fee_symbol'),
    );
  }

  static DateTime _parseTxTime(Map<String, dynamic> json) {
    final raw = json['tx_time'] ?? json['timestamp'] ?? json['time'];
    if (raw is String && raw.trim().isNotEmpty) {
      return DateTime.tryParse(raw)?.toLocal() ?? DateTime.now();
    }
    if (raw is int) {
      final isMillis = raw > 1000000000000;
      final value = isMillis ? raw : raw * 1000;
      return DateTime.fromMillisecondsSinceEpoch(value).toLocal();
    }
    if (raw is num) {
      final asInt = raw.toInt();
      final isMillis = asInt > 1000000000000;
      final value = isMillis ? asInt : asInt * 1000;
      return DateTime.fromMillisecondsSinceEpoch(value).toLocal();
    }
    return DateTime.now();
  }
}
