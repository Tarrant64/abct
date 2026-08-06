import 'package:flutter/material.dart';

import '../../core/models/connection_profile.dart';
import '../../core/ui/haptics.dart';
import '../../core/ui/value_formatters.dart';
import 'tabs/assets_tab.dart';
import 'tabs/dashboard_tab.dart';
import 'tabs/nfts_tab.dart';
import 'tabs/settings_tab.dart';
import 'tabs/staking_tab.dart';
import 'tabs/wallets_tab.dart';

class HomeShellScreen extends StatefulWidget {
  const HomeShellScreen({super.key, required this.profile});

  final ConnectionProfile profile;

  @override
  State<HomeShellScreen> createState() => _HomeShellScreenState();
}

class _HomeShellScreenState extends State<HomeShellScreen> {
  int _index = 0;

  final Map<int, Widget> _tabCache = {};

  Widget _getOrCreateTab(int index) {
    return _tabCache.putIfAbsent(index, () => switch (index) {
      0 => DashboardTab(
        key: const ValueKey(0),
        profile: widget.profile,
        onNavigateToAssets: () => setState(() => _index = 1),
      ),
      1 => AssetsTab(key: const ValueKey(1), profile: widget.profile),
      2 => WalletsTab(key: const ValueKey(2), profile: widget.profile),
      3 => StakingTab(key: const ValueKey(3), profile: widget.profile),
      4 => NftsTab(key: const ValueKey(4), profile: widget.profile),
      5 => SettingsTab(key: const ValueKey(5), profile: widget.profile),
      _ => const SizedBox.shrink(),
    });
  }

  static const _titles = [
    'Portfolio',
    'Assets',
    'Wallets',
    'Staking',
    'NFTs',
    'Settings',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Text(
                ValueFormatters.titleCase(widget.profile.name),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
        ],
      ),
      body: IndexedStack(
        index: _index,
        children: List.generate(6, (i) {
          // Only create tabs that have been visited (current + previously visited)
          if (i == _index || _tabCache.containsKey(i)) {
            return _getOrCreateTab(i);
          }
          return const SizedBox.shrink();
        }),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) {
          Haptics.selection();
          setState(() {
            _index = value;
          });
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.pie_chart_outline),
            selectedIcon: Icon(Icons.pie_chart),
            label: 'Overview',
          ),
          NavigationDestination(
            icon: Icon(Icons.account_balance_outlined),
            selectedIcon: Icon(Icons.account_balance),
            label: 'Assets',
          ),
          NavigationDestination(
            icon: Icon(Icons.account_balance_wallet_outlined),
            selectedIcon: Icon(Icons.account_balance_wallet),
            label: 'Wallets',
          ),
          NavigationDestination(
            icon: Icon(Icons.stacked_line_chart_outlined),
            selectedIcon: Icon(Icons.stacked_line_chart),
            label: 'Staking',
          ),
          NavigationDestination(
            icon: Icon(Icons.image_outlined),
            selectedIcon: Icon(Icons.image),
            label: 'NFTs',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
        ],
      ),
    );
  }
}
