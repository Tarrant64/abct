"""
NFT Image Caching Service

Handles fetching, processing, and caching of NFT images.
Supports all chains: Cardano, Ethereum, Solana, Polygon, Base.
"""

import asyncio
import httpx
import logging
from io import BytesIO
from typing import Optional, List, Tuple
from datetime import datetime

from config import (
    NFT_IMAGE_DB_PATH,
    NFT_IMAGE_MAX_SIZE_MB,
    NFT_IMAGE_THUMBNAIL_SIZE,
    IPFS_GATEWAYS
)
from nft_image_database import (
    init_nft_image_db,
    get_image_cache_config,
    update_image_cache_config,
    is_image_cache_enabled,
    save_nft_image,
    get_nft_image,
    get_nft_image_data,
    get_nft_thumbnail_data,
    get_pending_images,
    update_image_status,
    get_image_cache_stats,
    clear_image_cache,
    has_cached_image
)

logger = logging.getLogger(__name__)

# Try to import Pillow for thumbnail generation
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not installed - thumbnail generation disabled")


class NFTImageService:
    """Service for caching and serving NFT images."""

    def __init__(self):
        self._initialized = False
        self._http_client: Optional[httpx.AsyncClient] = None
        self.max_size_bytes = NFT_IMAGE_MAX_SIZE_MB * 1024 * 1024
        self.thumbnail_size = NFT_IMAGE_THUMBNAIL_SIZE

    async def initialize(self):
        """Initialize the service and database."""
        if not self._initialized:
            await init_nft_image_db()
            self._initialized = True
            logger.info("NFT Image Service initialized")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with optimized timeouts."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,   # Connection establishment
                    read=90.0,      # Read timeout (allow slow IPFS)
                    write=10.0,     # Request upload
                    pool=10.0       # Connection pool wait
                ),
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=100,        # Increase connection pool
                    max_keepalive_connections=20
                ),
                headers={
                    'User-Agent': 'ABCT-Portfolio-Tracker/1.0',
                    'Accept': 'image/*'
                }
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    # ========================================================================
    # Configuration
    # ========================================================================

    async def is_enabled(self) -> bool:
        """Check if image caching is enabled."""
        await self.initialize()
        return await is_image_cache_enabled()

    async def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable image caching."""
        await self.initialize()
        return await update_image_cache_config('enabled', enabled)

    async def get_config(self) -> dict:
        """Get full configuration."""
        await self.initialize()
        config = await get_image_cache_config()
        stats = await get_image_cache_stats()

        return {
            'enabled': config.get('enabled', False),
            'database_path': str(NFT_IMAGE_DB_PATH),
            'database_exists': NFT_IMAGE_DB_PATH.exists(),
            'pillow_available': PILLOW_AVAILABLE,
            'settings': {
                'max_image_size_bytes': config.get('max_image_size_bytes', self.max_size_bytes),
                'generate_thumbnails': config.get('generate_thumbnails', True),
                'thumbnail_size': config.get('thumbnail_size', self.thumbnail_size),
                'auto_fetch_on_nft_load': config.get('auto_fetch_on_nft_load', False),
                'enabled_chains': config.get('enabled_chains', ['cardano', 'ethereum', 'solana', 'polygon', 'base'])
            },
            'stats': stats
        }

    async def update_config(self, updates: dict) -> dict:
        """Update configuration settings."""
        await self.initialize()
        for key, value in updates.items():
            await update_image_cache_config(key, value)
        return await self.get_config()

    # ========================================================================
    # URL Processing
    # ========================================================================

    def _normalize_image_url(self, url: str) -> str:
        """Convert IPFS URLs to HTTP gateway URLs."""
        if not url:
            return url

        # Handle ipfs:// protocol
        if url.startswith('ipfs://'):
            ipfs_hash = url[7:]  # Remove 'ipfs://'
            return f"{IPFS_GATEWAYS[0]}{ipfs_hash}"

        # Handle Qm... IPFS hashes without protocol
        if url.startswith('Qm') and len(url) == 46:
            return f"{IPFS_GATEWAYS[0]}{url}"

        return url

    def _detect_image_format(self, content_type: str, data: bytes) -> str:
        """Detect image format from content-type or magic bytes."""
        # Check content-type header
        if content_type:
            ct = content_type.lower()
            if 'jpeg' in ct or 'jpg' in ct:
                return 'jpeg'
            elif 'png' in ct:
                return 'png'
            elif 'gif' in ct:
                return 'gif'
            elif 'webp' in ct:
                return 'webp'
            elif 'svg' in ct:
                return 'svg'

        # Check magic bytes
        if data:
            if data[:3] == b'\xff\xd8\xff':
                return 'jpeg'
            elif data[:8] == b'\x89PNG\r\n\x1a\n':
                return 'png'
            elif data[:6] in (b'GIF87a', b'GIF89a'):
                return 'gif'
            elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
                return 'webp'
            elif data[:5] == b'<?xml' or data[:4] == b'<svg':
                return 'svg'

        return 'unknown'

    # ========================================================================
    # Image Fetching
    # ========================================================================

    async def fetch_image(
        self,
        url: str,
        max_retries: int = 3
    ) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        Fetch an image from URL with retry logic and compression.

        Args:
            url: Image URL to fetch
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            Tuple of (image_data, image_format, error_message)
        """
        if not url:
            return None, None, "No URL provided"

        normalized_url = self._normalize_image_url(url)
        client = await self._get_client()

        # Build gateway fallback list for IPFS URLs
        urls_to_try = [normalized_url]
        if 'ipfs' in normalized_url.lower() or '/ipfs/' in normalized_url:
            for gateway in IPFS_GATEWAYS:
                if gateway in normalized_url:
                    ipfs_hash = normalized_url.split(gateway)[-1]
                    for alt_gateway in IPFS_GATEWAYS:
                        if alt_gateway != gateway:
                            urls_to_try.append(f"{alt_gateway}{ipfs_hash}")
                    break

        last_error = None

        # Retry loop
        for attempt in range(max_retries):
            for gateway_idx, try_url in enumerate(urls_to_try):
                try:
                    # Add delay on retries
                    if attempt > 0:
                        delay = 2 ** attempt  # Exponential: 2s, 4s, 8s
                        await asyncio.sleep(delay)
                        logger.debug(f"Retry {attempt + 1}/{max_retries} for {try_url[:50]}...")

                    response = await client.get(try_url)
                    response.raise_for_status()

                    data = response.content

                    # Size check BEFORE compression
                    if len(data) > self.max_size_bytes:
                        logger.info(f"Large image ({len(data)} bytes), attempting compression...")

                        content_type = response.headers.get('content-type', '')
                        image_format = self._detect_image_format(content_type, data)

                        if image_format == 'unknown':
                            last_error = "Unknown image format for large file"
                            continue

                        # Try compression
                        compressed_data, new_format = self._compress_image(data, image_format)

                        if len(compressed_data) <= self.max_size_bytes:
                            logger.info(f"✓ Compression successful: {len(data)} → {len(compressed_data)} bytes")
                            return compressed_data, new_format, None
                        else:
                            last_error = f"Image too large even after compression: {len(compressed_data)} bytes (max: {self.max_size_bytes})"
                            continue

                    # Normal size - detect format
                    content_type = response.headers.get('content-type', '')
                    image_format = self._detect_image_format(content_type, data)

                    if image_format == 'unknown':
                        last_error = "Unknown image format"
                        continue

                    # Apply compression to all images for consistency and space savings
                    compressed_data, final_format = self._compress_image(data, image_format)

                    return compressed_data, final_format, None

                except httpx.TimeoutException as e:
                    last_error = f"Timeout on {try_url[:50]}... (attempt {attempt + 1})"
                    logger.debug(last_error)
                    continue  # Try next gateway

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        # Rate limited - wait longer and try next gateway
                        last_error = f"Rate limited by {try_url[:30]}... (attempt {attempt + 1})"
                        logger.debug(last_error)
                        await asyncio.sleep(5 * (attempt + 1))
                        continue
                    else:
                        last_error = f"HTTP {e.response.status_code} for {try_url[:50]}... (attempt {attempt + 1})"
                        logger.debug(last_error)
                        continue

                except Exception as e:
                    last_error = f"Error fetching {try_url[:50]}...: {str(e)} (attempt {attempt + 1})"
                    logger.debug(last_error)
                    continue

        return None, None, f"All retries exhausted: {last_error}"

    def _generate_thumbnail(self, image_data: bytes, image_format: str) -> Optional[bytes]:
        """Generate a thumbnail from image data."""
        if not PILLOW_AVAILABLE:
            return None

        if image_format == 'svg':
            # SVG can't be thumbnailed with Pillow
            return None

        try:
            img = Image.open(BytesIO(image_data))

            # Convert to RGB if necessary (for JPEG output)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # Create thumbnail (maintains aspect ratio)
            img.thumbnail((self.thumbnail_size, self.thumbnail_size), Image.Resampling.LANCZOS)

            # Save to bytes
            output = BytesIO()
            img.save(output, format='JPEG', quality=85, optimize=True)
            return output.getvalue()

        except Exception as e:
            logger.warning(f"Failed to generate thumbnail: {e}")
            return None

    def _get_image_dimensions(self, image_data: bytes, image_format: str) -> Tuple[Optional[int], Optional[int]]:
        """Get image dimensions."""
        if not PILLOW_AVAILABLE or image_format == 'svg':
            return None, None

        try:
            img = Image.open(BytesIO(image_data))
            return img.width, img.height
        except Exception:
            return None, None

    def _compress_image(self, image_data: bytes, image_format: str) -> Tuple[bytes, str]:
        """
        Compress image to WebP format with quality optimization.

        Returns:
            Tuple of (compressed_data, new_format)
        """
        if not PILLOW_AVAILABLE:
            return image_data, image_format

        # Skip compression for SVG (already compressed)
        if image_format == 'svg':
            return image_data, 'svg'

        try:
            img = Image.open(BytesIO(image_data))

            # Preserve transparency for RGBA images
            if img.mode in ('RGBA', 'LA', 'P'):
                if 'transparency' in img.info or img.mode == 'RGBA':
                    # WebP supports transparency
                    output = BytesIO()
                    img.save(output, format='WEBP', quality=85, method=6, lossless=False)
                    compressed = output.getvalue()

                    compression_ratio = len(compressed) / len(image_data)
                    logger.debug(f"Compressed RGBA image: {len(image_data)} → {len(compressed)} bytes ({compression_ratio:.1%})")

                    return compressed, 'webp'

            # Convert to RGB for lossy WebP
            img = img.convert('RGB')

            # Dynamic quality based on original size
            original_size_mb = len(image_data) / (1024 * 1024)
            if original_size_mb > 5:
                quality = 75  # More aggressive for large images
            elif original_size_mb > 2:
                quality = 80
            else:
                quality = 85

            output = BytesIO()
            img.save(output, format='WEBP', quality=quality, method=6)
            compressed = output.getvalue()

            compression_ratio = len(compressed) / len(image_data)
            logger.info(f"Compressed image: {len(image_data)} → {len(compressed)} bytes ({compression_ratio:.1%}, quality={quality})")

            return compressed, 'webp'

        except Exception as e:
            logger.warning(f"Failed to compress image: {e}")
            return image_data, image_format

    # ========================================================================
    # Image Caching Operations
    # ========================================================================

    async def cache_image(
        self,
        asset_id: str,
        blockchain: str,
        image_url: str,
        force: bool = False
    ) -> dict:
        """
        Fetch and cache an NFT image.

        Args:
            asset_id: Unique identifier for the NFT
            blockchain: Chain name (cardano, ethereum, etc.)
            image_url: URL to fetch the image from
            force: Force re-fetch even if already cached

        Returns:
            Dict with status and details
        """
        await self.initialize()

        # Check if already cached (unless forcing)
        if not force:
            existing = await get_nft_image(asset_id, blockchain)
            if existing and existing.get('fetch_status') == 'fetched':
                return {
                    'status': 'already_cached',
                    'asset_id': asset_id,
                    'blockchain': blockchain,
                    'size_bytes': existing.get('image_size')
                }

        # Register the image as pending
        await save_nft_image(
            asset_id=asset_id,
            blockchain=blockchain,
            image_url=image_url,
            fetch_status='pending'
        )

        # Fetch the image
        image_data, image_format, error = await self.fetch_image(image_url)

        if error:
            await save_nft_image(
                asset_id=asset_id,
                blockchain=blockchain,
                image_url=image_url,
                fetch_status='failed',
                error_message=error
            )
            return {
                'status': 'failed',
                'asset_id': asset_id,
                'blockchain': blockchain,
                'error': error
            }

        # Get dimensions
        width, height = self._get_image_dimensions(image_data, image_format)

        # Generate thumbnail
        config = await get_image_cache_config()
        thumbnail_data = None
        if config.get('generate_thumbnails', True):
            thumbnail_data = self._generate_thumbnail(image_data, image_format)

        # Save to database
        await save_nft_image(
            asset_id=asset_id,
            blockchain=blockchain,
            image_url=image_url,
            image_data=image_data,
            image_format=image_format,
            width=width,
            height=height,
            thumbnail_data=thumbnail_data,
            fetch_status='fetched'
        )

        return {
            'status': 'fetched',
            'asset_id': asset_id,
            'blockchain': blockchain,
            'format': image_format,
            'size_bytes': len(image_data),
            'dimensions': f"{width}x{height}" if width and height else None,
            'has_thumbnail': thumbnail_data is not None
        }

    async def batch_cache_images(
        self,
        nfts: List[dict],
        blockchain: str,
        max_concurrent: int = 5
    ) -> dict:
        """
        Fetch and cache images for multiple NFTs.

        Args:
            nfts: List of NFT dicts with 'asset_id' and 'image_url' keys
            blockchain: Chain name
            max_concurrent: Maximum concurrent fetches

        Returns:
            Summary of results
        """
        await self.initialize()

        semaphore = asyncio.Semaphore(max_concurrent)
        results = {'fetched': 0, 'failed': 0, 'skipped': 0, 'errors': []}

        async def fetch_one(nft):
            async with semaphore:
                asset_id = nft.get('asset_id') or nft.get('token_id') or nft.get('unit')
                image_url = nft.get('image_url') or nft.get('image')

                if not asset_id or not image_url:
                    results['skipped'] += 1
                    return

                result = await self.cache_image(asset_id, blockchain, image_url)

                if result['status'] == 'fetched':
                    results['fetched'] += 1
                elif result['status'] == 'failed':
                    results['failed'] += 1
                    results['errors'].append({
                        'asset_id': asset_id,
                        'error': result.get('error')
                    })
                else:
                    results['skipped'] += 1

        await asyncio.gather(*[fetch_one(nft) for nft in nfts])

        return results

    # ========================================================================
    # Image Retrieval
    # ========================================================================

    async def get_image(self, asset_id: str, blockchain: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Get cached image data."""
        await self.initialize()
        return await get_nft_image_data(asset_id, blockchain)

    async def get_thumbnail(self, asset_id: str, blockchain: str) -> Tuple[Optional[bytes], Optional[str]]:
        """Get cached thumbnail data."""
        await self.initialize()
        return await get_nft_thumbnail_data(asset_id, blockchain)

    async def has_image(self, asset_id: str, blockchain: str) -> bool:
        """Check if an image is cached."""
        await self.initialize()
        return await has_cached_image(asset_id, blockchain)

    # ========================================================================
    # Cache Management
    # ========================================================================

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        await self.initialize()
        return await get_image_cache_stats()

    async def clear_cache(self, blockchain: str = None) -> int:
        """Clear cached images."""
        await self.initialize()
        deleted = await clear_image_cache(blockchain)
        logger.info(f"Cleared {deleted} cached images" + (f" for {blockchain}" if blockchain else ""))
        return deleted

    async def get_pending(self, blockchain: str = None, limit: int = 50) -> list:
        """Get images that are pending fetch."""
        await self.initialize()
        return await get_pending_images(blockchain, limit)

    async def process_pending(self, blockchain: str = None, limit: int = 50, max_concurrent: int = 5) -> dict:
        """Process pending images in the queue."""
        await self.initialize()

        pending = await get_pending_images(blockchain, limit)
        if not pending:
            return {'processed': 0, 'message': 'No pending images'}

        results = {'fetched': 0, 'failed': 0}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_one(item):
            async with semaphore:
                result = await self.cache_image(
                    item['asset_id'],
                    item['blockchain'],
                    item['image_url']
                )
                if result['status'] == 'fetched':
                    results['fetched'] += 1
                else:
                    results['failed'] += 1

        await asyncio.gather(*[process_one(item) for item in pending])

        return {
            'processed': len(pending),
            'fetched': results['fetched'],
            'failed': results['failed']
        }


# Singleton instance
nft_image_service = NFTImageService()
