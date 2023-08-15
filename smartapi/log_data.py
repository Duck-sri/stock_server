from pathlib import Path

import time
import threading
import traceback

import psycopg2 as psql
from psycopg2 import pool as psql_pool

import smartapi.utils as utils
from smartapi.configs import app_config
from smartapi.connections import SmartAPIConnect, SocketConnection
from smartapi.connections.api_types import *


PSQL_POOL = psql_pool.ThreadedConnectionPool(**app_config['server']['db'])

def run_query(query: str, one: bool = False):
    conn = PSQL_POOL.getconn()

    if conn:
        cur = conn.cursor()
        cur.execute(query)
        res = cur.fetchone() if one else cur.fetchall()
        cur.close()

    PSQL_POOL.putconn(conn)

    return res

upsert_sql = """
    INSERT INTO tick_data (token, time, price, volume)
    VALUES (%(token)s, %(time)s, %(price)s, %(volume)s)
    ON CONFLICT (token, time) DO UPDATE
    SET price = EXCLUDED.price, volume = EXCLUDED.volume;
"""

times = []

def on_data(_, data):
    data_to_upsert = {
        'token': data['token'],
        'time': data['exchange_timestamp'].strftime("%Y-%m-%d %H:%M:%S"),
        'price': data['last_traded_price'],
        'volume': int(data['volume_trade_for_the_day'])
    }

    start = time.perf_counter_ns()
    conn = PSQL_POOL.getconn()
    try:
        if conn:
            cur = conn.cursor()
            cur.execute(upsert_sql, data_to_upsert)
            cur.close()

        conn.commit()
    except:
        ...
    finally:
        PSQL_POOL.putconn(conn=conn)
        
    end = time.perf_counter_ns()
    elapsed = (end-start)
    times.append(elapsed)

    # print(f"Time taken : {elapsed/1e6 :.3f}")


token_map = utils.read_json(Path('/Users/you-know-who/Code/Project/stock_server/notebooks/token_map.json'))
subscribe_keys = set(token_map.keys())

def on_open(ws_conn):
    ws_obj.subscribe(
        str.ljust('try_1', 10),
        SubscriptionMode.QUOTE,
        exchange_token_map={
            # ExchangeType.NSE_FO : ['48105', '48326', '48022', '48399']
            ExchangeType.NSE_FO : list(subscribe_keys)
        }
    )
    print("Connected")
    print(subscribe_keys)


def on_error(ws_conn, err: str):
    # print("Closing here")
    ws_obj.close_connection()
    ws_obj.connect()

# if __name__ == '__main__':

from smartapi.configs import user_config

api_obj = SmartAPIConnect(
    client_code=user_config['client_code'],
    pin=user_config['angel_pin'],
    totp=user_config['keys']['qr_otp'],
    api_key=user_config['keys']['trading']
)

tokens = api_obj.generate_session()

ws_obj = SocketConnection(
    client_code=user_config['client_code'],
    jwt_token=tokens['jwtToken'],
    feed_token=tokens['feedToken'],
    api_key=user_config['keys']['feed']
)

ws_obj.on_close = lambda _: print("Connection Closed !!")
ws_obj.on_message = lambda _, data: print(f"Message recieved : {data} !!")

ws_obj.on_data = on_data
ws_obj.on_open = on_open
ws_obj.on_error = on_error

try:
    ws_obj.connect()

except KeyboardInterrupt:
    ws_obj.close_connection()
    api_obj.terminate_session()
    PSQL_POOL.closeall()

    if len(times) > 0:
        print(f"Avg Upsert time: {(sum(times)/(1e6*len(times))) :.3f}")
        print(f"Max: {max(times)/1e6 :.3f}")
        print(f"Min: {min(times)/1e6 :.3f}")

finally:
    ...