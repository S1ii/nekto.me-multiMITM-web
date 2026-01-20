"""
Config management module - hot reload support
"""
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, List, Any
import asyncio

from src.client import Client
from src.audio.audio_client import AudioClient
from src.audio.config import parse_search_criteria


CONFIG_PATH = Path("config.ini")


def read_config() -> ConfigParser:
    """Read current config from file"""
    config = ConfigParser()
    config.read(CONFIG_PATH)
    return config


def write_config(config: ConfigParser):
    """Write config to file"""
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)


def get_text_clients_config() -> List[Dict[str, Any]]:
    """Get all text chat clients from config"""
    config = read_config()
    clients_list = []
    
    client_names = config.get("settings", "clients", fallback="").split()
    
    for name in client_names:
        section = f"client/{name}"
        if config.has_section(section):
            client_data = {
                "name": name,
                "token": config.get(section, "token"),
                "ua": config.get(section, "ua"),
                "sex": config.get(section, "sex", fallback=None),
                "wish_sex": config.get(section, "wish-sex", fallback=None),
                "age": config.get(section, "age", fallback=None),
                "wish_age": config.get(section, "wish-age", fallback=None),
                "role": config.get(section, "role", fallback=None),
                "adult": config.get(section, "adult", fallback=None),
                "wish_role": config.get(section, "wish-role", fallback=None),
            }
            clients_list.append(client_data)
    
    return clients_list


def get_audio_clients_config() -> List[Dict[str, Any]]:
    """Get all audio clients from config"""
    config = read_config()
    clients_list = []
    
    if not config.has_section("audio"):
        return clients_list
    
    client_names = config.get("audio", "clients", fallback="").strip().replace(",", " ").split()
    
    for name in client_names:
        section = f"audio/client/{name}"
        if config.has_section(section):
            client_data = {
                "name": name,
                "token": config.get(section, "token", fallback=None) or config.get(section, "user_id", fallback=None),
                "ua": config.get(section, "ua"),
                "sex": config.get(section, "sex", fallback=None),
                "search_sex": config.get(section, "search-sex", fallback=None),
                "age": config.get(section, "age", fallback=None),
                "search_age": config.get(section, "search-age", fallback=None),
                "wait_for": config.get(section, "wait-for", fallback=None),
                "proxy": config.get(section, "proxy", fallback=None),
            }
            clients_list.append(client_data)
    
    return clients_list


def update_text_client(name: str, data: Dict[str, Any]):
    """Update or create text client in config"""
    config = read_config()
    section = f"client/{name}"
    
    if not config.has_section(section):
        config.add_section(section)
    
    # Update fields
    if "token" in data:
        config.set(section, "token", data["token"])
    if "ua" in data:
        config.set(section, "ua", data["ua"])
    if "sex" in data and data["sex"]:
        config.set(section, "sex", data["sex"])
    if "wish_sex" in data and data["wish_sex"]:
        config.set(section, "wish-sex", data["wish_sex"])
    if "age" in data and data["age"]:
        config.set(section, "age", data["age"])
    if "wish_age" in data and data["wish_age"]:
        config.set(section, "wish-age", data["wish_age"])
    if "role" in data and data["role"] is not None:
        config.set(section, "role", str(data["role"]))
    if "adult" in data and data["adult"] is not None:
        config.set(section, "adult", str(data["adult"]))
    if "wish_role" in data and data["wish_role"]:
        config.set(section, "wish-role", data["wish_role"])
    
    # Update clients list in settings
    clients = config.get("settings", "clients", fallback="").split()
    if name not in clients:
        clients.append(name)
        config.set("settings", "clients", " ".join(clients))
    
    write_config(config)


def update_audio_client(name: str, data: Dict[str, Any]):
    """Update or create audio client in config"""
    config = read_config()
    
    # Ensure audio section exists
    if not config.has_section("audio"):
        config.add_section("audio")
    
    section = f"audio/client/{name}"
    if not config.has_section(section):
        config.add_section(section)
    
    # Update fields
    if "token" in data:
        config.set(section, "token", data["token"])
    if "ua" in data:
        config.set(section, "ua", data["ua"])
    if "sex" in data and data["sex"]:
        config.set(section, "sex", data["sex"])
    if "search_sex" in data and data["search_sex"]:
        config.set(section, "search-sex", data["search_sex"])
    if "age" in data and data["age"]:
        config.set(section, "age", data["age"])
    if "search_age" in data and data["search_age"]:
        config.set(section, "search-age", data["search_age"])
    if "wait_for" in data:
        if data["wait_for"]:
            config.set(section, "wait-for", data["wait_for"])
        elif config.has_option(section, "wait-for"):
            config.remove_option(section, "wait-for")
    if "proxy" in data:
        if data["proxy"]:
            config.set(section, "proxy", data["proxy"])
        elif config.has_option(section, "proxy"):
            config.remove_option(section, "proxy")
    
    # Update clients list in audio section
    clients = config.get("audio", "clients", fallback="").strip().replace(",", " ").split()
    clients = [c for c in clients if c]  # Remove empty strings
    if name not in clients:
        clients.append(name)
        config.set("audio", "clients", " ".join(clients))
    
    write_config(config)


def delete_text_client(name: str):
    """Delete text client from config"""
    config = read_config()
    section = f"client/{name}"
    
    if config.has_section(section):
        config.remove_section(section)
    
    # Remove from clients list
    clients = config.get("settings", "clients", fallback="").split()
    if name in clients:
        clients.remove(name)
        config.set("settings", "clients", " ".join(clients))
    
    write_config(config)


def delete_audio_client(name: str):
    """Delete audio client from config"""
    config = read_config()
    section = f"audio/client/{name}"
    
    if config.has_section(section):
        config.remove_section(section)
    
    # Remove from clients list
    if config.has_section("audio"):
        clients = config.get("audio", "clients", fallback="").strip().replace(",", " ").split()
        clients = [c for c in clients if c and c != name]
        config.set("audio", "clients", " ".join(clients))
    
    write_config(config)
