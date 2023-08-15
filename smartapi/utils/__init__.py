from pathlib import Path

import base64
import zlib
import json

import tomli
from datetime import datetime, timedelta

import struct

import socket
import requests

import traceback

# using some TA functions
from .indicators import *

def read_toml(file_path: Path) -> dict | None :
    if isinstance(file_path, str):
        file_path = Path(file_path).absolute()

    if not file_path.exists():
        raise FileNotFoundError("Dude wtf !!")

    with open(file_path.as_posix(), 'rb') as fp:
        data = tomli.load(fp)

    return data


def read_json(file_path: Path) -> dict | None :
    if isinstance(file_path, str):
        file_path = Path(file_path).absolute()

    if not file_path.exists():
        raise FileNotFoundError("Dude wtf !!")

    with open(file_path.as_posix(), 'rb') as fp:
        data = json.load(fp)

    return data

def get_public_ip(ip_check_url: str = None) -> str:
    if not isinstance(ip_check_url, str):
        ip_check_url = 'https://checkip.amazonaws.com'

    try:
        ip =  requests.get(ip_check_url).text.strip()
    except:
        print("Error in getting public ip ...")
        traceback.print_exc()
        ip = "127.0.0.1"

    return ip

def get_local_ip() -> str:
    return socket.gethostbyname(socket.gethostname())

def get_mac_address() -> str:
    import uuid, re
    return ':'.join(re.findall('..', '%012x' % uuid.getnode()))


def date_to_str(date_obj: datetime, date_format: str = '%Y-%m-%d %H:%M') -> str:
    return date_obj.strftime(date_format)

def unpack_binary_str(binary_data: str, start: int, end: int, endian: str = "<",byte_format="I"):
    return struct.unpack(
        endian+byte_format,
        binary_data[start: end]
    )