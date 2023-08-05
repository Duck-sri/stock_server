from enum import StrEnum, IntEnum
from dataclasses import dataclass, asdict

from datetime import datetime

class TransactionType(StrEnum):
    BUY = 'BUY'
    SELL = 'SELL'

class Exchange(StrEnum):
    BSE = 'BSE'
    NSE = 'NSE'
    NFO = 'NFO'
    MCX = 'MCX'

class ExchangeType(IntEnum):
    NSE_CM = 1
    NSE_FO = 2
    BSE_CM = 3
    BSE_FO = 4
    MCX_FO = 5
    NCX_FO = 7
    CDE_FO = 13

ExchangeMap = {
    ExchangeType.NSE_CM: Exchange.NSE,
    ExchangeType.NSE_FO: Exchange.NFO,
    ExchangeType.BSE_CM: Exchange.BSE,
    ExchangeType.MCX_FO: Exchange.MCX
}

class Variety(StrEnum):
    NORMAL = 'NORMAL'
    STOPLOSS = 'STOPLOSS'
    AMO = 'AMO'
    ROBO = 'ROBO'

class ProductType(StrEnum):
    DELIVERY = 'DELIVERY'
    CARRYFORWARD = 'CARRYFORWARD'
    MARGIN = 'MARGIN'
    INTRADAY = 'INTRADAY'
    BO = 'BO'

class OrderType(StrEnum):
    MARKET = 'MARKET'
    LIMIT = 'LIMIT'
    STOPLOSS_LIMIT = 'STOPLOSS_LIMIT'
    STOPLOSS_MARKET = 'STOPLOSS_MARKET'

class Duration(StrEnum):
    DAY = 'DAY'
    IOC = 'IOC'

class Interval(StrEnum):
    ONE_MINUTE = 'ONE_MINUTE'
    THREE_MINUTE = 'THREE_MINUTE'
    FIVE_MINUTE = 'FIVE_MINUTE'
    TEN_MINUTE = 'TEN_MINUTE'
    FIFTEEN_MINUTE = 'FIFTEEN_MINUTE'
    THIRTY_MINUTE = 'THIRTY_MINUTE'
    ONE_HOUR = 'ONE_HOUR'
    ONE_DAY = 'ONE_DAY'


class SocketTask(StrEnum):
    CONNECT = 'cn'
    HEARTBEAT = 'hb'
    MARKET_WATCH = 'mw'
    SUBSCRIBE_INDEX = 'sfi'
    MARKET_DEPTH = 'dp'


class SubscribeAction(IntEnum):
    SUBSCRIBE = 1
    UNSUBSCRIBE = 0

class SubscriptionMode(IntEnum):
    LTP_MODE = 1
    QUOTE = 2
    SNAP_QUOTE = 3


# all limits are days worth of data
DAY_LIMITS = {
    Interval.ONE_MINUTE : 30,
    Interval.THREE_MINUTE : 90,
    Interval.FIVE_MINUTE : 90,
    Interval.TEN_MINUTE : 90,
    Interval.FIFTEEN_MINUTE : 180,
    Interval.THIRTY_MINUTE : 180,
    Interval.ONE_HOUR : 365,
    Interval.ONE_DAY : 2000
}

@dataclass
class Order:

    tradingsymbol: str
    symboltoken: str
    quantity: str

    # The min or max price to execute the order at (for LIMIT orders)
    price: str = ''

    variety: Variety = None
    transactiontype: TransactionType = None
    exchange: Exchange = None
    ordertype: OrderType = None
    producttype: ProductType = None
    duration: Duration = None

    # only SL & SL-M
    triggerprice : str = ''

    # only ROBO
    squareoff: str = ''
    stoploss: str = ''
    trailingStopLoss: str = ''

    # waste
    ordertag: str = ''
    disclosedquantity: str = ''

    def to_dict(self) -> dict:
        return_dict = {}
        for key, value in asdict(self).items():
            if isinstance(value, StrEnum):
                return_dict[key] = value.value.upper()
            elif isinstance(value, int):
                return_dict[key] = str(value)
            elif isinstance(value, float):
                return_dict[key] = f"{value :.2f}"
            elif isinstance(value, str) and len(value) != 0:
                return_dict[key] = value
            else:
                # not taking null and false data
                continue

        return return_dict

class TickInterval(Enum):
    ONE_MINUTE = timedelta(minutes=1)
    THREE_MINUTE = timedelta(minutes=3)
    FIVE_MINUTE = timedelta(minutes=5)
    TEN_MINUTE = timedelta(minutes=10)
    FIFTEEN_MINUTE = timedelta(minutes=15)
    THIRTY_MINUTE = timedelta(minutes=30)
    ONE_HOUR = timedelta(hours=1)
    ONE_DAY = timedelta(days=1)

@dataclass
class Stock:
    exchange: Exchange = None
    tradingsymbol: str = None
    symboltoken: str = None

    def __repr__(self) -> str:
        return f"<{self.exchange.value.upper()}:{self.tradingsymbol}>"

@dataclass
class Price:
    open: float = 0
    high: float = 0
    close: float = 0
    low: float = 0
    ltp: float = 0

    stock: Stock = None

    time: datetime = None

    @classmethod
    def from_dict(cls, data):
        stock = Stock(
            exchange=Exchange[data['exchange']],
            tradingsymbol=data['tradingsymbol'],
            symboltoken=data['symboltoken']
        )
        return cls(
            open=float(data['open']),
            high=float(data['high']),
            close=float(data['close']),
            low=float(data['low']),
            ltp=float(data['ltp']),
            stock=stock
        )

if __name__ == '__main__':
    order = Order(
        variety=Variety.NORMAL,
        transactiontype=TransactionType.BUY,
        symboltoken="3045",
        tradingsymbol="SBIN-EQ",
        exchange=Exchange.NSE,
        ordertype=OrderType.MARKET,
        producttype=ProductType.INTRADAY,
        duration=Duration.DAY,
        price=195.4,
        squareoff=0,
        stoploss=0,
        quantity=1
    )

    data = {
        "exchange":"NSE",
        "tradingsymbol":"SBIN-EQ",
        "symboltoken":"3045",
        "open":"186",
        "high":"191.25",
        "low":"185",
        "close":"187.80",
        "ltp":"191",
    }

    print(Price.from_dict(data))
    print(order.to_dict())
