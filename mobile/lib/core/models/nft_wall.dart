import 'json_utils.dart';

class NftWallPage {
  const NftWallPage({
    required this.items,
    required this.fetchedCount,
    this.total,
  });

  final List<NftWallItem> items;
  final int fetchedCount;
  final int? total;
}

class NftWallItem {
  const NftWallItem({
    required this.chain,
    required this.assetId,
    required this.name,
    this.collectionName,
    this.thumbnailUrl,
    this.imageUrl,
    this.detailsUrl,
  });

  final String chain;
  final String assetId;
  final String name;
  final String? collectionName;
  final String? thumbnailUrl;
  final String? imageUrl;
  final String? detailsUrl;

  String get stableKey => '$chain|$assetId';

  factory NftWallItem.fromJson(Map<String, dynamic> json) {
    final assetId = JsonUtils.optionalString(json, 'asset_id') ??
        JsonUtils.optionalString(json, 'id') ??
        JsonUtils.optionalString(json, 'token_id') ??
        '';

    final chain = JsonUtils.optionalString(json, 'chain') ??
        JsonUtils.optionalString(json, 'blockchain') ??
        JsonUtils.optionalString(json, 'network') ??
        'unknown';

    final name = JsonUtils.optionalString(json, 'name') ??
        JsonUtils.optionalString(json, 'title') ??
        JsonUtils.optionalString(json, 'display_name') ??
        'Untitled NFT';

    return NftWallItem(
      chain: chain.trim().isEmpty ? 'unknown' : chain.trim(),
      assetId: assetId.trim(),
      name: name.trim().isEmpty ? 'Untitled NFT' : name.trim(),
      collectionName: JsonUtils.optionalString(json, 'collection_name') ??
          JsonUtils.optionalString(json, 'collection'),
      thumbnailUrl: _firstNonEmpty([
        JsonUtils.optionalString(json, 'thumbnail_url'),
        JsonUtils.optionalString(json, 'thumbnail'),
        JsonUtils.optionalString(json, 'preview_image'),
        JsonUtils.optionalString(json, 'image_thumb'),
      ]),
      imageUrl: _firstNonEmpty([
        JsonUtils.optionalString(json, 'image_url'),
        JsonUtils.optionalString(json, 'image'),
        JsonUtils.optionalString(json, 'full_image_url'),
        JsonUtils.optionalString(json, 'media_url'),
      ]),
      detailsUrl: JsonUtils.optionalString(json, 'details_url') ??
          JsonUtils.optionalString(json, 'detail_url'),
    );
  }

  static String? _firstNonEmpty(List<String?> values) {
    for (final value in values) {
      if (value != null && value.trim().isNotEmpty) {
        return value.trim();
      }
    }
    return null;
  }
}
