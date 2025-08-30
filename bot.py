import os
import time
import ccxt
from dotenv import load_dotenv
import sentry_sdk
from sentry_sdk import capture_exception, capture_message
import schedule

load_dotenv()

# Initialize Sentry
SENTRY_DSN = os.getenv('SENTRY_DSN')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        environment='production'
    )
    print("Sentry initialized")
else:
    print("Warning: SENTRY_DSN not provided, error reporting disabled")

# Load environment variables
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
SYMBOL = os.getenv('SYMBOL', 'BTC_USDT')  # Default to BTC_USDT perpetual
STRATEGY = os.getenv('STRATEGY', 'simple').lower()
INCREASE_STEP = float(os.getenv('INCREASE_STEP', '2.0')) if STRATEGY == 'martingale' else None
MAX_INCREASE = float(os.getenv('MAX_INCREASE', '8.0')) if STRATEGY == 'martingale' else None
BASE_AMOUNT = float(os.getenv('BASE_AMOUNT'))
LEVERAGE = int(os.getenv('LEVERAGE'))
if not 2 <= LEVERAGE <= 10:
    error_msg = "Leverage must be between 2 and 10"
    print(error_msg)
    capture_message(error_msg)
    raise ValueError(error_msg)
ORDER_TYPE = os.getenv('ORDER_TYPE', 'market').lower()
DIRECTION = os.getenv('DIRECTION', 'long').lower()
TAKE_PROFIT_PCT = float(os.getenv('TAKE_PROFIT_PCT'))
POSITION_PCT = os.getenv('POSITION_PCT')  # Optional, string or None
if POSITION_PCT:
    POSITION_PCT = float(POSITION_PCT)
COLLATERAL_PCT = os.getenv('COLLATERAL_PCT')  # Optional
if COLLATERAL_PCT:
    COLLATERAL_PCT = float(COLLATERAL_PCT)
SCHEDULE_HOUR = int(os.getenv('SCHEDULE_HOUR', '0'))
SCHEDULE_MINUTE = int(os.getenv('SCHEDULE_MINUTE', '0'))

STATE_DIR = 'data'
STATE_FILE = os.path.join(STATE_DIR, 'state.txt')
os.makedirs(STATE_DIR, exist_ok=True)

def get_current_multiplier():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return float(f.read().strip())
    return 1.0

def save_multiplier(m):
    with open(STATE_FILE, 'w') as f:
        f.write(str(m))

def run_bot():
    print("Starting trading bot...")
    print(f"Strategy: {STRATEGY}, Direction: {DIRECTION}, Order Type: {ORDER_TYPE}")
    print(f"Base Amount: {BASE_AMOUNT}, Leverage: {LEVERAGE}, Take Profit PCT: {TAKE_PROFIT_PCT}")
    capture_message("Trading bot started", level="info")

    # Initialize exchange
    exchange = ccxt.mexc({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'options': {'defaultType': 'swap'},
    })

    try:
        # Load markets for precision
        exchange.load_markets()
        market = exchange.market(SYMBOL)
    except Exception as e:
        print(f"Error loading markets: {e}")
        capture_exception(e)
        return

    try:
        # Set position mode to one-way (hedged=False)
        exchange.set_position_mode(False, SYMBOL)
    except Exception as e:
        print(f"Error setting position mode: {e}")
        capture_exception(e)
        return

    try:
        # Check for open positions
        positions = exchange.fetch_positions([SYMBOL])
        open_pos = [p for p in positions if p['contracts'] > 0]
        if open_pos:
            print("Open position exists, skipping trade execution.")
            capture_message("Open position exists, skipping trade execution.", level="info")
            return
    except Exception as e:
        print(f"Error fetching positions: {e}")
        capture_exception(e)
        return

    # Determine multiplier for martingale
    if STRATEGY == 'martingale':
        try:
            # Get yesterday's timestamp in ms
            yesterday = int((time.time() - 86400) * 1000)
            trades = exchange.fetch_my_trades(SYMBOL, since=yesterday)
            pnls = [t.get('realizedPnl', 0) for t in trades if t.get('realizedPnl', 0) != 0]
            last_pnl = pnls[-1] if pnls else 0
            current_multiplier = get_current_multiplier()
            if last_pnl < 0:
                new_multiplier = min(MAX_INCREASE, current_multiplier * INCREASE_STEP)
            else:
                new_multiplier = 1.0
            save_multiplier(new_multiplier)
            multiplier = new_multiplier
            print(f"Martingale multiplier: {multiplier}")
        except Exception as e:
            print(f"Error in martingale calculation: {e}")
            capture_exception(e)
            return
    else:
        multiplier = 1.0
        print("Using simple strategy, multiplier: 1.0")

    try:
        # Get balance
        balance_info = exchange.fetch_balance({'type': 'contract'})
        free_balance = balance_info['USDT']['free']
        print(f"Free balance: {free_balance} USDT")
    except Exception as e:
        print(f"Error fetching balance: {e}")
        capture_exception(e)
        return

    # Calculate base margin
    base_margin = BASE_AMOUNT
    if COLLATERAL_PCT is not None:
        base_margin = (COLLATERAL_PCT / 100) * free_balance
        print(f"Using {COLLATERAL_PCT}% of collateral, base margin: {base_margin}")

    # Apply multiplier
    margin = base_margin * multiplier

    try:
        # Calculate notional and quantity
        ticker = exchange.fetch_ticker(SYMBOL)
        current_price = ticker['last']
        print(f"Current price: {current_price}")
        notional = margin * LEVERAGE
        quantity = notional / current_price
        quantity = exchange.amount_to_precision(SYMBOL, quantity)
        print(f"Calculated quantity: {quantity}")
    except Exception as e:
        print(f"Error fetching ticker or calculating quantity: {e}")
        capture_exception(e)
        return

    try:
        # Set leverage
        exchange.set_leverage(LEVERAGE, SYMBOL, {'openType': 2})  # 2: cross margin
        print(f"Leverage set to {LEVERAGE}x")
    except Exception as e:
        print(f"Error setting leverage: {e}")
        capture_exception(e)
        return

    # Determine side and entry price
    if DIRECTION == 'long':
        side = 'buy'
        tp_multiplier = 1 + (TAKE_PROFIT_PCT / 100)
        tp_side = 'sell'
    else:
        side = 'sell'
        tp_multiplier = 1 - (TAKE_PROFIT_PCT / 100)
        tp_side = 'buy'

    if ORDER_TYPE == 'limit':
        price_entry = ticker['ask'] if side == 'buy' else ticker['bid']
        price_entry = exchange.price_to_precision(SYMBOL, price_entry)
    else:
        price_entry = None

    try:
        # Place entry order
        entry_params = {'openType': 2}  # cross
        order = exchange.create_order(SYMBOL, ORDER_TYPE, side, quantity, price_entry, entry_params)
        print(f"Entry order placed: {order['id']}")
    except Exception as e:
        print(f"Error placing entry order: {e}")
        capture_exception(e)
        return

    # Wait for order to fill with timeout
    max_wait_seconds = 300  # 5 minutes
    start_time = time.time()
    filled_order = None
    try:
        filled_order = exchange.fetch_order(order['id'], SYMBOL)
        while filled_order['status'] != 'closed' and (time.time() - start_time) < max_wait_seconds:
            time.sleep(10)  # Check every 10 seconds
            filled_order = exchange.fetch_order(order['id'], SYMBOL)
        if filled_order['status'] != 'closed':
            exchange.cancel_order(order['id'], SYMBOL)
            print("Limit order not filled within timeout, cancelled.")
            capture_message("Limit order not filled within timeout, cancelled.", level="warning")
            return
        print("Entry order filled.")
    except Exception as e:
        print(f"Error monitoring or cancelling entry order: {e}")
        capture_exception(e)
        if order and order.get('id'):
            try:
                exchange.cancel_order(order['id'], SYMBOL)
            except Exception as cancel_e:
                print(f"Error cancelling order: {cancel_e}")
                capture_exception(cancel_e)
        return

    entry_price = filled_order['average']
    filled_quantity = filled_order['filled']

    # Calculate TP price
    tp_price = entry_price * tp_multiplier
    tp_price = exchange.price_to_precision(SYMBOL, tp_price)

    # Determine TP quantity
    tp_quantity = filled_quantity if POSITION_PCT is None else filled_quantity * (POSITION_PCT / 100)
    tp_quantity = exchange.amount_to_precision(SYMBOL, tp_quantity)

    try:
        # Place TP order
        tp_params = {'reduceOnly': True, 'openType': 2}
        tp_order = exchange.create_order(SYMBOL, 'limit', tp_side, tp_quantity, tp_price, tp_params)
        print(f"Take profit order placed: {tp_order['id']}")
    except Exception as e:
        print(f"Error placing take profit order: {e}")
        capture_exception(e)
        return

    print("Trade executed successfully.")
    capture_message("Trade executed successfully", level="info")

# Schedule the bot to run daily at the specified hour and minute
schedule.every().day.at(f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}").do(run_bot)
print(f"Scheduled bot to run daily at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}")

# Keep the script running to check the schedule
while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute