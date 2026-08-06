import 'dart:convert';
import 'dart:io';

import 'package:abct_mobile/core/network/cache_store.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

// Tests exercise the real CacheStore against a temp directory (via the
// forDirectory test constructor); the older groups below additionally pin
// the on-disk entry format directly with dart:io.

void main() {
  late Directory tmpDir;

  setUp(() {
    tmpDir = Directory.systemTemp.createTempSync('cache_store_test_');
  });

  tearDown(() {
    if (tmpDir.existsSync()) {
      tmpDir.deleteSync(recursive: true);
    }
  });

  /// Replicates CacheStore's URL → file mapping for direct disk inspection.
  File fileForUrl(String url) {
    final hash = sha256.convert(utf8.encode(url)).toString();
    return File('${tmpDir.path}/${hash.substring(0, 32)}.json');
  }

  void deleteAllCacheFiles() {
    for (final entity in tmpDir.listSync()) {
      if (entity is File && entity.path.endsWith('.json')) {
        entity.deleteSync();
      }
    }
  }

  group('CacheStore async round-trip', () {
    test('write and read back data with metadata and ETag', () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', {'value': 1}, 300, etag: '"v1"');

      expect(await store.read('https://x/a'), {'value': 1});
      final meta = await store.readWithMeta('https://x/a');
      expect(meta!.isFresh, isTrue);
      expect(meta.etag, '"v1"');
      expect(meta.age, lessThan(const Duration(seconds: 5)));

      // Entry survives a fresh store instance (really on disk).
      final second = CacheStore.forDirectory(tmpDir);
      expect(await second.read('https://x/a'), {'value': 1});
      expect((await second.readWithMeta('https://x/a'))!.etag, '"v1"');
    });

    test('expired entries read null but stale-read returns data', () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', 'old', 0);
      await Future<void>.delayed(const Duration(milliseconds: 5));

      expect(await store.read('https://x/a'), isNull);
      expect(await store.readStale('https://x/a'), 'old');
      expect((await store.readWithMeta('https://x/a'))!.isFresh, isFalse);
    });

    test('large payloads round-trip through the isolate decode path',
        () async {
      final store = CacheStore.forDirectory(tmpDir);
      final big = {
        'blob': List<String>.generate(2000, (i) => 'row-$i-${'x' * 50}'),
      };
      expect(jsonEncode({'data': big}).length,
          greaterThan(CacheStore.isolateJsonThresholdBytes));

      await store.write('https://x/big', big, 300);
      // Fresh instance forces the disk decode path (memory bypassed).
      final second = CacheStore.forDirectory(tmpDir);
      expect(await second.read('https://x/big'), big);
    });
  });

  group('CacheStore in-memory LRU', () {
    test('repeat reads are served from memory without touching disk',
        () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', {'value': 1}, 300);

      // Remove the backing file: only the memory layer can answer now.
      deleteAllCacheFiles();
      expect(await store.read('https://x/a'), {'value': 1});
    });

    test('exceeding capacity evicts the least recently used entry', () async {
      final store = CacheStore.forDirectory(tmpDir, memoryCapacity: 2);
      await store.write('https://x/a', 'a', 300);
      await store.write('https://x/b', 'b', 300);
      // Touch /a so /b becomes the least recently used…
      await store.read('https://x/a');
      // …then push a third entry in.
      await store.write('https://x/c', 'c', 300);

      deleteAllCacheFiles();
      expect(await store.read('https://x/a'), 'a'); // retained (recent)
      expect(await store.read('https://x/c'), 'c'); // retained (newest)
      expect(await store.read('https://x/b'), isNull); // evicted
    });

    test('clear wipes the memory layer as well as disk (logout semantics)',
        () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', 'secret', 300);

      await store.clear();

      expect(await store.read('https://x/a'), isNull);
      expect(await store.readStale('https://x/a'), isNull);
      expect(
        tmpDir.listSync().whereType<File>().where(
              (f) => f.path.endsWith('.json'),
            ),
        isEmpty,
      );
    });

    test('evictExpired removes expired entries from memory and disk',
        () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/old', 'old', 0);
      await store.write('https://x/new', 'new', 300);
      await Future<void>.delayed(const Duration(milliseconds: 5));

      await store.evictExpired();

      expect(await store.readStale('https://x/old'), isNull);
      expect(await store.read('https://x/new'), 'new');
      expect(fileForUrl('https://x/old').existsSync(), isFalse);
      expect(fileForUrl('https://x/new').existsSync(), isTrue);
    });
  });

  group('CacheStore clear-fence (logout race)', () {
    // A payload large enough to force the compute-encode path, guaranteeing
    // the write suspends before persisting — the window logout races into.
    final bigData = {
      'rows': List<String>.generate(2000, (i) => 'row-$i-${'x' * 50}'),
    };

    test('clear during an in-flight write abandons memory and disk',
        () async {
      final store = CacheStore.forDirectory(tmpDir);

      // Write suspends at the encode await; clear() bumps the generation
      // before the persist can commit.
      final write = store.write('https://x/a', bigData, 300);
      await store.clear();
      await write;

      expect(await store.readStale('https://x/a'), isNull);
      expect(
        tmpDir.listSync().whereType<File>(),
        isEmpty,
        reason: 'no committed entry and no orphaned tmp file may survive',
      );
    });

    test('clear during an in-flight touch abandons the re-stamp', () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', {'value': 1}, 300, etag: '"v1"');

      // touch suspends reading the entry; clear() lands before it commits.
      final touch = store.touch('https://x/a', 300);
      await store.clear();
      await touch;

      expect(await store.readStale('https://x/a'), isNull);
      expect(tmpDir.listSync().whereType<File>(), isEmpty);
    });

    test('touch after a completed clear is a no-op', () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', {'value': 1}, 300);
      await store.clear();

      await store.touch('https://x/a', 300);

      expect(await store.readStale('https://x/a'), isNull);
      expect(tmpDir.listSync().whereType<File>(), isEmpty);
    });

    test('writes after clear belong to the new generation and persist',
        () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', 'old-session', 300);
      await store.clear();

      await store.write('https://x/b', 'new-session', 300);

      expect(await store.read('https://x/b'), 'new-session');
      expect(await store.readStale('https://x/a'), isNull);
    });
  });

  group('CacheStore ETag handling', () {
    test('touch re-stamps freshness without changing data or ETag', () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.write('https://x/a', {'value': 1}, 0, etag: '"v1"');
      await Future<void>.delayed(const Duration(milliseconds: 5));
      expect(await store.read('https://x/a'), isNull); // expired

      await store.touch('https://x/a', 300);

      final meta = await store.readWithMeta('https://x/a');
      expect(meta!.isFresh, isTrue);
      expect(meta.data, {'value': 1});
      expect(meta.etag, '"v1"');

      // The re-stamp is persisted, not just in memory.
      final second = CacheStore.forDirectory(tmpDir);
      expect((await second.readWithMeta('https://x/a'))!.isFresh, isTrue);
    });

    test('touch on a missing entry is a no-op', () async {
      final store = CacheStore.forDirectory(tmpDir);
      await store.touch('https://x/none', 300);
      expect(await store.readStale('https://x/none'), isNull);
    });

    test('pre-ETag on-disk entries read back with a null etag', () async {
      const url = 'https://x/legacy';
      final now = DateTime.now().millisecondsSinceEpoch;
      // Old format: no etag field.
      fileForUrl(url).writeAsStringSync(jsonEncode({
        'url': url,
        'data': {'value': 'legacy'},
        'cached_at': now,
        'expires_at': now + 300000,
      }));

      final store = CacheStore.forDirectory(tmpDir);
      final meta = await store.readWithMeta(url);
      expect(meta!.data, {'value': 'legacy'});
      expect(meta.isFresh, isTrue);
      expect(meta.etag, isNull);
    });
  });

  Map<String, dynamic> _makeEntry(dynamic data, int ttlSeconds) {
    final now = DateTime.now().millisecondsSinceEpoch;
    return {
      'url': 'https://example.com/test',
      'data': data,
      'cached_at': now,
      'expires_at': now + (ttlSeconds * 1000),
    };
  }

  File _fileIn(String name) => File('${tmpDir.path}/$name.json');

  group('Cache entry serialization', () {
    test('write and read back valid entry', () {
      final file = _fileIn('entry1');
      final entry = _makeEntry({'value': 42}, 300);
      file.writeAsStringSync(jsonEncode(entry));

      final decoded = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
      expect(decoded['data'], {'value': 42});
      expect(decoded['expires_at'], greaterThan(decoded['cached_at'] as int));
    });

    test('expired entry has expires_at in the past', () {
      final file = _fileIn('entry2');
      final now = DateTime.now().millisecondsSinceEpoch;
      final entry = {
        'url': 'https://example.com/old',
        'data': 'stale',
        'cached_at': now - 600000,
        'expires_at': now - 1000, // expired 1 second ago
      };
      file.writeAsStringSync(jsonEncode(entry));

      final decoded = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
      final expiresAt = decoded['expires_at'] as int;
      expect(expiresAt < now, isTrue);
      // Data is still readable (stale mode)
      expect(decoded['data'], 'stale');
    });

    test('non-expired entry has expires_at in the future', () {
      final file = _fileIn('entry3');
      final entry = _makeEntry('fresh', 3600);
      file.writeAsStringSync(jsonEncode(entry));

      final decoded = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
      final expiresAt = decoded['expires_at'] as int;
      final now = DateTime.now().millisecondsSinceEpoch;
      expect(expiresAt > now, isTrue);
    });
  });

  group('Cache eviction logic', () {
    test('deletes expired files, keeps valid ones', () {
      final now = DateTime.now().millisecondsSinceEpoch;

      // Expired entry
      final expiredFile = _fileIn('expired');
      expiredFile.writeAsStringSync(jsonEncode({
        'url': 'a',
        'data': 1,
        'cached_at': now - 600000,
        'expires_at': now - 1000,
      }));

      // Valid entry
      final validFile = _fileIn('valid');
      validFile.writeAsStringSync(jsonEncode({
        'url': 'b',
        'data': 2,
        'cached_at': now,
        'expires_at': now + 300000,
      }));

      // Simulate eviction
      for (final entity in tmpDir.listSync()) {
        if (entity is! File || !entity.path.endsWith('.json')) continue;
        try {
          final entry =
              jsonDecode(entity.readAsStringSync()) as Map<String, dynamic>;
          final expiresAt = entry['expires_at'] as int? ?? 0;
          if (now > expiresAt) {
            entity.deleteSync();
          }
        } catch (_) {
          entity.deleteSync();
        }
      }

      expect(expiredFile.existsSync(), isFalse);
      expect(validFile.existsSync(), isTrue);
    });

    test('clear removes all files', () {
      _fileIn('a').writeAsStringSync('{}');
      _fileIn('b').writeAsStringSync('{}');

      expect(tmpDir.listSync().length, 2);

      tmpDir.deleteSync(recursive: true);
      tmpDir.createSync(recursive: true);

      expect(tmpDir.listSync().length, 0);
    });
  });

  group('Cache TTL calculation', () {
    test('TTL of 300s sets expires_at 5 minutes ahead', () {
      final entry = _makeEntry('data', 300);
      final diff = (entry['expires_at'] as int) - (entry['cached_at'] as int);
      expect(diff, 300000); // 300 * 1000ms
    });

    test('TTL of 0 expires immediately', () {
      final entry = _makeEntry('data', 0);
      expect(entry['expires_at'], entry['cached_at']);
    });
  });
}
