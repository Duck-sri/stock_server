# import smartapi.log_data

from pathlib import Path

import pandas as pd
import time
from datetime import datetime, timedelta
import tqdm

from pprint import pprint
import smartapi.utils as utils
from smartapi.connections.api_types import TransactionType, Exchange, Variety, ProductType, OrderType, Duration, Interval, Order
from smartapi.connections import SmartAPIConnect

import traceback

path = Path("./smartapi/configs/user.toml").absolute()
print(path)
user_config = utils.read_toml(path)

api_obj = SmartAPIConnect(
    client_code=user_config['client_code'],
    pin=user_config['angel_pin'],
    totp=user_config['keys']['qr_otp'],
    api_key=user_config['keys']['trading']
)


session_data = api_obj.generate_session()

try:
    today = datetime.today().replace(hour=9, minute=15, second=0, microsecond=0)

    token_map = utils.read_json(Path('/Users/you-know-who/Code/Project/stock_server/notebooks/token_map.json'))
    tokens = list(token_map.keys())

    for token in tqdm.tqdm(tokens):
        res = api_obj.get_candle_data(
            exchange=Exchange.NFO,
            symbol_token=token,
            interval=Interval.ONE_MINUTE,
            start_date=(today - timedelta(days=4)),
            end_date=today
        )

        res.to_csv(Path(f'./dump/{token}.csv').absolute(), index=True, index_label='time')
        time.sleep(.3)

except:
    traceback.print_exc()
    print("Error here")
    ...
finally:
    response = api_obj.terminate_session()
    print("Logged out")