import 'json_utils.dart';

class NftsSummary {
  NftsSummary({
    required this.totalNfts,
    required this.totalCollections,
    required this.totalFloorValueUsd,
    required this.collections,
    this.lastUpdated,
  });

  factory NftsSummary.empty() {
    return NftsSummary(
      totalNfts: 0,
      totalCollections: 0,
      totalFloorValueUsd: 0,
      collections: const [],
      lastUpdated: null,
    );
  }

  final int totalNfts;
  final int totalCollections;
  final double totalFloorValueUsd;
  final List<NftCollectionSummary> collections;
  final DateTime? lastUpdated;

  factory NftsSummary.fromJson(Map<String, dynamic> json) {
    final collectionItems = JsonUtils.listOfMaps(json['collections'])
        .map(NftCollectionSummary.fromJson)
        .toList()
      ..sort((a, b) => b.totalFloorValueUsd.compareTo(a.totalFloorValueUsd));

    return NftsSummary(
      totalNfts: JsonUtils.intValue(json, 'total_nfts'),
      totalCollections: JsonUtils.intValue(json, 'total_collections'),
      totalFloorValueUsd: JsonUtils.doubleValue(json, 'total_floor_value_usd'),
      collections: collectionItems,
      lastUpdated: JsonUtils.dateTime(json, 'last_updated'),
    );
  }
}

class NftCollectionSummary {
  NftCollectionSummary({
    required this.name,
    required this.blockchain,
    required this.nftCount,
    required this.floorPriceNative,
    required this.floorPriceUsd,
    required this.totalFloorValueUsd,
    this.imageUrl,
    this.thumbnailUrl,
    this.logoUrl,
    this.detailsUrl,
    this.policyId,
    required this.galleryImageUrls,
  });

  final String name;
  final String blockchain;
  final int nftCount;
  final double floorPriceNative;
  final double floorPriceUsd;
  final double totalFloorValueUsd;
  final String? imageUrl;
  final String? thumbnailUrl;
  final String? logoUrl;
  final String? detailsUrl;
  final String? policyId;
  final List<String> galleryImageUrls;

  String? get previewImageUrl {
    for (final value in [
      imageUrl,
      thumbnailUrl,
      ...galleryImageUrls,
      logoUrl,
    ]) {
      if (value != null && value.trim().isNotEmpty) {
        return value.trim();
      }
    }
    return null;
  }

  factory NftCollectionSummary.fromJson(Map<String, dynamic> json) {
    return NftCollectionSummary(
      name: JsonUtils.string(json, 'name', fallback: 'Unknown Collection'),
      blockchain: JsonUtils.string(json, 'blockchain', fallback: 'unknown'),
      nftCount: JsonUtils.intValue(json, 'nft_count'),
      floorPriceNative: JsonUtils.doubleValue(json, 'floor_price_native'),
      floorPriceUsd: JsonUtils.doubleValue(json, 'floor_price_usd'),
      totalFloorValueUsd: JsonUtils.doubleValue(json, 'total_floor_value_usd'),
      imageUrl: JsonUtils.optionalString(json, 'image_url'),
      thumbnailUrl: JsonUtils.optionalString(json, 'thumbnail_url'),
      logoUrl: JsonUtils.optionalString(json, 'logo_url'),
      detailsUrl: JsonUtils.optionalString(json, 'details_url'),
      policyId: JsonUtils.optionalString(json, 'policy_id'),
      galleryImageUrls: _readGalleryImageUrls(json),
    );
  }

  static List<String> _readGalleryImageUrls(Map<String, dynamic> json) {
    final out = <String>[];
    final chain = JsonUtils.string(json, 'blockchain', fallback: '').trim();

    void add(dynamic value) {
      if (value is! String) return;
      final trimmed = value.trim();
      if (trimmed.isEmpty) return;
      if (!out.contains(trimmed)) {
        out.add(trimmed);
      }
    }

    void addGeneratedThumbnail(Map<String, dynamic> nft) {
      final assetId = JsonUtils.optionalString(nft, 'asset_id');
      if (assetId == null || assetId.trim().isEmpty || chain.isEmpty) {
        return;
      }
      add('/nfts/images/$chain/${assetId.trim()}/thumbnail');
    }

    // 1) Direct image URL from NFT data.
    final nfts = JsonUtils.listOfMaps(json['nfts']);
    for (final nft in nfts) {
      add(nft['image']);
      add(nft['image_url']);
    }

    // 2) image_url from EVM chains (and related nested image fields).
    for (final nft in nfts) {
      for (final key in const [
        'image_url',
        'thumbnail_url',
        'thumbnail',
        'media_url',
        'preview_image',
        'metadata_image_url',
      ]) {
        add(nft[key]);
      }
      final metadata = JsonUtils.map(nft['metadata']);
      if (metadata.isNotEmpty) {
        add(metadata['image']);
        add(metadata['image_url']);
      }
    }

    // 3) Generated backend thumbnail endpoint.
    for (final nft in nfts) {
      addGeneratedThumbnail(nft);
    }

    // Collection-level fallbacks last.
    for (final key in const [
      'image_url',
      'thumbnail_url',
      'image',
      'thumbnail',
      'preview_image',
      'cover_image',
      'logo_url',
    ]) {
      add(json[key]);
    }

    return out;
  }
}
