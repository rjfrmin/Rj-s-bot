# config.py
# Values can be overridden by environment variables on the cloud.

import os

# === MODE ===
# "paper" = simulate only (recommended first). "live" = real trades (dangerous).
MODE = os.getenv("MODE", "paper")

# === RPC / STREAMING ===
# Get a free or paid key at https://helius.dev
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "YOUR_HELIUS_API_KEY_HERE")
RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
WS_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# === WALLET TO COPY ===
# Comma-separated list in the environment variable TARGET_WALLETS
# Example: "wallet1,wallet2,wallet3"
_raw_wallets = os.getenv("TARGET_WALLETS", "")
TARGET_WALLETS = [w.strip() for w in _raw_wallets.split(",") if w.strip()]

# === YOUR TRADING WALLET (only needed for live mode) ===
PRIVATE_KEY_BASE58 = os.getenv("PRIVATE_KEY_BASE58", "")

# === POSITION & RISK ===
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", "0.05"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "5"))
MAX_SOL_PER_DAY = float(os.getenv("MAX_SOL_PER_DAY", "1.0"))
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "5000"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "300"))

# === EXIT RULES ===
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "40.0"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "25.0"))
MIRROR_TARGET_SELLS = os.getenv("MIRROR_TARGET_SELLS", "true").lower() == "true"
TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "0.0"))

# === SIGNAL FILTERS ===
CLUSTER_WINDOW_SECONDS = int(os.getenv("CLUSTER_WINDOW_SECONDS", "90"))
MIN_CLUSTER_SIZE = int(os.getenv("MIN_CLUSTER_SIZE", "2"))
REQUIRE_CLUSTER = os.getenv("REQUIRE_CLUSTER", "false").lower() == "true"

# === PAPER TRADING ===
PAPER_STARTING_BALANCE_SOL = float(os.getenv("PAPER_STARTING_BALANCE_SOL", "5.0"))
PAPER_LATENCY_MS = int(os.getenv("PAPER_LATENCY_MS", "800"))
