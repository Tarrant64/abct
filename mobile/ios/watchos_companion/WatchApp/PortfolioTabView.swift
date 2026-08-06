import SwiftUI

struct PortfolioTabView: View {
  let data: PortfolioWatchData
  let onRefresh: () -> Void
  let onHandoff: () -> Void

  @State private var selectedTab = 0

  var body: some View {
    NavigationStack {
      TabView(selection: $selectedTab) {
        PortfolioOverviewPage(
          data: data,
          onRefresh: onRefresh,
          onHandoff: onHandoff
        )
        .tag(0)

        AssetListPage(assets: data.assets)
          .tag(1)

        FavoritesPage(assets: data.assets)
          .tag(2)
      }
      .tabViewStyle(.page(indexDisplayMode: .automatic))
      .background(Color.black)
    }
  }
}

#Preview {
  PortfolioTabView(
    data: .sample,
    onRefresh: {},
    onHandoff: {}
  )
}
