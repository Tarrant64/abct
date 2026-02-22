import re
from typing import Optional, Tuple, List, Dict

def detect_blockchain(address: str) -> Optional[str]:
    """
    Detect the blockchain based on address format.

    Returns:
        'cardano', 'bitcoin', 'ethereum', 'polygon', 'base', 'solana', 'algorand',
        'bsc', 'arbitrum', 'avalanche', 'tron', 'xrp', 'hedera', 'multiversx',
        'sui', 'aptos', 'filecoin', 'litecoin', 'dogecoin', 'zcash', 'tezos',
        'stacks', 'vechain', 'cosmos', 'near', 'icp', 'ton', 'polkadot', 'kusama',
        'stellar', 'kaspa', 'osmosis', 'celestia', 'injective', 'dydx', 'sei',
        'akash', 'kaia', 'ergo', 'iota', 'waves', 'mina', 'zilliqa', or None if unknown
    """
    address = address.strip()

    # Check for explicit prefix
    if ':' in address:
        prefix, addr = address.split(':', 1)
        prefix = prefix.lower()
        prefix_map = {
            'cardano': 'cardano', 'bitcoin': 'bitcoin', 'ethereum': 'ethereum',
            'eth': 'ethereum', 'polygon': 'polygon', 'matic': 'polygon',
            'base': 'base', 'solana': 'solana', 'sol': 'solana',
            'algorand': 'algorand', 'algo': 'algorand',
            'bsc': 'bsc', 'bnb': 'bsc',
            'arb': 'arbitrum', 'arbitrum': 'arbitrum',
            'avax': 'avalanche', 'avalanche': 'avalanche',
            'tron': 'tron', 'trx': 'tron',
            'xrp': 'xrp', 'ripple': 'xrp',
            'hedera': 'hedera', 'hbar': 'hedera',
            'multiversx': 'multiversx', 'egld': 'multiversx', 'elrond': 'multiversx',
            'sui': 'sui',
            'aptos': 'aptos', 'apt': 'aptos',
            'filecoin': 'filecoin', 'fil': 'filecoin',
            'litecoin': 'litecoin', 'ltc': 'litecoin',
            'dogecoin': 'dogecoin', 'doge': 'dogecoin',
            'zcash': 'zcash', 'zec': 'zcash',
            'tezos': 'tezos', 'xtz': 'tezos',
            'stacks': 'stacks', 'stx': 'stacks',
            'vechain': 'vechain', 'vet': 'vechain',
            'cosmos': 'cosmos', 'atom': 'cosmos',
            'near': 'near',
            'icp': 'icp',
            # New chains
            'ton': 'ton',
            'polkadot': 'polkadot', 'dot': 'polkadot',
            'kusama': 'kusama', 'ksm': 'kusama',
            'stellar': 'stellar', 'xlm': 'stellar',
            'kaspa': 'kaspa', 'kas': 'kaspa',
            'osmosis': 'osmosis', 'osmo': 'osmosis',
            'celestia': 'celestia', 'tia': 'celestia',
            'injective': 'injective', 'inj': 'injective',
            'dydx': 'dydx',
            'sei': 'sei',
            'akash': 'akash', 'akt': 'akash',
            'kaia': 'kaia', 'klay': 'kaia',
            'ergo': 'ergo', 'erg': 'ergo',
            'iota': 'iota',
            'waves': 'waves',
            'mina': 'mina',
            'zilliqa': 'zilliqa', 'zil': 'zilliqa',
        }
        if prefix in prefix_map:
            return prefix_map[prefix]
        return None

    # Cardano mainnet addresses start with addr1
    if address.startswith('addr1'):
        return 'cardano'

    # Cardano stake addresses start with stake1
    if address.startswith('stake1'):
        return 'cardano'

    # MultiversX addresses start with erd1, exactly 62 chars
    if address.startswith('erd1') and len(address) == 62:
        return 'multiversx'

    # Cosmos addresses start with cosmos1, bech32 encoded
    if address.startswith('cosmos1') and 39 <= len(address) <= 45:
        return 'cosmos'

    # Tezos addresses start with tz1/tz2/tz3 (implicit) or KT1 (contract), 36 chars
    if address.startswith(('tz1', 'tz2', 'tz3', 'KT1')) and len(address) == 36:
        return 'tezos'

    # Litecoin bech32 addresses start with ltc1
    if address.startswith('ltc1') and len(address) >= 26:
        return 'litecoin'

    # NEAR named accounts end with .near
    if address.endswith('.near') and len(address) >= 6:
        return 'near'

    # Stacks addresses start with SP (mainnet) or ST (testnet), 33-41 chars
    if address.startswith(('SP', 'ST')) and 33 <= len(address) <= 41:
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        if all(c in base58_chars for c in address):
            return 'stacks'

    # Algorand addresses - 58 characters, base32 (uppercase A-Z and 2-7)
    if len(address) == 58:
        base32_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')
        if all(c in base32_chars for c in address.upper()):
            return 'algorand'

    # Tron addresses - T + 33 base58 characters
    if address.startswith('T') and len(address) == 34:
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        if all(c in base58_chars for c in address):
            return 'tron'

    # Hedera addresses - shard.realm.num format (e.g., 0.0.1234567)
    if re.match(r'^\d+\.\d+\.\d+$', address):
        return 'hedera'

    # XRP addresses - start with r, 25-35 chars, base58
    if address.startswith('r') and 25 <= len(address) <= 35:
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        if all(c in base58_chars for c in address):
            return 'xrp'

    # Dogecoin addresses - D prefix, 26-35 chars, base58
    if address.startswith('D') and 26 <= len(address) <= 35:
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        if all(c in base58_chars for c in address):
            return 'dogecoin'

    # ZCash transparent addresses - t1 (P2PKH) or t3 (P2SH), 35 chars
    if address.startswith(('t1', 't3')) and len(address) == 35:
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        if all(c in base58_chars for c in address):
            return 'zcash'

    # Litecoin legacy addresses - L prefix (P2PKH) or M prefix (P2SH), 26-35 chars
    if address.startswith(('L', 'M')) and 26 <= len(address) <= 35:
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        if all(c in base58_chars for c in address):
            return 'litecoin'

    # Filecoin addresses - start with f0, f1, f3, or f4
    if len(address) >= 3 and address[0] == 'f' and address[1] in ('0', '1', '3', '4'):
        return 'filecoin'

    # Ethereum addresses - start with 0x and are 42 characters
    if address.lower().startswith('0x') and len(address) == 42:
        try:
            # Verify it's valid hex
            int(address[2:], 16)
            return 'ethereum'
        except ValueError:
            pass

    # Sui addresses - start with 0x and are 66 characters (vs ETH 42)
    # Aptos shares the same format; defaults to Sui. Use aptos: prefix for Aptos.
    if address.lower().startswith('0x') and len(address) == 66:
        try:
            int(address[2:], 16)
            return 'sui'
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

    # TON addresses - EQ... or UQ... user-friendly format (48 chars)
    if address.startswith(('EQ', 'UQ')) and len(address) == 48:
        return 'ton'

    # Stellar addresses - G prefix, 56 chars, base32
    if address.startswith('G') and len(address) == 56:
        return 'stellar'

    # Mina Protocol addresses - B62... prefix, ~55 chars
    if address.startswith('B62') and 50 <= len(address) <= 60:
        return 'mina'

    # Kaspa addresses - kaspa: prefix
    if address.startswith('kaspa:') and len(address) > 10:
        return 'kaspa'

    # Cosmos IBC chain bech32 prefixes
    if address.startswith('osmo1') and 39 <= len(address) <= 50:
        return 'osmosis'
    if address.startswith('celestia1') and 43 <= len(address) <= 55:
        return 'celestia'
    if address.startswith('inj1') and 42 <= len(address) <= 46:
        return 'injective'
    if address.startswith('dydx1') and 42 <= len(address) <= 47:
        return 'dydx'
    if address.startswith('sei1') and 42 <= len(address) <= 46:
        return 'sei'
    if address.startswith('akash1') and 43 <= len(address) <= 50:
        return 'akash'

    # Waves addresses - 3P/3N prefix, ~35 chars, base58
    if address.startswith(('3P', '3N')) and 34 <= len(address) <= 36:
        return 'waves'

    # Ergo addresses - start with 9, ~51 chars
    if address.startswith('9') and 40 <= len(address) <= 60:
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        if all(c in base58_chars for c in address):
            return 'ergo'

    # Polkadot addresses - SS58 format, 47-48 chars, base58 (starts with 1)
    # Kusama addresses - SS58 format, 47-48 chars (starts with C/D/E/F/G/H)
    # These are ambiguous without prefix, so require explicit prefix

    # Zilliqa bech32 addresses - zil1... (39 chars)
    if address.startswith('zil1') and len(address) == 39:
        return 'zilliqa'

    # IOTA MoveVM addresses - 0x + 64 hex chars (same as Sui but use iota: prefix)
    # Handled via explicit prefix only (iota:0x...) to avoid collision with Sui

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
        prefix_map = {
            'eth': 'ethereum', 'sol': 'solana', 'matic': 'polygon',
            'algo': 'algorand', 'bnb': 'bsc', 'arb': 'arbitrum',
            'avax': 'avalanche', 'trx': 'tron',
            'ripple': 'xrp', 'hbar': 'hedera',
            'egld': 'multiversx', 'elrond': 'multiversx',
            'apt': 'aptos', 'fil': 'filecoin',
            'ltc': 'litecoin', 'doge': 'dogecoin', 'zec': 'zcash',
            'xtz': 'tezos', 'stx': 'stacks', 'vet': 'vechain',
            'atom': 'cosmos',
            # New chains
            'dot': 'polkadot', 'ksm': 'kusama', 'xlm': 'stellar',
            'kas': 'kaspa', 'osmo': 'osmosis', 'tia': 'celestia',
            'inj': 'injective', 'akt': 'akash', 'klay': 'kaia',
            'erg': 'ergo', 'zil': 'zilliqa',
        }
        if blockchain in prefix_map:
            blockchain = prefix_map[blockchain]

        valid_chains = ('cardano', 'bitcoin', 'ethereum', 'polygon', 'base', 'solana',
                        'algorand', 'bsc', 'arbitrum', 'avalanche', 'tron',
                        'xrp', 'hedera', 'multiversx', 'sui', 'aptos', 'filecoin',
                        'litecoin', 'dogecoin', 'zcash', 'tezos', 'stacks',
                        'vechain', 'cosmos', 'near', 'icp',
                        'ton', 'polkadot', 'kusama', 'stellar', 'kaspa',
                        'osmosis', 'celestia', 'injective', 'dydx', 'sei', 'akash',
                        'kaia', 'ergo', 'iota', 'waves', 'mina', 'zilliqa')
        if blockchain in valid_chains:
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
