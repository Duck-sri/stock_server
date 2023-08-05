import json

import ssl
import socket
import websocket

from datetime import datetime, timedelta

import threading

from collections import defaultdict

import utils
from api_types import SubscribeAction, SubscriptionMode, ExchangeType

class SocketConnection:

    ROOT_URL = "ws://smartapisocket.angelone.in/smart-stream"
    HEART_BEAT_MESSAGE = "ping"
    HEART_BEAT_RESPONSE = "pong"
    HEART_BEAT_INTERVAL = 25     # Adjusted to 10s
    LITTLE_ENDIAN_BYTE_ORDER = "<"
    RESUBSCRIBE_FLAG = False
    # HB_THREAD_FLAG = True

    # Available Actions
    SUBSCRIBE_ACTION = 1
    UNSUBSCRIBE_ACTION = 0

    # Possible Subscription Mode
    LTP_MODE = 1
    QUOTE = 2
    SNAP_QUOTE = 3

    # Exchange Type
    NSE_CM = 1
    NSE_FO = 2
    BSE_CM = 3
    BSE_FO = 4
    MCX_FO = 5
    NCX_FO = 7
    CDE_FO = 13

    # Subscription Mode Map
    SUBSCRIPTION_MODE_MAP = {
        1: "LTP",
        2: "QUOTE",
        3: "SNAP_QUOTE"
    }


    CONNECTION_ACTIVE = False

    # dict[mode : {exchange : [tokens]}]
    # input_request_dict = defaultdict(lambda : {})
    mode_exchange_tokens_map: dict[SubscriptionMode: dict[ExchangeType: list[str]]] = defaultdict(lambda : {})
    current_retry_attempt = 0

    def __init__(self, client_code:str, jwt_token: str, feed_token: str, api_key: str) -> None:

        # TODO unify all these user stuff into an User object
        self.__client_code = client_code
        self.__jwt_token = jwt_token
        self.__feed_token = feed_token
        self.__api_key = api_key


        self._ws_conn = None

        self._last_ping_timestamp = None
        self._last_pong_timestamp = None
        self.MAX_RETRY_ATTEMPT = 2


        self.on_open = None
        self.on_close = None
        self.on_message = None
        self.on_data = None
        self.on_error = None

    def send(self, data: dict) -> bool:
        "Send dict to binary - JSON data"
        b_data = json.dumps(data).encode('latin-1')
        self._ws_conn.send(b_data)
        return True

    def connect(self):
        """ Make the web socket connection with the server """

        if self.CONNECTION_ACTIVE or (self._ws_conn is not None):
            print("Already exists an active connection!!!")
            return

        headers = {
            "Authorization": self.__jwt_token,
            "x-api-key": self.__api_key,
            "x-client-code": self.__client_code,
            "x-feed-token": self.__feed_token
        }

        self._ws_conn = websocket.WebSocketApp(
            self.ROOT_URL, 
            header=headers, 
            on_open=self.__handle_open,
            on_close=self.__handle_close,
            on_data=self.__handle_data,
            on_ping=self.__handle_ping,
            on_pong=self.__handle_pong,
            on_error=self.__handle_error,
        )

        self.CONNECTION_ACTIVE = True

        # does all the heartbeat stuff ??!?
        self._ws_conn.run_forever(
            sslopt={
                "cert_reqs": ssl.CERT_NONE
            },
            ping_interval=self.HEART_BEAT_INTERVAL,
            ping_payload=self.HEART_BEAT_MESSAGE
        )

    def close_connection(self):
        "Closes connection"
        self.RESUBSCRIBE_FLAG = False

        # TODO add logs
        if self._ws_conn and self.CONNECTION_ACTIVE:
            self._ws_conn.close()
            self.CONNECTION_ACTIVE = False

    def send(self, data: dict):
        "Sends the given in json string to server"
        self._ws_conn.send(json.dumps(data))

    def subscribe(self, correlation_id: str, mode: SubscriptionMode, exchange_token_map: dict[ExchangeType: list[str]]):
        """
            Subscribe for given tokens from the server

            Args:
                correlation_id: A 10 character alphanumeric ID client 
                mode:           Specifies LTP | Quote | Snap
                exchange_token_map:     dicts of exchange type and tokens
                    {
                        ExchangeType.NSE : ["10525", "5290"],
                        ExchangeType.FCO : [ "234230", "234235", "234219"],
                    }

                this will be converted to: 
                    [
                        { "exchangeType": 1, "tokens": ["10626", "5290"]},
                        {"exchangeType": 5, "tokens": [ "234230", "234235", "234219"]}
                    ]
        """
        request_data = {
            "correlationID": correlation_id,
            "action": SubscribeAction.SUBSCRIBE.value,
            "params": {
                "mode": mode.value,
                "tokenList": [
                    {"exchangeType": exchange.value, "tokens": tokens} for exchange, tokens in exchange_token_map.items()
                ]
            }
        }

        # dict[mode : {exchange : [tokens]}]
        # self.mode_exchange_tokens_map

        # having an account of all the items in subscriptions
        for exchange_type, tokens in exchange_token_map.items():
            if exchange_type in self.mode_exchange_tokens_map[mode]:
                self.mode_exchange_tokens_map[mode][exchange_type].extend(tokens)
            else:
                self.mode_exchange_tokens_map[mode][exchange_type] = tokens

        self.send(request_data)
        self.RESUBSCRIBE_FLAG = True

    def resubscribe(self):
        "Re-subscribe to all tokens in each mode"

        # for key, val in self.mode_exchange_tokens_map.items():
        for mode, exchange_tokens_map in self.mode_exchange_tokens_map.items():
            token_list = []
            for exchange_type, tokens in exchange_tokens_map.items():
                if len(tokens) == 0: continue
                temp_data = {
                    'exchangeType': exchange_type.value,
                    'tokens': tokens
                }
                token_list.append(temp_data)

            if len(token_list) == 0:
                return

            request_data = {
                "action": SubscribeAction.SUBSCRIBE.value,
                "params": {
                    "mode": mode.value,
                    "tokenList": token_list
                }
            }
            self.send(request_data)

    def unsubscribe(self, correlation_id: str, mode: SubscriptionMode, token_list: dict):
        request_data = {
            "correlationID": correlation_id,
            "action": SubscribeAction.UNSUBSCRIBE.value,
            "params": {
                "mode": mode.value,
                "tokenList": token_list
            }
        }

        self._ws_conn.send(json.dumps(request_data))

        for _ in token_list.items():
            exchange_type, tokens = _['exchangeType'], _['tokens']
            
            # remove the tokens
            for token in tokens:
                self.mode_exchange_tokens_map[mode][exchange_type].remove(token)

        self.RESUBSCRIBE_FLAG = True

    def _parse_token_value(self, binary_str: str) -> str:
        "Parse till \x00 for token information"
        token = ""
        for char in map(chr, binary_str):
            if char == '\x00':
                return token

            token += char

        return token

    def _parse_best_5_buy_and_sell_data(self, binary_data):

        def split_packets(binary_packets):
            packets = []

            i = 0
            while i < len(binary_packets):
                packets.append(binary_packets[i: i+20])
                i += 20
            return packets

        best_5_buy_sell_packets = split_packets(binary_data)

        best_5_buy_data = []
        best_5_sell_data = []

        for packet in best_5_buy_sell_packets:
            each_data = {
                "flag": utils.unpack_binary_str(packet, 0, 2, byte_format="H")[0],
                "quantity": utils.unpack_binary_str(packet, 2, 10, byte_format="q")[0],
                "price": utils.unpack_binary_str(packet, 10, 18, byte_format="q")[0] / 100,
                "no of orders": utils.unpack_binary_str(packet, 18, 20, byte_format="H")[0]
            }

            if each_data["flag"] == 0:
                best_5_buy_data.append(each_data)
            else:
                best_5_sell_data.append(each_data)

        return {
            "best_5_buy_data": best_5_buy_data,
            "best_5_sell_data": best_5_sell_data
        }

    def _parse_binary_data(self, binary_data: str):
        """
            Unpacks binary data to a specified dict format
            refer: https://smartapi.angelbroking.com/docs/WebSocket2

            Args:
                binary_data:    Binary response from server

            returns:
                dict of all specified data
        """

        parsed_data = {
           "subscription_mode" : utils.unpack_binary_str(binary_data, 0, 1, byte_format="B")[0],
           "exchange_type": utils.unpack_binary_str(binary_data, 1, 2, byte_format="B")[0],
           "token": self._parse_token_value(binary_data[2:27]),
           "sequence_number": utils.unpack_binary_str(binary_data, 27, 35, byte_format="q")[0],
           "exchange_timestamp": utils.unpack_binary_str(binary_data, 35, 43, byte_format="q")[0],
           "last_traded_price": utils.unpack_binary_str(binary_data, 43, 51, byte_format="q")[0] / 100,
        }

        # TODO add way to show token and also the symbol name in the parsed data
        exchange_time = datetime.fromtimestamp(parsed_data['exchange_timestamp']/1000)
        parsed_data['exchange_timestamp'] = exchange_time
        parsed_data['exchange_timestring'] = datetime.strftime(exchange_time,"%Y-%b-%d %H:%M:%S")

        if parsed_data["subscription_mode"] in [SubscriptionMode.QUOTE, SubscriptionMode.SNAP_QUOTE]:
            parsed_data["last_traded_quantity"] = utils.unpack_binary_str(binary_data, 51, 59, byte_format="q")[0]
            parsed_data["average_traded_price"] = utils.unpack_binary_str(binary_data, 59, 67, byte_format="q")[0]/ 100
            parsed_data["volume_trade_for_the_day"] = utils.unpack_binary_str(binary_data, 67, 75, byte_format="q")[0]
            parsed_data["total_buy_quantity"] = utils.unpack_binary_str(binary_data, 75, 83, byte_format="d")[0]
            parsed_data["total_sell_quantity"] = utils.unpack_binary_str(binary_data, 83, 91, byte_format="d")[0]
            parsed_data["open_price_of_the_day"] = utils.unpack_binary_str(binary_data, 91, 99, byte_format="q")[0] / 100
            parsed_data["high_price_of_the_day"] = utils.unpack_binary_str(binary_data, 99, 107, byte_format="q")[0] / 100
            parsed_data["low_price_of_the_day"] = utils.unpack_binary_str(binary_data, 107, 115, byte_format="q")[0] / 100
            parsed_data["closed_price"] = utils.unpack_binary_str(binary_data, 115, 123, byte_format="q")[0] / 100

        if parsed_data["subscription_mode"] == SubscriptionMode.SNAP_QUOTE:
            parsed_data["last_traded_timestamp"] = utils.unpack_binary_str(binary_data, 123, 131, byte_format="q")[0]
            parsed_data["open_interest"] = utils.unpack_binary_str(binary_data, 131, 139, byte_format="q")[0]
            parsed_data["open_interest_change_percentage"] = utils.unpack_binary_str(binary_data, 139, 147, byte_format="q")[0]
            parsed_data["upper_circuit_limit"] = utils.unpack_binary_str(binary_data, 347, 355, byte_format="q")[0]
            parsed_data["lower_circuit_limit"] = utils.unpack_binary_str(binary_data, 355, 363, byte_format="q")[0]
            parsed_data["52_week_high_price"] = utils.unpack_binary_str(binary_data, 363, 371, byte_format="q")[0]
            parsed_data["52_week_low_price"] = utils.unpack_binary_str(binary_data, 371, 379, byte_format="q")[0]

            # TODO implement the best 5 buy and sell for the API - UI thing
            best_5_buy_and_sell_data = self._parse_best_5_buy_and_sell_data(binary_data[147:347])
            parsed_data["best_5_buy_data"] = best_5_buy_and_sell_data["best_5_buy_data"]
            parsed_data["best_5_sell_data"] = best_5_buy_and_sell_data["best_5_sell_data"]

        return parsed_data


    def __handle_error(self, ws_conn, error: str):
        self.RESUBSCRIBE_FLAG = True
        
        self.on_error(ws_conn, error)

        if self.current_retry_attempt < self.MAX_RETRY_ATTEMPT:
            print("Trying to reconnect/resubscribe")
            self.current_retry_attempt += 1

            try:
                self.close_connection()
                self.connect()
            except Exception as err:
                print("Error occured while reconnect/resubscribe")

    def __handle_open(self, ws_conn):
        if self.RESUBSCRIBE_FLAG:
            self.resubscribe()
            self.RESUBSCRIBE_FLAG = False
        else:
            self.on_open(ws_conn)

    def __handle_close(self, ws_conn, *args):
        "Calls user defined on_close function"
        self.on_close(ws_conn, *args)
        self.close_connection()

    def __handle_data(self, ws_conn, data, data_type, continue_flag: bool):
        if data_type == 2:
            msg = self._parse_binary_data(data)
        else:
            msg = data

        if msg == b'\x00':
            return

        self.on_data(ws_conn, msg)

    def __handle_message(self, ws_conn, message: str):
        if message != self.HEART_BEAT_RESPONSE:
            msg = self._parse_binary_data(msg)
            self.on_message(ws_conn, msg)
        else:
            self.on_message(ws_conn, message)

    def __handle_ping(self, ws_conn, data):
        now = datetime.now()
        print(f"Ping function: [Data] {data}, [Timestamp] {now.strftime('%d-%m-%y %H:%M:%S')}")
        self._last_ping_timestamp = now

    def __handle_pong(self, ws_conn, data):
        if data == b'\x00':
            now = datetime.now()
            print(f"Pong function:, [Timestamp] {now.strftime('%d-%m-%y %H:%M:%S')}")
            self._last_pong_timestamp = now

        else:
            # if not a pong - send to handle data
            self.on_data(ws_conn, data)


if __name__ == '__main__':
    from pathlib import Path

    import pandas as pd
    from collections import defaultdict
    from pprint import pprint
    from api_types import TransactionType, Exchange, Variety, ProductType, OrderType, Duration, Interval, Order

    from ram_connect import SmartAPIConnect
    import traceback

    user_config = utils.read_toml(Path("./.config/user.toml").absolute())

    api_obj = SmartAPIConnect(
        client_code=user_config['client_code'],
        pin=user_config['angel_pin'],
        totp=user_config['keys']['qr_otp'],
        api_key=user_config['keys']['trading']
    )

    session_data = api_obj.generate_session()


    dfs = defaultdict(lambda: pd.DataFrame({
        'time' : [],
        'price' : [],
        'total_volume' : [],
    }).set_index('time'))

    def on_data(_, data):
        token = data['token']
        price = data['last_traded_price']
        # buys = data['total_buy_quantity']
        # sells = data['total_sell_quantity']
        time = data['exchange_timestamp']
        volume = data['volume_trade_for_the_day']

        # prev_idx = None

        # if len(dfs[token]) > 1:
        #     prev_idx = len(dfs[token])-1
        #     if (dfs[token].index[prev_idx] == time) and prev_idx > 0:
        #         prev_idx -= 1
        #     else:
        #         prev_idx = None

        # if prev_idx is not None:
        #     price_change = price - dfs[token]['price'].iloc[prev_idx]
        #     # buy_change = buys - dfs[token]['buy_q'].iloc[prev_idx]
        #     # sell_change = sells - dfs[token]['sell_q'].iloc[prev_idx]
        #     volume_change = volume - dfs[token]['total_volume'].iloc[prev_idx]
        # else:
        #     price_change = 0
        #     # buy_change = 0
        #     # sell_change = 0
        #     volume_change = 0


        dfs[token].at[time, 'price'] = price
        # dfs[token].at[time, 'buy_q'] = buys
        # dfs[token].at[time, 'sell_q'] = sells
        dfs[token].at[time, 'total_volume'] = volume

        # dfs[token].at[time, 'price_change'] = price_change
        # dfs[token].at[time, 'buy_change'] = buy_change
        # dfs[token].at[time, 'sell_change'] = sell_change
        # dfs[token].at[time, 'volume'] = volume_change

        # pprint(data, indent=1)
        print(dfs[token])
        print()

    try:
        ws_obj = SocketConnection(
            client_code=user_config['client_code'],
            jwt_token=session_data['jwtToken'],
            feed_token=session_data['feedToken'],
            api_key=user_config['keys']['trading']
        )

        ws_obj.on_open = lambda _: print("Connection Opened !!")
        ws_obj.on_close = lambda _: print("Connection Closed !!")
        ws_obj.on_error = lambda _, err: print(f"Connection Error: {err} !!")
        ws_obj.on_message = lambda _, data: print(f"Message recieved : {data} !!")

        # ws_obj.on_data = lambda _, data: print(f"Data recieved : \n{data}", end='\n\n')
        ws_obj.on_data = on_data

        def on_open(ws_conn):
            print("Connection opened")
            ws_obj.subscribe(
                str.ljust('try_1', 10),
                SubscriptionMode.QUOTE,
                exchange_token_map={
                    # ExchangeType.NSE_FO : ['42765', '42938', '42927', '43002']
                    # ExchangeType.NSE_FO : ['42884'],
                    ExchangeType.NSE_CM : ['1333', '11386', '4963', '5900', ''],
                }
            )

        ws_obj.on_open = on_open
        ws_obj.connect()

        # time.sleep(30)
    except:
        traceback.print_exc()

    finally:
        api_obj.terminate_session()