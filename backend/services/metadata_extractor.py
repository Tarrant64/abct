"""
Universal NFT Metadata Extractor for Cardano

Handles flexible metadata extraction from multiple API sources:
- NFT CDN (primary)
- NMKR (secondary)
- Blockfrost/Koios (on-chain fallback)
- TapTools (pricing only)

Supports various metadata standards and field naming conventions.
"""

import logging
import re
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """
    Flexible metadata extraction for Cardano NFTs.

    Handles various metadata formats and naming conventions across different
    API providers and metadata standards (CIP25v1, CIP25v2, etc.)
    """

    # Field name variations for common metadata
    COLLECTION_NAME_FIELDS = [
        'collection',
        'collection_name',
        'collectionName',
        'project',
        'projectName',
        'project_name',
        'name',  # At policy level
        'title'
    ]

    NFT_NAME_FIELDS = [
        'name',
        'title',
        'nft_name',
        'assetName',
        'asset_name'
    ]

    DESCRIPTION_FIELDS = [
        'description',
        'desc',
        'projectDescription',
        'project_description'
    ]

    IMAGE_FIELDS = [
        'image',
        'displayImageUrl',
        'display_image_url',
        'ipfsLink',
        'ipfs_link',
        'coverImage',
        'cover_image'
    ]

    AUTHOR_FIELDS = [
        'author',
        'authors',
        'artist',
        'artists',
        'creator',
        'creators',
        'publisher'
    ]

    # Edition/rarity number patterns
    EDITION_PATTERNS = [
        r'#(\d+)',                          # #234
        r'(\d+)\s*of\s*(\d+)',              # 234 of 1000
        r'(\d+)\s*/\s*(\d+)',               # 234/1000
        r'edition[:\s]*(\d+)',              # edition: 234
        r'number[:\s]*(\d+)',               # number: 234
    ]

    def extract_collection_name(self, metadata: Dict, source: str = 'unknown') -> Optional[str]:
        """
        Extract collection name from metadata.

        Args:
            metadata: Raw metadata dict from API
            source: Source API name (for logging)

        Returns:
            Collection name or None
        """
        # Check for Book.io specific format (attributes.Book Title)
        # This must be checked FIRST before trying standard fields
        book_title = self._extract_book_title(metadata)
        if book_title:
            logger.debug(f"Found collection name in attributes['Book Title'] from {source}: {book_title}")
            return book_title

        # Try direct fields
        for field in self.COLLECTION_NAME_FIELDS:
            value = self._get_nested_value(metadata, field)
            if value and isinstance(value, str) and len(value.strip()) > 0:
                # For Book.io NFTs, the 'name' field has format "BookName #123"
                # Try to extract just the book name by removing edition suffix
                cleaned_value = self._remove_edition_suffix(value)
                if cleaned_value and cleaned_value != value:
                    logger.debug(f"Found collection name in '{field}' (cleaned from '{value}') from {source}: {cleaned_value}")
                    return cleaned_value.strip()

                logger.debug(f"Found collection name in '{field}' from {source}: {value}")
                return value.strip()

        # For on-chain metadata, check nested structures
        if 'onchain_metadata' in metadata:
            onchain = metadata['onchain_metadata']
            if isinstance(onchain, dict):
                # Check for Book Title in onchain attributes first
                book_title = self._extract_book_title(onchain)
                if book_title:
                    logger.debug(f"Found collection name in onchain_metadata.attributes['Book Title'] from {source}: {book_title}")
                    return book_title

                for field in self.COLLECTION_NAME_FIELDS:
                    value = self._get_nested_value(onchain, field)
                    if value and isinstance(value, str) and len(value.strip()) > 0:
                        # Try to remove edition suffix
                        cleaned_value = self._remove_edition_suffix(value)
                        if cleaned_value and cleaned_value != value:
                            logger.debug(f"Found collection name in onchain_metadata.{field} (cleaned) from {source}: {cleaned_value}")
                            return cleaned_value.strip()

                        logger.debug(f"Found collection name in onchain_metadata.{field} from {source}: {value}")
                        return value.strip()

        logger.debug(f"No collection name found in metadata from {source}")
        return None

    def extract_nft_name(self, metadata: Dict, source: str = 'unknown') -> Optional[str]:
        """
        Extract individual NFT name from metadata.

        Args:
            metadata: Raw metadata dict from API
            source: Source API name

        Returns:
            NFT name or None
        """
        # IMPORTANT: Check onchain_metadata FIRST (for Blockfrost responses)
        # This prevents picking up hex-encoded 'asset_name' from top level
        if 'onchain_metadata' in metadata and isinstance(metadata['onchain_metadata'], dict):
            for field in self.NFT_NAME_FIELDS:
                value = self._get_nested_value(metadata['onchain_metadata'], field)
                if value and isinstance(value, str) and len(value.strip()) > 0:
                    # Skip if it looks like hex-encoded data
                    if not self._is_hex_encoded(value):
                        return value.strip()

        # Then try top-level fields (for NFTCDN, NMKR responses)
        for field in self.NFT_NAME_FIELDS:
            value = self._get_nested_value(metadata, field)
            if value and isinstance(value, str) and len(value.strip()) > 0:
                # Skip if it looks like hex-encoded data
                if not self._is_hex_encoded(value):
                    return value.strip()

        return None

    def extract_description(self, metadata: Dict) -> Optional[str]:
        """
        Extract description from metadata.

        Args:
            metadata: Raw metadata dict

        Returns:
            Description string or None
        """
        for field in self.DESCRIPTION_FIELDS:
            value = self._get_nested_value(metadata, field)

            # Handle string descriptions
            if value and isinstance(value, str):
                return value.strip()

            # Handle array descriptions (join with spaces)
            if value and isinstance(value, list):
                parts = [str(part).strip() for part in value if part]
                return ' '.join(parts)

        # Try onchain_metadata
        if 'onchain_metadata' in metadata and isinstance(metadata['onchain_metadata'], dict):
            for field in self.DESCRIPTION_FIELDS:
                value = self._get_nested_value(metadata['onchain_metadata'], field)
                if value:
                    if isinstance(value, str):
                        return value.strip()
                    if isinstance(value, list):
                        parts = [str(part).strip() for part in value if part]
                        return ' '.join(parts)

        return None

    def extract_image_url(self, metadata: Dict) -> Optional[str]:
        """
        Extract image URL from metadata, checking multiple field variations.
        Prioritizes 'files' array over direct 'image' field for better resolution.

        Args:
            metadata: Raw metadata dict

        Returns:
            Image URL (with IPFS converted to gateway) or None
        """
        # PRIORITY 1: Check files array first (usually higher resolution for Cardano NFTs)
        files = self._get_nested_value(metadata, 'files')
        if files and isinstance(files, list) and len(files) > 0:
            first_file = files[0]
            if isinstance(first_file, dict):
                src = first_file.get('src') or first_file.get('url') or first_file.get('ipfs')
                if src:
                    return self._normalize_ipfs_url(src)

        # PRIORITY 2: Check onchain_metadata files (Cardano-specific)
        if 'onchain_metadata' in metadata and isinstance(metadata['onchain_metadata'], dict):
            onchain = metadata['onchain_metadata']

            # Try files in onchain first
            files = onchain.get('files')
            if files and isinstance(files, list) and len(files) > 0:
                first_file = files[0]
                if isinstance(first_file, dict):
                    src = first_file.get('src') or first_file.get('url') or first_file.get('ipfs')
                    if src:
                        return self._normalize_ipfs_url(src)

            # Then try image fields in onchain
            for field in self.IMAGE_FIELDS:
                value = self._get_nested_value(onchain, field)
                if value and isinstance(value, str):
                    return self._normalize_ipfs_url(value.strip())

        # PRIORITY 3: Check direct image fields (fallback)
        for field in self.IMAGE_FIELDS:
            value = self._get_nested_value(metadata, field)
            if value and isinstance(value, str) and len(value.strip()) > 0:
                return self._normalize_ipfs_url(value.strip())

        return None

    def extract_edition_info(self, metadata: Dict) -> Optional[Dict[str, Any]]:
        """
        Extract edition/rarity information from metadata.

        Handles formats like:
        - #234
        - 234 of 1000
        - 234/1000
        - edition: 234
        - id: "640" (Book.io format)
        - attributes: [{"trait_type": "Edition", "value": "234"}]

        Args:
            metadata: Raw metadata dict

        Returns:
            Dict with edition_number, total_supply, edition_text or None
        """
        # Check direct edition fields (including 'id' for Book.io NFTs)
        for field in ['edition', 'number', '#', 'serialNumber', 'serial_number', 'id']:
            value = self._get_nested_value(metadata, field)
            if value:
                # Try to parse edition info
                edition_info = self._parse_edition_value(value)
                if edition_info:
                    return edition_info

        # Check attributes
        attributes = self._get_nested_value(metadata, 'attributes')
        if attributes and isinstance(attributes, list):
            for attr in attributes:
                if isinstance(attr, dict):
                    trait_type = attr.get('trait_type', '').lower()
                    if any(keyword in trait_type for keyword in ['edition', 'number', '#', 'serial', 'rarity']):
                        value = attr.get('value')
                        if value:
                            edition_info = self._parse_edition_value(value)
                            if edition_info:
                                return edition_info

        # Check onchain_metadata
        if 'onchain_metadata' in metadata and isinstance(metadata['onchain_metadata'], dict):
            onchain = metadata['onchain_metadata']

            # Try direct fields in onchain
            for field in ['edition', 'number', '#', 'serialNumber']:
                value = self._get_nested_value(onchain, field)
                if value:
                    edition_info = self._parse_edition_value(value)
                    if edition_info:
                        return edition_info

            # Try attributes in onchain
            attributes = onchain.get('attributes')
            if attributes and isinstance(attributes, list):
                for attr in attributes:
                    if isinstance(attr, dict):
                        trait_type = attr.get('trait_type', '').lower()
                        if any(keyword in trait_type for keyword in ['edition', 'number', '#', 'serial']):
                            value = attr.get('value')
                            if value:
                                edition_info = self._parse_edition_value(value)
                                if edition_info:
                                    return edition_info

        # Check NFT name for edition info
        nft_name = self.extract_nft_name(metadata)
        if nft_name:
            edition_info = self._parse_edition_value(nft_name)
            if edition_info:
                return edition_info

        return None

    def extract_attributes(self, metadata: Dict) -> List[Dict[str, Any]]:
        """
        Extract attributes/traits from metadata.

        Args:
            metadata: Raw metadata dict

        Returns:
            List of attribute dicts with trait_type and value
        """
        attributes = []

        # Check direct attributes field
        attrs = self._get_nested_value(metadata, 'attributes')
        if attrs:
            if isinstance(attrs, list):
                # Standard array format
                for attr in attrs:
                    if isinstance(attr, dict):
                        attributes.append(self._normalize_attribute(attr))
                    elif isinstance(attr, str):
                        # Some APIs return attributes as strings
                        attributes.append({'trait_type': 'Attribute', 'value': attr})
            elif isinstance(attrs, dict):
                # Book.io format: attributes is a dict like {"Book Title": "Beowulf", "Variation": "..."}
                for key, value in attrs.items():
                    attributes.append({
                        'trait_type': str(key),
                        'value': str(value)
                    })

        # Check onchain_metadata.attributes
        if 'onchain_metadata' in metadata and isinstance(metadata['onchain_metadata'], dict):
            onchain_attrs = metadata['onchain_metadata'].get('attributes')
            if onchain_attrs:
                if isinstance(onchain_attrs, list):
                    # Standard array format
                    for attr in onchain_attrs:
                        if isinstance(attr, dict):
                            attributes.append(self._normalize_attribute(attr))
                elif isinstance(onchain_attrs, dict):
                    # Book.io format in onchain_metadata
                    for key, value in onchain_attrs.items():
                        attributes.append({
                            'trait_type': str(key),
                            'value': str(value)
                        })

        # Check traits (alternative naming)
        traits = self._get_nested_value(metadata, 'traits')
        if traits and isinstance(traits, list):
            for trait in traits:
                if isinstance(trait, dict):
                    attributes.append(self._normalize_attribute(trait))

        return attributes

    def extract_creator_info(self, metadata: Dict) -> Optional[str]:
        """
        Extract creator/author information.

        Args:
            metadata: Raw metadata dict

        Returns:
            Creator name/info or None
        """
        for field in self.AUTHOR_FIELDS:
            value = self._get_nested_value(metadata, field)

            # Handle string
            if value and isinstance(value, str):
                return value.strip()

            # Handle array (join with commas)
            if value and isinstance(value, list):
                names = [str(name).strip() for name in value if name]
                if names:
                    return ', '.join(names)

        # Try onchain_metadata
        if 'onchain_metadata' in metadata and isinstance(metadata['onchain_metadata'], dict):
            for field in self.AUTHOR_FIELDS:
                value = self._get_nested_value(metadata['onchain_metadata'], field)
                if value:
                    if isinstance(value, str):
                        return value.strip()
                    if isinstance(value, list):
                        names = [str(name).strip() for name in value if name]
                        if names:
                            return ', '.join(names)

        return None

    def extract_unified_metadata(self, metadata: Dict, source: str = 'unknown') -> Dict[str, Any]:
        """
        Extract all metadata into a unified format.

        Args:
            metadata: Raw metadata dict from any API
            source: Source API name (nftcdn, nmkr, blockfrost, etc.)

        Returns:
            Unified metadata dict with standardized fields
        """
        unified = {
            'source': source,
            'extracted_at': datetime.now().isoformat(),
            'collection_name': self.extract_collection_name(metadata, source),
            'nft_name': self.extract_nft_name(metadata, source),
            'description': self.extract_description(metadata),
            'image_url': self.extract_image_url(metadata),
            'edition_info': self.extract_edition_info(metadata),
            'attributes': self.extract_attributes(metadata),
            'creator': self.extract_creator_info(metadata),
            'raw_metadata': metadata  # Keep raw for debugging
        }

        logger.debug(f"Extracted unified metadata from {source}: collection={unified['collection_name']}, nft={unified['nft_name']}, attributes={len(unified['attributes'])}")

        return unified

    # Helper methods

    def _get_nested_value(self, data: Dict, key: str) -> Any:
        """
        Get value from dict, checking both direct key and nested 'metadata.key'.

        Args:
            data: Dict to search
            key: Key name

        Returns:
            Value or None
        """
        # Direct key
        if key in data:
            return data[key]

        # Nested in 'metadata' sub-dict
        if 'metadata' in data and isinstance(data['metadata'], dict):
            if key in data['metadata']:
                return data['metadata'][key]

        return None

    def _normalize_ipfs_url(self, url: str) -> str:
        """
        Convert IPFS protocol URLs to gateway URLs.

        Args:
            url: Original URL (may be ipfs://)

        Returns:
            HTTP gateway URL
        """
        if url.startswith('ipfs://'):
            return url.replace('ipfs://', 'https://ipfs.io/ipfs/')
        return url

    def _parse_edition_value(self, value: Any) -> Optional[Dict[str, Any]]:
        """
        Parse edition information from various formats.

        Args:
            value: Edition value (string, int, or dict)

        Returns:
            Dict with edition_number, total_supply, edition_text or None
        """
        if not value:
            return None

        value_str = str(value)

        # Try patterns
        for pattern in self.EDITION_PATTERNS:
            match = re.search(pattern, value_str, re.IGNORECASE)
            if match:
                groups = match.groups()

                if len(groups) == 1:
                    # Single number (e.g., #234, edition: 234)
                    try:
                        edition_num = int(groups[0])
                        return {
                            'edition_number': edition_num,
                            'total_supply': None,
                            'edition_text': f"#{edition_num}"
                        }
                    except ValueError:
                        pass

                elif len(groups) == 2:
                    # Number and total (e.g., 234 of 1000)
                    try:
                        edition_num = int(groups[0])
                        total = int(groups[1])
                        return {
                            'edition_number': edition_num,
                            'total_supply': total,
                            'edition_text': f"#{edition_num} of {total}"
                        }
                    except ValueError:
                        pass

        # If it's just a plain number
        try:
            edition_num = int(value_str)
            return {
                'edition_number': edition_num,
                'total_supply': None,
                'edition_text': f"#{edition_num}"
            }
        except ValueError:
            pass

        return None

    def _normalize_attribute(self, attr: Dict) -> Dict[str, Any]:
        """
        Normalize attribute dict to standard format.

        Args:
            attr: Raw attribute dict

        Returns:
            Normalized dict with trait_type and value
        """
        # Try various field name combinations
        trait_type = (
            attr.get('trait_type') or
            attr.get('traitType') or
            attr.get('name') or
            attr.get('key') or
            'Attribute'
        )

        value = (
            attr.get('value') or
            attr.get('val') or
            attr.get('trait_value') or
            ''
        )

        return {
            'trait_type': str(trait_type),
            'value': str(value)
        }

    def _extract_book_title(self, metadata: Dict) -> Optional[str]:
        """
        Extract book title from Book.io specific attributes format.

        Book.io NFTs store the collection name in attributes['Book Title']
        where attributes is a dict (not array).

        Args:
            metadata: Raw metadata dict

        Returns:
            Book title or None
        """
        # Check direct attributes
        attributes = metadata.get('attributes')
        if attributes and isinstance(attributes, dict):
            book_title = attributes.get('Book Title') or attributes.get('book_title')
            if book_title and isinstance(book_title, str):
                return book_title.strip()

        # Check onchain_metadata.attributes
        if 'onchain_metadata' in metadata:
            onchain = metadata['onchain_metadata']
            if isinstance(onchain, dict):
                attributes = onchain.get('attributes')
                if attributes and isinstance(attributes, dict):
                    book_title = attributes.get('Book Title') or attributes.get('book_title')
                    if book_title and isinstance(book_title, str):
                        return book_title.strip()

        return None

    def _remove_edition_suffix(self, name: str) -> Optional[str]:
        """
        Remove edition suffix from NFT name to extract collection name.

        Examples:
        - "Beowulf #640" → "Beowulf"
        - "Cool Apes #123" → "Cool Apes"
        - "Art Piece (1/100)" → "Art Piece"

        Args:
            name: NFT name that may contain edition suffix

        Returns:
            Cleaned collection name or None if no pattern matched
        """
        if not name or not isinstance(name, str):
            return None

        # Patterns to match and remove
        patterns = [
            r'\s*#\d+$',              # "Name #123"
            r'\s*\(\d+/\d+\)$',       # "Name (1/100)"
            r'\s*\[\d+/\d+\]$',       # "Name [1/100]"
            r'\s*\d+/\d+$',           # "Name 1/100"
            r'\s*-\s*\d+$',           # "Name - 123"
        ]

        for pattern in patterns:
            cleaned = re.sub(pattern, '', name).strip()
            if cleaned and cleaned != name:
                return cleaned

        # If no pattern matched, return None (not the original name)
        # This prevents false positives where we'd return a name that
        # doesn't actually have an edition suffix
        return None

    def _is_hex_encoded(self, value: str) -> bool:
        """
        Check if a string appears to be hex-encoded data.

        Args:
            value: String to check

        Returns:
            True if it looks like hex data, False otherwise
        """
        if not value or not isinstance(value, str):
            return False

        # Must be even length (hex pairs)
        if len(value) % 2 != 0:
            return False

        # Must be all hex characters
        if not all(c in '0123456789abcdefABCDEF' for c in value):
            return False

        # If it's longer than 20 chars and all hex, likely encoded
        # (short hex strings might be legitimate IDs)
        return len(value) > 20


# Global instance
metadata_extractor = MetadataExtractor()
