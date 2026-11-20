#!/usr/bin/env python3
"""
Memecoin Copy + Signal Bot (Solana)
===================================
Paper-trading first. Real money only after you understand every line.

What it does:
- Watches a list of target wallets for buys (via Helius transactionSubscribe)
- Optional cluster signal: multiple targets buying the same mint in a short window
- Enters with fixed SOL size
- Exits on take-profit, stop-loss, or when the target sells (configurable)
- Runs in paper mode by default (no real transactions)

Requirements:
  pip install websockets aiohttp solders base58 python-dotenv

You need a Helius API key (free tier works for testing).
Never put a real private key in this file if you share the code.
"""

import asyncio
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from collections import defaultdict, deque

import aiohttp
import websockets
from solders.pubkey import Pubkey

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Position:
    mint: str
    entry_price: float          # in SOL per token (approx)
    amount_tokens: float
    cost_sol: float
    entry_time: float
    source_wallet: str
    highest_price: float = 0.0
    status: str = "open"        # open | closed

@dataclass
class PaperState:
    balance_sol: float = config.PAPER_STARTING_BALANCE_SOL
    positions: Dict[str, Position] = field(default_factory=dict)
    closed_pnl: float = 0.0
    trades: List[dict] = field(default_factory=list)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

paper = PaperState()
recent_buys: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))  # mint -> list of (wallet, timestamp)
open_mints: Set[str] = set()
daily_spent = 0.0
day_start = time.time()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now() -> float:
    return time.time()

def reset_daily_if_needed():
    global daily_spent, day_start
    if now() - day_start > 86400:
        daily_spent = 0.0
        day_start = now()
        log.info("Daily spend counter reset")

def can_open_new() -> bool:
    reset_daily_if_needed()
    if len(paper.positions) >= config.MAX_POSITIONS:
        return False
    if daily_spent + config.BUY_AMOUNT_SOL > config.MAX_SOL_PER_DAY:
        return False
    if paper.balance_sol < config.BUY_AMOUNT_SOL:
        return False
    return True

def record_buy_signal(mint: str, wallet: str):
    recent_buys[mint].append((wallet, now()))
    # Clean old entries
    cutoff = now() - config.CLUSTER_WINDOW_SECONDS
    while recent_buys[mint] and recent_buys[mint][0][1] < cutoff:
        recent_buys[mint].popleft()

def cluster_size(mint: str) -> int:
    wallets = {w for w, t in recent_buys[mint]}
    return len(wallets)

# ---------------------------------------------------------------------------
# Paper execution
# ---------------------------------------------------------------------------

async def paper_buy(mint: str, source_wallet: str, estimated_price: float = 0.00001):
    """Simulate a buy. In real mode this would call Jupiter / PumpPortal."""
    if not can_open_new():
        log.warning(f"Skip buy {mint[:8]}... risk limits hit")
        return

    cost = config.BUY_AMOUNT_SOL
    # crude token amount estimate
    tokens = cost / max(estimated_price, 1e-12)

    pos = Position(
        mint=mint,
        entry_price=estimated_price,
        amount_tokens=tokens,
        cost_sol=cost,
        entry_time=now(),
        source_wallet=source_wallet,
        highest_price=estimated_price,
    )
    paper.positions[mint] = pos
    paper.balance_sol -= cost
    global daily_spent
    daily_spent += cost
    open_mints.add(mint)

    log.info(
        f"[PAPER BUY] {mint[:12]}... | {cost:.4f} SOL | "
        f"from {source_wallet[:8]}... | balance left {paper.balance_sol:.3f}"
    )
    paper.trades.append({
        "side": "buy",
        "mint": mint,
        "sol": cost,
        "time": now(),
        "source": source_wallet,
    })

async def paper_sell(mint: str, reason: str, current_price: float):
    if mint not in paper.positions:
        return
    pos = paper.positions[mint]
    proceeds = pos.amount_tokens * current_price
    pnl = proceeds - pos.cost_sol
    pnl_pct = (pnl / pos.cost_sol) * 100 if pos.cost_sol else 0

    paper.balance_sol += proceeds
    paper.closed_pnl += pnl
    del paper.positions[mint]
    open_mints.discard(mint)

    log.info(
        f"[PAPER SELL] {mint[:12]}... | reason={reason} | "
        f"PnL {pnl:+.4f} SOL ({pnl_pct:+.1f}%) | "
        f"balance {paper.balance_sol:.3f}"
    )
    paper.trades.append({
        "side": "sell",
        "mint": mint,
        "sol": proceeds,
        "pnl": pnl,
        "reason": reason,
        "time": now(),
    })

# ---------------------------------------------------------------------------
# Exit logic
# ---------------------------------------------------------------------------

async def check_exits():
    """Periodic check of open positions against TP / SL / trailing."""
    while True:
        await asyncio.sleep(8)
        for mint, pos in list(paper.positions.items()):
            # In real bot you would fetch current price from Jupiter or Birdeye.
            # Here we keep the entry price as placeholder so TP/SL only fire on
            # explicit signals or when you plug in a price feed.
            current = pos.entry_price  # replace with live price
            pos.highest_price = max(pos.highest_price, current)

            # Take profit
            if current >= pos.entry_price * (1 + config.TAKE_PROFIT_PCT / 100):
                await paper_sell(mint, f"TP +{config.TAKE_PROFIT_PCT}%", current)
                continue

            # Stop loss
            if current <= pos.entry_price * (1 - config.STOP_LOSS_PCT / 100):
                await paper_sell(mint, f"SL -{config.STOP_LOSS_PCT}%", current)
                continue

            # Trailing stop
            if config.TRAILING_STOP_PCT > 0:
                trail_level = pos.highest_price * (1 - config.TRAILING_STOP_PCT / 100)
                if current <= trail_level:
                    await paper_sell(mint, f"Trailing SL", current)

# ---------------------------------------------------------------------------
# Transaction parsing (simplified)
# ---------------------------------------------------------------------------

def extract_token_buys(tx: dict, watched: Set[str]) -> List[tuple]:
    """
    Very simplified parser. Real production code needs full instruction decoding
    for Pump.fun, Raydium, Jupiter etc.
    Returns list of (wallet, mint) that appear to be buys by watched wallets.
    """
    results = []
    try:
        meta = tx.get("meta") or {}
        message = (tx.get("transaction") or {}).get("message") or {}
        account_keys = message.get("accountKeys") or []
        # Helius sometimes returns richer parsed data
        # This is a placeholder that looks for token balance increases
        pre = {b["mint"]: b for b in (meta.get("preTokenBalances") or []) if b.get("owner") in watched}
        post = {b["mint"]: b for b in (meta.get("postTokenBalances") or []) if b.get("owner") in watched}

        for mint, post_bal in post.items():
            pre_bal = pre.get(mint)
            pre_amount = float(pre_bal.get("uiTokenAmount", {}).get("uiAmount") or 0) if pre_bal else 0
            post_amount = float(post_bal.get("uiTokenAmount", {}).get("uiAmount") or 0)
            if post_amount > pre_amount + 1e-9:
                owner = post_bal.get("owner")
                if owner in watched:
                    results.append((owner, mint))
    except Exception as e:
        log.debug(f"parse error: {e}")
    return results

# ---------------------------------------------------------------------------
# WebSocket listener
# ---------------------------------------------------------------------------

async def listen_wallets():
    if not config.TARGET_WALLETS:
        log.error("No TARGET_WALLETS set. Add them via environment variable.")
        return

    watched = set(config.TARGET_WALLETS)
    log.info(f"Watching {len(watched)} wallets...")

    while True:
        try:
            async with websockets.connect(config.WS_URL) as ws:
                # Subscribe to transactions that involve any of our target wallets
                for wallet in watched:
                    sub = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "transactionSubscribe",
                        "params": [
                            {"accountInclude": [wallet]},
                            {
                                "commitment": "confirmed",
                                "encoding": "jsonParsed",
                                "transactionDetails": "full",
                                "maxSupportedTransactionVersion": 0,
                            },
                        ],
                    }
                    await ws.send(json.dumps(sub))

                log.info("WebSocket connected and subscribed")

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        if "params" not in msg:
                            continue
                        result = msg["params"].get("result") or {}
                        tx = result.get("transaction") or result
                        if not tx:
                            continue

                        buys = extract_token_buys(tx, watched)
                        for wallet, mint in buys:
                            if mint in open_mints:
                                continue  # already in a position

                            record_buy_signal(mint, wallet)
                            size = cluster_size(mint)

                            if config.REQUIRE_CLUSTER and size < config.MIN_CLUSTER_SIZE:
                                log.info(f"Signal ignored (cluster {size} < {config.MIN_CLUSTER_SIZE}) {mint[:10]}...")
                                continue

                            strength = "CLUSTER" if size >= config.MIN_CLUSTER_SIZE else "single"
                            log.info(f"BUY signal ({strength} size={size}) {mint[:12]}... by {wallet[:8]}...")

                            # Simulated latency
                            await asyncio.sleep(config.PAPER_LATENCY_MS / 1000)
                            await paper_buy(mint, wallet)

                            # Also handle target sells for mirror
                            if config.MIRROR_TARGET_SELLS:
                                # Real implementation would detect sell side here
                                pass

                    except Exception as e:
                        log.debug(f"message handling error: {e}")

        except Exception as e:
            log.error(f"WS error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

#
