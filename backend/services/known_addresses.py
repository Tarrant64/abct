"""
Known Address Database

Static lookup of known CEX hot wallet addresses per blockchain.
Used by the intelligence router to label counterparty addresses.
"""

from typing import Optional

# Known CEX hot wallet addresses by blockchain
# Format: { blockchain: { address_lowercase: label } }
# EVM chains (polygon, base, arbitrum, etc.) share the same address space as Ethereum
KNOWN_ADDRESSES = {
    "ethereum": {
        # Binance
        "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
        "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
        "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance",
        "0x9696f59e4d72e237be84ffd425dcad154bf96976": "Binance",
        "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance",
        "0x5a52e96bacdabb82fd05763e25335261b270efcb": "Binance",
        "0x3c783c21a0383057d128bae431894a5c19f9cf06": "Binance",
        "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance",
        # Coinbase
        "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
        "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
        "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": "Coinbase",
        "0x3cd751e6b0078be393132286c442345e68ff0aaa": "Coinbase",
        "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": "Coinbase",
        "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase",
        "0x77134cbc06cb00b66f4c7e623d5fdbf6777635ec": "Coinbase",
        # Kraken
        "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
        "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13": "Kraken",
        "0xe853c56864a2ebe4576a807d26fdc4a0ada51919": "Kraken",
        "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
        # OKX
        "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
        "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": "OKX",
        "0xa7efae728d2936e78bda97dc267687568dd593f3": "OKX",
        # Gate.io
        "0x0d0707963952f2fba59dd06f2b425ace40b492fe": "Gate.io",
        "0x1c4b70a3968436b9a0a9cf5205c787eb81bb558c": "Gate.io",
        # KuCoin
        "0xd6216fc19db775df9774a6e33526131da7d19a2c": "KuCoin",
        "0xeb2629a2734e272bcc07bda959863f316f4bd4cf": "KuCoin",
        "0xf3f094484ec6901ffc9681bcb808b96bafd0b8a8": "KuCoin",
        # Bybit
        "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
        "0x1db92e2eebc8e0c075a02bea49a2935bcd2dfcf4": "Bybit",
        # Gemini
        "0xd24400ae8bfebb18ca49be86258a3c749cf46853": "Gemini",
        "0x6fc82a5fe25a5cdb58bc74600a40a69c065263f8": "Gemini",
        # Crypto.com
        "0x6262998ced04146fa42253a5c0af90ca02dfd2a3": "Crypto.com",
        "0x46340b20830761efd32832a74d7169b29feb9758": "Crypto.com",
        # Huobi / HTX
        "0xab5c66752a9e8167967685f1450532fb96d5d24f": "HTX",
        "0x6748f50f686bfbca6fe8ad62b22228b87f31ff2b": "HTX",
        "0xfdb16996831753d5331ff813c29a93c76834a0ad": "HTX",
    },
    "bitcoin": {
        # Binance
        "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3": "Binance",
        "34xp4vrocgjym3xr7ycvpfhocnxv4twseo": "Binance",
        "3jzq4atw1turvbfib95kv8u8gm9dkzpde6": "Binance",
        "1ndjqh3yhanc2acbqkxyxpnzdfkn6lgokg": "Binance",
        "bc1qx9t2l3pyny2spqpqlye8svce70nppwtaxwdrp4": "Binance",
        # Coinbase
        "3kf9nxowq4assgxrmzhwux4bby9ynnwzed": "Coinbase",
        "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh": "Coinbase",
        "3cd1qegssvq3f6mhvxrlxewag1yj5epbcpt": "Coinbase",
        # Kraken
        "bc1qr4dl5wa7kl8yu792dceg9z5knl2grgqp09393": "Kraken",
        "3afzwtczfg96v4bycj6amaiwoxkbkgedf7": "Kraken",
        # Bitfinex
        "bc1qgdjqv0av3q56jvd82tkdjpy7gddzmss2t8u8h6": "Bitfinex",
        "3jzycbtpn6j72pfmerwq8kpmfsnnb4f1mq": "Bitfinex",
    },
    "cardano": {
        # Binance
        "addr1q9yr2pglsre33xueqxd4xkg4kgxnc75qwmka7yqtlxla4dz7jq9g6kpgnerepwjspuya3v5awhwxq5mlvs0n20zzlnqs58zt3j": "Binance",
        # Coinbase (Cardano addresses are longer, using a few known patterns)
        # Note: Cardano uses bech32 addresses and case-sensitive comparisons
    },
    "solana": {
        # Binance
        "5tzfn7nyjrgi4ztlwrnxxyb5fbnzyrof4jcmjatv7yar": "Binance",
        "9wfpc9rqzhr4yuupjaxf9jsedgflwufsb2jys3txccy": "Binance",
        "2ojv9barm7z1gvbtwkzgpmwsj8aqf34x1ylazbqzaq8t": "Binance",
        # Coinbase
        "h8ztjcisazcyochiuj57h2b4ybcl73rmimwb8noo3njdi": "Coinbase",
        # Kraken
        "fwwbgdvgltwgjbzqbuaafpw27zg3xdnnzmaqsgkx4pzr": "Kraken",
        # OKX
        "5veggsjncka1gnlyvfmkqnzpvr5nbeafl2jwdxqylnna": "OKX",
    },
}

# Chains that share EVM address space with Ethereum
EVM_COMPATIBLE_CHAINS = {"polygon", "base", "arbitrum", "bsc", "avalanche", "optimism"}


def identify_address(address: str, blockchain: str) -> Optional[str]:
    """
    Look up a known label for an address on a given blockchain.

    Args:
        address: The wallet/contract address
        blockchain: The blockchain name (ethereum, bitcoin, cardano, solana, etc.)

    Returns:
        Label string if known (e.g. "Binance"), None if unknown
    """
    if not address:
        return None

    chain = blockchain.lower()

    # For case-insensitive chains (EVM, Bitcoin), normalize to lowercase
    # Cardano is case-sensitive (bech32)
    if chain != "cardano":
        address = address.lower()

    # Direct lookup
    chain_addresses = KNOWN_ADDRESSES.get(chain, {})
    if address in chain_addresses:
        return chain_addresses[address]

    # EVM-compatible chains fall back to Ethereum addresses
    if chain in EVM_COMPATIBLE_CHAINS:
        eth_addresses = KNOWN_ADDRESSES.get("ethereum", {})
        if address in eth_addresses:
            return eth_addresses[address]

    return None


def is_known_cex(address: str, blockchain: str) -> bool:
    """Check if an address belongs to a known centralized exchange."""
    return identify_address(address, blockchain) is not None
