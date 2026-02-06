import re
from typing import Optional, Tuple, List, Dict

def detect_blockchain(address: str) -> Optional[str]:
    """
    Detect the blockchain based on address format.

    Returns:
        'cardano', 'bitcoin', 'ethereum', 'polygon', 'base', 'solana', 'algorand', or None if unknown
    """
    address = address.strip()

    # Check for explicit prefix
    if ':' in address:
        prefix, addr = address.split(':', 1)
        prefix = prefix.lower()
        if prefix in ('cardano', 'bitcoin', 'ethereum', 'eth', 'polygon', 'matic', 'base', 'solana', 'sol', 'algorand', 'algo'):
            if prefix == 'eth':
                return 'ethereum'
            elif prefix == 'sol':
                return 'solana'
            elif prefix == 'matic':
                return 'polygon'
            elif prefix == 'algo':
                return 'algorand'
            return prefix
        return None

    # Cardano mainnet addresses start with addr1
    if address.startswith('addr1'):
        return 'cardano'

    # Cardano stake addresses start with stake1
    if address.startswith('stake1'):
        return 'cardano'

    # Algorand addresses - 58 characters, base32 (uppercase A-Z and 2-7)
    if len(address) == 58:
        base32_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')
        if all(c in base32_chars for c in address.upper()):
            return 'algorand'

    # Ethereum addresses - start with 0x and are 42 characters
    if address.lower().startswith('0x') and len(address) == 42:
        try:
            # Verify it's valid hex
            int(address[2:], 16)
            return 'ethereum'
        except ValueError:
            pass

    # Solana addresses - base58, 32-44 chars, no 0/O/I/l
    # Must check before Bitcoin since some formats could overlap
    if len(address) >= 32 and len(address) <= 44:
        # Exclude Bitcoin addresses
        if not address.startswith(('1', '3', 'bc1')):
            base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
            if all(c in base58_chars for c in address):
                return 'solana'

    # Bitcoin addresses
    # Legacy (P2PKH) - starts with 1
    if re.match(r'^1[a-km-zA-HJ-NP-Z1-9]{25,34}$', address):
        return 'bitcoin'

    # P2SH - starts with 3
    if re.match(r'^3[a-km-zA-HJ-NP-Z1-9]{25,34}$', address):
        return 'bitcoin'

    # Bech32 (SegWit) - starts with bc1
    if re.match(r'^bc1[a-zA-HJ-NP-Z0-9]{25,90}$', address):
        return 'bitcoin'

    # Bitcoin extended public keys (xpub/ypub/zpub)
    if is_bitcoin_xpub(address):
        return 'bitcoin'

    return None


def is_bitcoin_xpub(key: str) -> bool:
    """
    Check if a string is a Bitcoin extended public key.

    Supports:
        - xpub: BIP44 Legacy (P2PKH addresses starting with 1)
        - ypub: BIP49 Nested SegWit (P2SH-P2WPKH addresses starting with 3)
        - zpub: BIP84 Native SegWit (P2WPKH addresses starting with bc1)
        - tpub/upub/vpub: Testnet variants
    """
    if not key:
        return False

    # Check prefix and approximate length (xpubs are ~111 characters)
    valid_prefixes = ('xpub', 'ypub', 'zpub', 'tpub', 'upub', 'vpub')
    if not key.startswith(valid_prefixes):
        return False

    # Check length (typically 111-112 characters for mainnet)
    if len(key) < 100 or len(key) > 120:
        return False

    # Verify base58 encoding (no 0, O, I, l characters)
    base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
    if not all(c in base58_chars for c in key):
        return False

    return True


def get_xpub_type(xpub: str) -> Optional[str]:
    """
    Get the type of extended public key.

    Returns:
        'legacy' (xpub), 'nested_segwit' (ypub), 'native_segwit' (zpub),
        or testnet variants, or None if invalid
    """
    if not is_bitcoin_xpub(xpub):
        return None

    type_map = {
        'xpub': 'legacy',
        'ypub': 'nested_segwit',
        'zpub': 'native_segwit',
        'tpub': 'testnet_legacy',
        'upub': 'testnet_nested_segwit',
        'vpub': 'testnet_native_segwit'
    }

    for prefix, xpub_type in type_map.items():
        if xpub.startswith(prefix):
            return xpub_type

    return None

def parse_address(line: str) -> Optional[Tuple[str, str]]:
    """
    Parse a line from the wallets file.

    Returns:
        Tuple of (blockchain, address) or None if invalid
    """
    line = line.strip()

    # Skip empty lines and comments
    if not line or line.startswith('#'):
        return None

    # Check for explicit prefix
    if ':' in line:
        parts = line.split(':', 1)
        blockchain = parts[0].lower()
        address = parts[1].strip()

        # Normalize short names to full names
        if blockchain == 'eth':
            blockchain = 'ethereum'
        elif blockchain == 'sol':
            blockchain = 'solana'
        elif blockchain == 'matic':
            blockchain = 'polygon'
        elif blockchain == 'algo':
            blockchain = 'algorand'

        if blockchain in ('cardano', 'bitcoin', 'ethereum', 'polygon', 'base', 'solana', 'algorand'):
            return (blockchain, address)
        return None

    # Auto-detect
    blockchain = detect_blockchain(line)
    if blockchain:
        return (blockchain, line)

    return None

def parse_wallets_file(filepath: str) -> List[Dict]:
    """
    Parse the wallets file and return list of wallet entries.

    Returns:
        List of dicts with 'blockchain' and 'address' keys
    """
    wallets = []

    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                result = parse_address(line)
                if result:
                    blockchain, address = result
                    wallets.append({
                        'blockchain': blockchain,
                        'address': address,
                        'line_number': line_num
                    })
    except FileNotFoundError:
        return []

    return wallets

def validate_cardano_address(address: str) -> bool:
    """Basic validation for Cardano addresses."""
    if not address.startswith(('addr1', 'stake1')):
        return False
    # Mainnet addresses are typically 58-120 characters
    if len(address) < 50 or len(address) > 120:
        return False
    return True

def validate_bitcoin_address(address: str) -> bool:
    """Basic validation for Bitcoin addresses."""
    # Legacy
    if address.startswith('1'):
        return 26 <= len(address) <= 35
    # P2SH
    if address.startswith('3'):
        return 26 <= len(address) <= 35
    # Bech32
    if address.startswith('bc1'):
        return 26 <= len(address) <= 90
    return False
