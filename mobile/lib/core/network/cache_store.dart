import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

/// Metadata about a cached entry's freshness.
class CacheEntry {
  const CacheEntry({
    required this.data,
    required this.isFresh,
    required this.cachedAt,
    this.etag,
  });

  /// The cached response body.
  final dynamic data;

  /// Whether the entry is still within its TTL.
  final bool isFresh;

  /// When the data was originally cached (milliseconds since epoch).
  final int cachedAt;

  /// The ETag the server sent with this payload, if any. Used for
  /// If-None-Match conditional revalidation (entries written before ETag
  /// support simply have none).
  final String? etag;

  /// Age of this cache entry.
  Duration get age =>
      Duration(milliseconds: DateTime.now().millisecondsSinceEpoch - cachedAt);
}

/// Disk-backed response cache with an in-memory LRU layer.
///
/// All file I/O is asynchronous and JSON payloads above
/// [isolateJsonThresholdBytes] are decoded/encoded off the UI isolate, so
/// cache access never janks a frame. Repeat reads are served from the LRU
/// without touching disk at all.
///
/// [clear] wipes both layers — callers relying on cache-clear-on-logout get
/// the in-memory copies destroyed along with the files.
class CacheStore {
  CacheStore._() : _memoryCapacity = defaultMemoryCapacity;

  /// Test-only constructor that stores entries in [directory] instead of the
  /// app documents directory, so tests can run without path_provider.
  @visibleForTesting
  CacheStore.forDirectory(
    Directory directory, {
    int memoryCapacity = defaultMemoryCapacity,
  })  : _cacheDir = directory,
        _memoryCapacity = memoryCapacity;

  static final CacheStore instance = CacheStore._();

  /// Maximum number of entries held in the in-memory LRU layer.
  static const int defaultMemoryCapacity = 32;

  /// JSON strings longer than this are decoded/encoded via [compute] so the
  /// work happens off the UI isolate. Below it, isolate spawn overhead costs
  /// more than the parse itself.
  static const int isolateJsonThresholdBytes = 64 * 1024;

  Directory? _cacheDir;
  final int _memoryCapacity;

  /// Monotonic clear-fence, bumped by [clear] before anything else.
  ///
  /// Every code path that will insert into memory or persist to disk
  /// snapshots this at entry and abandons its work if the value has moved —
  /// otherwise a write in flight when logout clears the cache would
  /// re-persist the previous session's data for the next user.
  int _generation = 0;

  /// Current clear-fence value. Consumers doing async work between reading
  /// data and writing it back (e.g. the cache interceptor's network round
  /// trips) snapshot this and skip the write-back if it has changed.
  int get generation => _generation;

  /// In-memory LRU keyed by file key; insertion order == recency
  /// (least-recently-used first).
  final LinkedHashMap<String, _MemoryEntry> _memory =
      LinkedHashMap<String, _MemoryEntry>();

  Future<Directory> _dir() async {
    if (_cacheDir != null) return _cacheDir!;
    final appDir = await getApplicationDocumentsDirectory();
    final dir = Directory('${appDir.path}/api_cache');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    _cacheDir = dir;
    return dir;
  }

  String _fileKey(String url) {
    final hash = sha256.convert(utf8.encode(url)).toString();
    return hash.substring(0, 32);
  }

  Future<File> _fileFor(String url) async {
    final dir = await _dir();
    return File('${dir.path}/${_fileKey(url)}.json');
  }

  /// Read cached data for [url]. Returns `null` if expired or missing.
  Future<dynamic> read(String url) async {
    final entry = await _entryFor(url);
    if (entry == null || entry.isExpired) return null;
    return entry.data;
  }

  /// Read cached data even if expired (offline fallback).
  Future<dynamic> readStale(String url) async {
    final entry = await _entryFor(url);
    return entry?.data;
  }

  /// Read cached data with freshness metadata.
  ///
  /// Returns a [CacheEntry] with `isFresh` indicating whether the data is
  /// within its TTL. Returns `null` only if no cached data exists at all.
  /// This powers the stale-while-revalidate pattern: callers can render stale
  /// data immediately while fetching fresh data in the background.
  Future<CacheEntry?> readWithMeta(String url) async {
    final entry = await _entryFor(url);
    if (entry == null) return null;
    return CacheEntry(
      data: entry.data,
      isFresh: !entry.isExpired,
      cachedAt: entry.cachedAt,
      etag: entry.etag,
    );
  }

  /// Write [data] to the cache with a TTL of [ttlSeconds], remembering the
  /// server's [etag] when provided.
  Future<void> write(
    String url,
    dynamic data,
    int ttlSeconds, {
    String? etag,
  }) async {
    final generation = _generation;
    final now = DateTime.now().millisecondsSinceEpoch;
    final entry = _MemoryEntry(
      url: url,
      data: data,
      cachedAt: now,
      expiresAt: now + (ttlSeconds * 1000),
      etag: etag,
    );
    _memoryPut(_fileKey(url), entry);
    await _persist(entry, generation);
  }

  /// Re-stamp the entry for [url] as fresh for another [ttlSeconds] without
  /// changing its data or ETag. Backs 304 Not Modified revalidations, where
  /// the server confirmed the cached payload is still current. No-op if no
  /// entry exists.
  Future<void> touch(String url, int ttlSeconds) async {
    final generation = _generation;
    final entry = await _entryFor(url);
    // Abandon if the store was cleared while reading: the entry belongs to
    // the previous session and must not be re-stamped back to life.
    if (entry == null || generation != _generation) return;
    final now = DateTime.now().millisecondsSinceEpoch;
    entry.cachedAt = now;
    entry.expiresAt = now + (ttlSeconds * 1000);
    _memoryPut(_fileKey(url), entry);
    await _persist(entry, generation);
  }

  /// Delete all expired entries.
  Future<void> evictExpired() async {
    final generation = _generation;
    final now = DateTime.now().millisecondsSinceEpoch;
    _memory.removeWhere((_, entry) => now > entry.expiresAt);

    final dir = await _dir();
    if (!await dir.exists()) return;
    try {
      await for (final entity in dir.list()) {
        // A clear() mid-sweep already removed everything; stop touching disk.
        if (generation != _generation) return;
        if (entity is! File || !entity.path.endsWith('.json')) continue;
        try {
          final entry = await _decodeFile(entity);
          final expiresAt = entry['expires_at'] as int? ?? 0;
          if (now > expiresAt && generation == _generation) {
            await entity.delete();
          }
        } catch (_) {
          if (generation == _generation) {
            await entity.delete();
          }
        }
      }
    } on FileSystemException {
      // Directory replaced underneath us by clear(); nothing left to evict.
    }
  }

  /// Wipe all cached data — both the in-memory layer and the files.
  ///
  /// Called on logout: bumping [generation] FIRST means every in-flight
  /// write/touch (and any interceptor write whose request predates this
  /// clear) abandons instead of re-persisting the old session's data.
  Future<void> clear() async {
    _generation++;
    _memory.clear();
    final dir = await _dir();
    if (await dir.exists()) {
      await dir.delete(recursive: true);
      await dir.create(recursive: true);
    }
  }

  /// Returns the entry for [url] from memory (promoting it to
  /// most-recently-used) or, failing that, from disk (populating memory).
  Future<_MemoryEntry?> _entryFor(String url) async {
    final generation = _generation;
    final key = _fileKey(url);
    final cached = _memory.remove(key);
    if (cached != null) {
      _memory[key] = cached; // re-insert as most recently used
      return cached;
    }

    final file = await _fileFor(url);
    if (!await file.exists()) return null;
    try {
      final decoded = await _decodeFile(file);
      // Cleared while reading: the bytes came from a file clear() has (or is
      // about to have) deleted — don't resurrect them into memory.
      if (generation != _generation) return null;
      final entry = _MemoryEntry(
        url: url,
        data: decoded['data'],
        cachedAt: decoded['cached_at'] as int? ?? 0,
        expiresAt: decoded['expires_at'] as int? ?? 0,
        // Entries written before ETag support have no etag field.
        etag: decoded['etag'] as String?,
      );
      _memoryPut(key, entry);
      return entry;
    } catch (_) {
      return null;
    }
  }

  void _memoryPut(String key, _MemoryEntry entry) {
    _memory.remove(key);
    _memory[key] = entry;
    while (_memory.length > _memoryCapacity) {
      _memory.remove(_memory.keys.first);
    }
  }

  /// Persists [entry], abandoning at every stage if [generation] no longer
  /// matches the store's — a clear() (logout) fired after the write began,
  /// and committing would hand the old session's data to the next one.
  Future<void> _persist(_MemoryEntry entry, int generation) async {
    final file = await _fileFor(entry.url);
    final json = <String, dynamic>{
      'url': entry.url,
      'data': entry.data,
      'cached_at': entry.cachedAt,
      'expires_at': entry.expiresAt,
      if (entry.etag != null) 'etag': entry.etag,
    };
    final encoded = await _encodeJson(json);
    if (generation != _generation) return;
    // Write-then-rename so a concurrent read never sees a half-written file.
    final tmp = File('${file.path}.tmp');
    await tmp.writeAsString(encoded);
    if (generation != _generation) {
      // Abandon mid-write: never commit, and remove the orphaned tmp file.
      try {
        await tmp.delete();
      } catch (_) {}
      return;
    }
    await tmp.rename(file.path);
    if (generation != _generation) {
      // clear() landed between the last check and the rename — undo it.
      try {
        await file.delete();
      } catch (_) {}
    }
  }

  Future<Map<String, dynamic>> _decodeFile(File file) async {
    final raw = await file.readAsString();
    final decoded = raw.length > isolateJsonThresholdBytes
        ? await compute(jsonDecode, raw)
        : jsonDecode(raw);
    return decoded as Map<String, dynamic>;
  }

  Future<String> _encodeJson(Map<String, dynamic> json) async {
    // Size isn't knowable before encoding, so route all structured payloads
    // (every API response body is a Map or List) off the UI isolate;
    // primitive payloads are trivially cheap inline.
    final data = json['data'];
    if (data is Map || data is List) {
      return compute(jsonEncode, json);
    }
    return jsonEncode(json);
  }
}

/// Mutable in-memory representation of a cache entry.
class _MemoryEntry {
  _MemoryEntry({
    required this.url,
    required this.data,
    required this.cachedAt,
    required this.expiresAt,
    this.etag,
  });

  final String url;
  final dynamic data;
  int cachedAt;
  int expiresAt;
  final String? etag;

  bool get isExpired => DateTime.now().millisecondsSinceEpoch > expiresAt;
}
