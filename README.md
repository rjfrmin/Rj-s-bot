# Memecoin Copy + Signal Bot (Solana)

Paper-first copy-trading bot with simple cluster signals and proper risk exits.

## What this is

- Watches wallets you choose
- Detects when they buy tokens
- Optionally boosts signals when several of those wallets buy the same token quickly (cluster)
- Enters with a fixed SOL size
- Exits on take-profit, stop-loss, or (when implemented) when the target sells
- Defaults to **paper mode** so you lose no real money while testing

## What this is not

- Not a guaranteed profit machine
- Not production-ready for live trading without more work
- Does not include full Pump.fun / Raydium instruction decoding or live price feeds yet
- Does not hold or ask for your private key in paper mode

## Quick start (local)

```bash
cd memecoin_bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
