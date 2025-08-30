# MEXC Trading Bot

A Dockerized Python trading bot for MEXC futures trading, designed to execute daily trades based on configurable parameters. The bot supports both simple and Martingale strategies, with error handling, Sentry integration for monitoring, and scheduling via environment variables.

## Features
- **Strategies**: Choose between `simple` (fixed position size) or `martingale` (increase position size after losses).
- **Order Types**: Supports `market` and `limit` orders with timeout handling for limit orders.
- **Position Sizing**: Configurable base amount, leverage (2x–10x), and optional collateral percentage.
- **Take Profit**: Set a percentage-based take profit, with an optional partial position close.
- **Direction**: Trade in `long` or `short` direction.
- **Scheduling**: Runs daily at a specified hour and minute (UTC) using the `schedule` library.
- **Error Reporting**: Integrates with Sentry for error and event logging.
- **Persistence**: Stores Martingale multiplier state across runs.
- **Precision Handling**: Rounds quantities and prices to exchange precision.

## Prerequisites
- Docker installed on your system.
- A MEXC account with futures trading enabled and API keys with trading permissions.
- A Sentry account and DSN for error reporting (optional).

## Installation

1. **Clone the Repository** (or create the files manually):
   ```bash
   git clone https://github.com/pablommf23/mexc_dca
   cd mexc-trading-bot
   ```

2. **Set Up Environment Variables**:
   - Copy the `.env.example` to `.env` and fill in your details:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` with your MEXC API keys, Sentry DSN, and desired parameters:
     ```
     API_KEY=your_api_key_here
     API_SECRET=your_api_secret_here
     SENTRY_DSN=your_sentry_dsn_here
     SYMBOL=BTC_USDT
     STRATEGY=martingale  # or simple
     INCREASE_STEP=2.0    # Martingale multiplier per loss
     MAX_INCREASE=8.0     # Max Martingale multiplier
     BASE_AMOUNT=10.0     # Base margin in USDT
     LEVERAGE=5           # 2 to 10
     ORDER_TYPE=market    # or limit
     DIRECTION=long       # or short
     TAKE_PROFIT_PCT=1.0  # Take profit percentage
     SCHEDULE_HOUR=0      # Hour for daily execution (0-23, UTC)
     SCHEDULE_MINUTE=0    # Minute for daily execution (0-59)
     # POSITION_PCT=50     # Optional: percentage of position to close at TP
     # COLLATERAL_PCT  Optional: percentage of free balance to use
     ```

3. **Build the Docker Image**:
   ```bash
   docker build -t trading-bot .
   ```

4. **Run the Container**:
   ```bash
   docker run --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/log.txt:/app/log.txt trading-bot
   ```
   - The `-v` mounts persist the state file (`data/state.txt`) for Martingale tracking and log file (`log.txt`) for debugging.
   - The bot runs continuously, executing daily at the specified `SCHEDULE_HOUR` and `SCHEDULE_MINUTE` (UTC).

## Configuration Parameters
| Parameter          | Description                                                                 | Example         |
|--------------------|-----------------------------------------------------------------------------|-----------------|
| `API_KEY`          | MEXC API key with trading permissions                                       | `your_api_key`  |
| `API_SECRET`       | MEXC API secret                                                             | `your_secret`   |
| `SENTRY_DSN`       | Sentry DSN for error reporting (optional
