import 'package:abct_mobile/core/models/connection_profile.dart';
import 'package:abct_mobile/core/models/staking_summary.dart';
import 'package:abct_mobile/core/network/api_client.dart';
import 'package:abct_mobile/core/network/cache_interceptor.dart';
import 'package:abct_mobile/core/ui/app_refresh.dart';
import 'package:abct_mobile/features/home/tabs/staking_tab.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Protocol grouping on the Staking tab (UI-1): per-protocol sections with
/// group totals and counts, collapse/expand, flat rendering for
/// single-position groups, the priced=false "value estimated" indicator,
/// and expanded-state preservation across silent reloads.
final _profile = ConnectionProfile(
  name: 'test',
  baseUrl: 'https://example.invalid',
);

StakingPosition position({
  String blockchain = 'cardano',
  String poolName = 'Pool',
  String protocol = 'cardano',
  String positionKind = '',
  String stakedSymbol = '',
  double delegatedUsd = 100,
  bool priced = true,
}) {
  return StakingPosition(
    blockchain: blockchain,
    stakeKey: 'stake_$poolName',
    poolId: 'pool_$poolName',
    poolName: poolName,
    poolTicker: '',
    stakedSymbol: stakedSymbol,
    delegatedAmount: delegatedUsd,
    delegatedUsd: delegatedUsd,
    rewardsLifetime: 1,
    rewardsUsd: 1,
    apy: 3,
    active: true,
    logoUrl: '',
    protocol: protocol,
    positionKind: positionKind,
    priced: priced,
  );
}

class FakeStakingApi extends ApiClient {
  FakeStakingApi(this.positions) : super(_profile);

  int fetches = 0;
  List<StakingPosition> positions;

  @override
  Future<StakingSummary> getStaking({
    bool refresh = false,
    bool revalidate = false,
  }) async {
    fetches++;
    return StakingSummary(
      totalStakedUsd:
          positions.fold(0.0, (sum, p) => sum + p.delegatedUsd),
      totalRewardsUsd: positions.fold(0.0, (sum, p) => sum + p.rewardsUsd),
      positions: positions,
    );
  }
}

List<StakingPosition> mixedPositions() => [
      position(poolName: 'Delegation A', delegatedUsd: 100),
      position(poolName: 'Delegation B', delegatedUsd: 200),
      position(poolName: 'Delegation C', delegatedUsd: 300),
      position(
        poolName: 'Indigo INDY Staking',
        protocol: 'indigo',
        stakedSymbol: 'INDY',
        delegatedUsd: 50,
      ),
      position(
        poolName: 'Strike Trading',
        protocol: 'strike',
        stakedSymbol: 'STRIKE',
        delegatedUsd: 40,
      ),
      position(
        poolName: 'Strike Vault',
        protocol: 'strike',
        positionKind: 'vault',
        stakedSymbol: 'STRIKE',
        delegatedUsd: 30,
        priced: false,
      ),
    ];

Future<FakeStakingApi> pumpStaking(
  WidgetTester tester,
  List<StakingPosition> positions,
) async {
  final api = FakeStakingApi(positions);
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: StakingTab(profile: _profile, apiClient: api)),
    ),
  );
  await tester.pumpAndSettle();
  return api;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(ApiClient.resetSharedForTesting);

  group('protocol grouping', () {
    testWidgets('multi-position groups show name, total, and count',
        (tester) async {
      await pumpStaking(tester, mixedPositions());

      // Native delegations collapse to one Cardano group row. ("Cardano"
      // also appears as the blockchain label on flat position tiles, so the
      // group row is identified by its count line.)
      expect(find.text('Cardano'), findsWidgets);
      expect(find.text('3 delegations'), findsOneWidget);
      expect(find.text('\$600.00'), findsOneWidget);
      expect(find.text('Delegation A'), findsNothing);

      // Strike groups its trading and vault rows.
      expect(find.text('Strike'), findsOneWidget);
      expect(find.text('2 positions'), findsOneWidget);
      expect(find.text('\$70.00'), findsOneWidget);
    });

    testWidgets('tapping a group expands to individual positions',
        (tester) async {
      await pumpStaking(tester, mixedPositions());

      await tester.tap(find.text('3 delegations'));
      await tester.pumpAndSettle();

      expect(find.text('Delegation A'), findsOneWidget);
      expect(find.text('Delegation B'), findsOneWidget);
      expect(find.text('Delegation C'), findsOneWidget);

      await tester.tap(find.text('3 delegations'));
      await tester.pumpAndSettle();
      expect(find.text('Delegation A'), findsNothing);
    });

    testWidgets('single-position group renders flat without expansion chrome',
        (tester) async {
      await pumpStaking(tester, mixedPositions());

      // Indigo's lone position is visible directly, with no group row.
      expect(find.text('Indigo INDY Staking'), findsOneWidget);
      expect(find.text('1 position'), findsNothing);

      // Only the two multi-position groups get expansion tiles.
      expect(find.byType(ExpansionTile), findsNWidgets(2));
    });

    testWidgets('unknown protocols group by their payload identifier',
        (tester) async {
      await pumpStaking(tester, [
        position(poolName: 'Nova A', protocol: 'nova_stake', delegatedUsd: 10),
        position(poolName: 'Nova B', protocol: 'nova_stake', delegatedUsd: 20),
        // Second protocol so the Total Staked stat tile differs from the
        // Nova Stake group total.
        position(
          poolName: 'Iagon Staking',
          protocol: 'iagon',
          stakedSymbol: 'IAG',
          delegatedUsd: 1000,
        ),
      ]);

      expect(find.text('Nova Stake'), findsOneWidget);
      expect(find.text('\$30.00'), findsOneWidget);
    });
  });

  group('group header logos', () {
    Iterable<String> imageUrls(WidgetTester tester) => tester
        .widgetList<CachedNetworkImage>(find.byType(CachedNetworkImage))
        .map((widget) => widget.imageUrl);

    testWidgets(
        'Strike group shows the protocol mark even when all rows are '
        'ADA-denominated', (tester) async {
      await pumpStaking(tester, [
        position(
          poolName: 'Strike V2 Trading Account',
          protocol: 'Strike',
          positionKind: 'trading_balance',
          stakedSymbol: 'ADA',
          delegatedUsd: 40,
        ),
        position(
          poolName: 'Strike Vault',
          protocol: 'Strike',
          positionKind: 'vault',
          stakedSymbol: 'ADA',
          delegatedUsd: 30,
        ),
      ]);

      expect(
        imageUrls(tester),
        contains('https://example.invalid/images/token/STRIKE'),
      );
      expect(
        imageUrls(tester),
        isNot(contains('https://example.invalid/images/token/ADA')),
      );

      // Image loads fail in the test env, so the fallback renders — it must
      // be the protocol-initial avatar, never a chain mark that would make a
      // failed load look like the wrong-logo bug.
      expect(
        find.descendant(
          of: find.byType(CircleAvatar),
          matching: find.text('S'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('Cardano native delegation group keeps the ADA mark',
        (tester) async {
      await pumpStaking(tester, [
        position(poolName: 'Delegation A', delegatedUsd: 100),
        position(poolName: 'Delegation B', delegatedUsd: 200),
      ]);

      expect(
        imageUrls(tester),
        contains('https://example.invalid/images/token/ADA'),
      );
    });

    testWidgets('unknown protocol falls back to its own token position logo',
        (tester) async {
      await pumpStaking(tester, [
        position(
          poolName: 'Nova A',
          protocol: 'nova_stake',
          stakedSymbol: 'NOVA',
          delegatedUsd: 10,
        ),
        position(
          poolName: 'Nova B',
          protocol: 'nova_stake',
          stakedSymbol: 'ADA',
          delegatedUsd: 20,
        ),
      ]);

      expect(
        imageUrls(tester),
        contains('https://example.invalid/images/token/NOVA'),
      );
    });
  });

  group('priced indicator', () {
    testWidgets('group containing an unpriced position shows value estimated',
        (tester) async {
      await pumpStaking(tester, mixedPositions());

      // Collapsed Strike group surfaces the indicator; expanding shows it on
      // the unpriced vault row too.
      expect(find.text('value estimated'), findsOneWidget);

      await tester.tap(find.text('Strike'));
      await tester.pumpAndSettle();
      expect(find.text('value estimated'), findsNWidgets(2));
    });

    testWidgets('fully priced data shows no indicator', (tester) async {
      await pumpStaking(tester, [
        position(poolName: 'Delegation A', delegatedUsd: 100),
        position(
          poolName: 'Indigo INDY Staking',
          protocol: 'indigo',
          stakedSymbol: 'INDY',
          delegatedUsd: 50,
        ),
      ]);

      expect(find.text('value estimated'), findsNothing);
    });
  });

  group('expanded-state preservation', () {
    testWidgets('expanded group survives a silent reload', (tester) async {
      final api = await pumpStaking(tester, mixedPositions());
      expect(api.fetches, 1);

      await tester.tap(find.text('3 delegations'));
      await tester.pumpAndSettle();
      expect(find.text('Delegation A'), findsOneWidget);

      // Background revalidation lands for the staking endpoint.
      CacheInterceptor.debugNotifyRevalidated(
        'https://example.invalid/api/mobile/defi/staking',
        <String, dynamic>{},
      );
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();

      expect(api.fetches, 2);
      expect(find.text('Delegation A'), findsOneWidget);
      expect(find.text('Delegation C'), findsOneWidget);
    });

    testWidgets('resume signal reload also preserves expansion',
        (tester) async {
      final api = await pumpStaking(tester, mixedPositions());

      await tester.tap(find.text('Strike'));
      await tester.pumpAndSettle();
      expect(find.text('Strike Vault'), findsOneWidget);

      (tester.state(find.byType(StakingTab)) as dynamic)
          .debugBackdateLastLoad(const Duration(seconds: 31));
      AppRefreshSignal.instance.debugEmitSignal();
      await tester.pumpAndSettle();

      expect(api.fetches, 2);
      expect(find.text('Strike Vault'), findsOneWidget);
    });
  });

  group('StakingPosition parsing', () {
    test('parses protocol, position_kind, and priced', () {
      final parsed = StakingPosition.fromJson({
        'blockchain': 'cardano',
        'protocol': 'strike',
        'position_kind': 'vault',
        'priced': false,
        'pool_name': 'Strike Vault',
        'delegated_usd': 12.5,
      });

      expect(parsed.protocol, 'strike');
      expect(parsed.positionKind, 'vault');
      expect(parsed.priced, false);
      expect(parsed.isNativeDelegation, false);
    });

    test('falls back to blockchain and priced=true on older payloads', () {
      final parsed = StakingPosition.fromJson({
        'blockchain': 'cardano',
        'pool_name': 'Some Pool',
        'delegated_usd': 100,
      });

      expect(parsed.protocol, 'cardano');
      expect(parsed.priced, true);
      expect(parsed.isNativeDelegation, true);
    });
  });
}
