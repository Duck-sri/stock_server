from pathlib import Path

import time
import datetime
import json
import pandas as pd

import requests
from http import HTTPMethod
from urllib.parse import urljoin
from urllib3.exceptions import InsecureRequestWarning

import logging
import traceback

import pyotp
import utils
from api_types import Order, Exchange, Variety, Interval, SocketTask

# FIXME better way to read configs
angel_config = utils.read_toml(Path("./.config/angle_one_config.toml").absolute())

# FIXME add logger class for all the transactions performed
class SmartAPIConnect:
    """
        Encapsulates all the HTTP transactions between the AngleOne's Smart Api
    """

    # TODO add simulation with all checks with margin and stuff
    SIMULATION = True

    ERROR_MAP = angel_config['errors']
    TIMEOUT = angel_config['timeout']

    URLS = angel_config['urls']
    ROOT_URL = URLS['root']

    DISABLE_SSL = True

    SESSION_ACTIVE = False

    def __init__(self, client_code: str, pin: str, totp: str, api_key: str) -> None:
        """
            Args:
                client_code: Code from the AngelOne portal
                pin:         Mobile pin used to login
                totp:        QR code value while enabling totp
                api_key:     App api key
        """

        # FIXME  add checks to see it values are null / empty-string
        self.__client_code = client_code
        self.__client_pin = pin
        self.__client_totp_obj = pyotp.TOTP(totp)
        self.__client_api_key = api_key

        self.__access_token = None
        self.__refresh_token = None
        self.__feed_token = None

        self._public_ip = utils.get_public_ip()
        self._local_ip = utils.get_local_ip()
        self._mac_address = utils.get_mac_address()

        self.proxies = None

        if self.DISABLE_SSL:
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

        # TODO add a http connection/session object
        self._http_session = None

    @property
    def _headers(self) -> dict:
        "Return HTTP request headers"
        headers = {
            "Content-type": "application/json",
            "X-ClientLocalIP": self._local_ip,
            "X-ClientPublicIP": self._public_ip,
            "X-MACAddress": self._mac_address,
            "Accept": "application/json",
            "X-PrivateKey": self.__client_api_key,
            "X-UserType": "USER",
            "X-SourceID": "WEB"
        }

        if self.__access_token != None:
            headers['Authorization'] = f"Bearer {self.__access_token}"

        return headers

    @property
    def _login_url(self) -> str:
        return f"{self.URLS['publisher_login']}?api_key={self.__client_api_key}"


    def session_expiry_hook(self):
        # TODO implement session expiry hook - regenerate token IG ??
        self._refesh_access_token(self.__refresh_token)

    @staticmethod
    def load_lookup_table() -> pd.DataFrame:
        "Loads & saves the lookup table from angleone for symbols and symboltokens wiz used for trading further"
        lookup_dir = Path('./.lookup').absolute()
        lookup_dir.mkdir(exist_ok=True, parents=True)

        time_now = datetime.datetime.now()
        week_no = time_now.isocalendar().week
        year_no = time_now.year
        
        file_name = f"{year_no}_week_{week_no}.csv"

        lookup_file = lookup_dir.joinpath(file_name)

        if lookup_file.exists():
            df = pd.read_csv(lookup_file.as_posix())
        else:
            print("Making a request")
            # response = requests.get(angel_config['urls']['symboltoken_lookup'], verify=False)
            # print(response.status_code)
            df = pd.read_json(angel_config['urls']['symboltoken_lookup'])
            dtype_dict = {
                'token' : str,
                'symbol' : str,
                'name' : str,
                'expiry' : str,
                'strike' : float,
                'lotsize' : int,
                'instrumenttype' : str,
                'exch_seg' : str,
                'tick_size' : int,
            }

            df = df.astype(dtype_dict)
            df['expiry'] = df['expiry'].map(lambda date_str: datetime.datetime.strptime(date_str, '%d%b%Y').replace(hour=15, minute=15, second=0) if len(date_str) > 0 else None)
            df.to_csv(lookup_file.as_posix(), index=False)

            print(f'Saved file to : {lookup_file}')

        return df

    def request(self, route: str, method: HTTPMethod, params: dict = None, abs_url: bool = False) -> dict:
        """
            Generic function for making a request

            Args:
                route:   url to make the request - relative to root url
                method:  HTTP method
                params:  (optional) body/query for the request
                abs_url: (optional) if the given url is absolute

            Returns:
                decoded json response
        """
        
        if method.value in ["POST", "PUT"]:
            data = json.dumps(params)
            params = None
        elif method.value in ["GET", "DELETE"]:
            data = None
            params = json.dumps(params)

        headers = self._headers

        url = route if abs_url else urljoin(self.ROOT_URL, route)

        # TODO add debug log
        response = requests.request(
            method=method.value,
            url=url,
            data=data,
            params=params,
            headers=headers,
            verify=not self.DISABLE_SSL,
            allow_redirects=True,
            timeout=self.TIMEOUT,
            proxies=self.proxies
        )

        # parse response content
        try:
            data: dict | None = json.loads(response.content.decode('utf-8'))
        except ValueError:
            # TODO add debug/error log
            print(response.status_code)
            print(response.content.decode('utf-8'))
            raise ValueError("Couldn't parse json from the request response")

        # check for errors
        if  (data.get('errorCode') != '') and (data.get('success') == False):
            # check if token is expired
            if (data["errorCode"] == "AG8002"):
                self.session_expiry_hook()
                
                # fixing expired token and again making a request
                return self.request(
                    route=route,
                    method=method,
                    params=params,
                    abs_url=abs_url
                )

            error_name = self.ERROR_MAP[data['errorCode']]
            # native errors
            # TODO add debug/error log
            raise Exception(data['message'])

        elif data.get('status') == False and data.get('errorcode', '') != '':
            if data['errorcode'] == "AG8002":
                self.session_expiry_hook()

                # fixing expired token and again making a request
                return self.request(
                    route=route,
                    method=method,
                    params=params,
                    abs_url=abs_url
                )
            raise(Exception(data['message']))

        return data

    # TODO add RMS Limit checking
    # refer: https://smartapi.angelbroking.com/docs/User#Funds

    def generate_session(self):
        """ Generate a session for the client """

        params = {
            "clientcode": self.__client_code,
            "password": self.__client_pin,
            "totp": self.__client_totp_obj.now()
        }

        login_response = self.request(
            route=self.URLS['login'],
            method=HTTPMethod.POST,
            params=params
        )
        time.sleep(.5)

        self.SESSION_ACTIVE = True

        data = login_response['data']
        self.__access_token = data['jwtToken']
        self.__refresh_token = data['refreshToken']
        self.__feed_token = data['feedToken']

        return data

    def _refesh_access_token(self, refresh_token: str) -> None:
        "Updates all token with refresh token"
        response = self.request(
            route=self.URLS['generate_tokens'],
            method=HTTPMethod.POST,
            params={
                "refreshToken": refresh_token
            }
        )

        # TODO add logs for updating tokens
        self.__access_token = response['data']['jwtToken']
        self.__feed_token = response['data']['feedToken']
        self.__refresh_token = response['data']['refreshToken']
        print("Testing refesh response", response)


    def terminate_session(self) -> dict:
        "Calls logout api"

        response = self.request(
            route=self.URLS['logout'],
            method=HTTPMethod.POST,
            params={
                "clientcode": self.__client_code
            }
        )
        self.SESSION_ACTIVE = False

        return response


    def get_profile(self, token: str) -> dict:
        """
            Makes a request to get user profile

            Args:
                token:  Referesh token

            Returns:
                An user JSON-object
        """

        user = self.request(
            route=self.URLS['get_profile'],
            method=HTTPMethod.GET,
            params={
                "refreshToken": token
            }
        )

        return user


    # TODO implement GTT
    # refer: https://smartapi.angelbroking.com/docs/Gtt


    def place_order(self, order: Order) -> dict:
        """
            Create order

            Args:
                order:  An `Order` object containing all details
        
        """

        params = order.to_dict()

        # if self.SIMULATION:
        #     print(f"[SIMULATION] Placed order for price: {order.price}")

        order_response = self.request(
            route=self.URLS['order']['place'],
            method=HTTPMethod.POST,
            params=params
        )

        order_id = order_response['data']['orderid']

        # TODO add logs
        print("Placed order")
        print(f"Order ID: {order_id}")

        return order_response

    def modify_order(self, order: Order) -> dict:

        params = order.to_dict()
        
        response = self.request(
            route=self.URLS['order']['modify'],
            method=HTTPMethod.POST,
            params=params
        )

        # TODO add logs
        return response

    def cancel_order(self, order_id: str, variety: Variety) -> dict:

        params = {
            "variety" : variety.value.upper(),
            "orderid" : order_id
        }

        response = self.request(
            route=self.URLS['order']['cancel'],
            method=HTTPMethod.POST,
            params=params
        )

        return response

    def get_order_book(self) -> dict:
        return self.request(
            route=self.URLS['order']['order_book'],
            method=HTTPMethod.GET,
            params=''
        )['data']

    def get_trade_book(self) -> dict:
        return self.request(
            route=self.URLS['order']['trade_book'],
            method=HTTPMethod.GET,
            params=''
        )['data']

    def get_position(self) -> dict:
        return self.request(
            route=self.URLS['order']['position'],
            method=HTTPMethod.GET,
            params=''
        )['data']

    def get_holdings(self) -> dict:
        return self.request(
            route=self.URLS['holding'],
            method=HTTPMethod.GET,
            params=''
        )['data']


    def get_ltp(self, exchange: Exchange, symbol: str, symbol_token: str) -> dict:
        return self.request(
            route=self.URLS['order']['ltp'],
            method=HTTPMethod.POST,
            params={
                "exchange": exchange.value.upper(),
                "tradingsymbol": symbol,
                "symboltoken": symbol_token
            }
        )['data']


    def get_candle_data(self, exchange: Exchange, symbol_token: str, interval: Interval, start_date: datetime.datetime, end_date: datetime.datetime) -> pd.DataFrame:
        params = {
            "exchange": exchange.value.upper(),
            "symboltoken": symbol_token,
            "interval": interval.value.upper(),
            "fromdate": utils.date_to_str(start_date),
            "todate": utils.date_to_str(end_date)
        }

        response = self.request(
            route=self.URLS['historical']['candle'],
            method=HTTPMethod.POST,
            params=params
        )

        data = response['data']
        if data is None:
            print("Invalid token or date range")
            return pd.DataFrame({
                'time' : [],
                'open' : [],
                'high' : [],
                'close' : [],
                'low' : [],
            }).set_index('time')

        df = pd.DataFrame.from_dict(data)
        df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
        df['time'] = pd.to_datetime(df['time'])
        df.drop(['volume'], axis=1, inplace=True)
        df.set_index('time', inplace=True)

        return df

if __name__ == '__main__':
    from pprint import pprint
    from api_types import TransactionType, Exchange, Variety, ProductType, OrderType, Duration, Interval, Order

    user_config = utils.read_toml(Path("./.config/user.toml").absolute())

    api_obj = SmartAPIConnect(
        client_code=user_config['client_code'],
        pin=user_config['angel_pin'],
        totp=user_config['keys']['qr_otp'],
        api_key=user_config['keys']['trading']
    )

    session_data = api_obj.generate_session()

    try:
        today = datetime.datetime.today().replace(hour=9, minute=15, second=0, microsecond=0)
        start_date = today - datetime.timedelta(days=3) + datetime.timedelta(hours=6, minutes=0)
        end_date = start_date + datetime.timedelta(minutes=15)

        print(start_date)
        print(end_date)

        # api_obj.load_lookup_table()
        res = api_obj.get_candle_data(exchange=Exchange.NFO, symbol_token='48326', interval=Interval.ONE_MINUTE, start_date=start_date, end_date=end_date)
        print(res)

    except:
        traceback.print_exc()
        print("Error here")
        ...
    finally:
        response = api_obj.terminate_session()
        print("Logged out")