from configparser import ConfigParser
from pathlib import Path
from typing import Generator, List, Union

from src.audio.audio_client import AudioClient
from src.audio.types import SearchCriteria, Age


def get_audio_config(path: Union[str, Path] = "config.ini") -> ConfigParser:
    config = ConfigParser()
    config.read(path)
    return config


def parse_age_string(s: str, btw_chr: str = "-", in_btw_chr: str = ",") -> List[Age]:
    result: List[Age] = []
    for age in s.split(btw_chr):
        _from, to = age.split(in_btw_chr)
        result.append({"from": int(_from), "to": int(to)})
    return result


def parse_search_criteria(config: ConfigParser, section: str) -> SearchCriteria:
    """Парсинг критериев поиска - как в браузере HAR файле"""
    criteria: SearchCriteria = {
        "group": 0,
        "userSex": "ANY",
        "peerSex": "ANY",
    }
    user_sex = config.get(section, "sex", fallback=None)
    search_sex = config.get(section, "search-sex", fallback=None)
    user_age = config.get(section, "age", fallback=None)
    search_age = config.get(section, "search-age", fallback=None)
    
    if user_sex and search_sex:
        criteria["userSex"] = user_sex.upper()
        criteria["peerSex"] = search_sex.upper()
    
    if user_age and search_age:
        criteria["userAge"] = parse_age_string(user_age)[0]
        criteria["peerAges"] = parse_age_string(search_age)
    
    return criteria


def parse_audio_clients(
    path: Union[str, Path] = "config.ini",
) -> Generator[AudioClient, None, None]:
    config = get_audio_config(path=path)
    names_of_clients = config.get("audio", "clients", fallback="").strip()
    if not names_of_clients:
        return
    normalized = names_of_clients.replace(",", " ")
    for name in [item for item in normalized.split() if item]:
        option = f"audio/client/{name}"
        token = config.get(option, "token", fallback=None)
        if not token:
            token = config.get(option, "user_id")
        ua = config.get(option, "ua")
        proxy = config.get(option, "proxy", fallback=None)
        wait_for = config.get(option, "wait-for", fallback=None)
        yield AudioClient(
            name=name,
            user_id=token,
            ua=ua,
            search_criteria=parse_search_criteria(config, option),
            wait_for=wait_for,
            proxy=proxy,
        )
