"""
Import your shows from Kitsu to Sonarr!
"""

import configparser
import json
import requests
from slugify import slugify
from Pymoe import Kitsu
import ujson

KITSU_HEADER = {
    'User-Agent': 'Kitsu2Sonarr',
    'Accept': 'application/vnd.api+json',
    'Content-Type': 'application/vnd.api+json'
}

JAP_MAP_FILE = "library.json"


def save_map(map_var):
    """
    Save the map of shows.
    :param map_var: the map dictionary
    """
    with open(JAP_MAP_FILE, "w") as f:
        json.dump(map_var, f)


def get_library(instance, user_id):
    """
    Get the user's library from Kitsu
    :param instance: kitsu instance
    :param user_id: user id for the user's library
    :return: the user's library
    """
    return instance.library.get(user_id)


def get_library_item(item_id):
    """
    Get an individual library entry's media
    :param item_id: the library entry id
    :return: the media item
    """
    data_stuff = requests.get("https://kitsu.io/api/edge/library-entries/{}/media".format(item_id))
    if data_stuff.status_code == 200:
        return data_stuff.json()['data']
    raise ConnectionError()


def gather_library_tvdb_ids(library_items, instance, user_id):
    library = get_library(instance, user_id)
    for item in library:
        if item['attributes']['status'] != 'dropped':
            lib_item = get_library_item(item['id'])
            if lib_item is not None and lib_item['id'] not in library_items\
                and lib_item['type'] == "anime"\
                    and lib_item['attributes']['subtype'] == "TV":
                mapping = instance.mappings.get("thetvdb/series", lib_item['id'])
                if mapping is not None:
                    en_name = None
                    try:
                        en_name = lib_item['attributes']['titles']['en']
                    except KeyError:
                        print("The English name does not exist on Kitsu")
                    library_items[lib_item['id']] = {
                        'name': {
                            "romaji": lib_item['attributes']['titles']['en_jp'],
                            'english': en_name
                        },
                        'tvdbId': mapping}
                    save_map(library_items)
    return library_items


def get_sonarr_profiles(sonarr_api_path, sonarr_api_key):  # 3
    """
    Get media profiles from Sonarr
    :param sonarr_api_path: where your Sonarr instance is located
    :param sonarr_api_key: API key for your Sonarr instance
    :return: JSON of the available media profiles
    """
    profiles = requests.get("{}/profile?apiKey={}".format(sonarr_api_path, sonarr_api_key))
    if profiles.status_code == 200:
        return profiles.json()
    raise ConnectionError()


def get_sonarr_paths(sonarr_api_path, sonarr_api_key):  # 1
    """
    Get media paths from Sonarr
    :param sonarr_api_path: where your Sonarr instance is located
    :param sonarr_api_key: API key for your Sonarr instance
    :return: JSON of the available media paths
    """
    paths = requests.get("{}/rootfolder?apiKey={}".format(sonarr_api_path, sonarr_api_key))
    if paths.status_code == 200:
        return paths.json()
    raise ConnectionError()


def sonarr_add_show(api_path, api_key, item):
    """
    Add a show to Sonarr
    :param api_path: where your Sonarr instance is located
    :param api_key: API key for your Sonarr instance
    :param item: the item you want to add to Sonarr
    """
    item_name = item["name"]["romaji"]
    try:
        item_name = item["name"]["en"]
    except KeyError:
        print("The english name was None")
    item_id = item["tvdbId"].split("/")[0]
    sonarr_data = {
        "tvdbId": item_id,
        "title": item_name,
        "qualityProfileId": 3,
        "titleSlug": slugify(item_name),
        "images": [],
        "seasons": [],
        "rootFolderPath": "/anime"
    }
    show = requests.post("{}/series?apiKey={}".format(api_path, api_key), json=sonarr_data)
    if show.status_code == 200:
        print(show.json()['data'])
        #if show.json()['data']
        return
    raise ConnectionError()


def load_config():
    """
    Load the config file for the script, and make sure it is valid
    :return: the config object
    """
    config = configparser.ConfigParser()
    config.read('kitsu2sonarr.ini')
    if 'kitsu.io' not in config:
        config['kitsu.io'] = {}
        config['kitsu.io']['client_id'] = None
        config['kitsu.io']['client_secret'] = None
        config['kitsu.io']['user_id'] = None
        with open('kitsu2sonarr.ini', 'w') as configfile:
            config.write(configfile)
        raise Exception("Missing config items! 'kitsu.io' was added, please fill in those values "
                        "in \"kitsu2sonarr.ini\"")  # todo: write exception?
    else:
        for config_key in config['kitsu.io']:
            if config['kitsu.io'][config_key] == '':
                raise Exception("Missing config items! {} is not defined!".format(config_key))
    if 'sonarr' not in config:
        config['sonarr'] = {}
        config['sonarr']['url'] = None
        config['sonarr']['api_key'] = None
        with open('kitsu2sonarr.ini', 'w') as configfile:
            config.write(configfile)
        raise Exception("Missing config items!")
    else:
        for config_key in config['sonarr']:
            if config['sonarr'][config_key] == '':
                raise Exception("Missing config items! {} is not defined!".format(config_key))
    return config


def main():
    config = load_config()
    instance = Kitsu(config['kitsu.io']['client_id'], config['kitsu.io']['client_secret'])
    library_items = dict()
    try:
        with open(JAP_MAP_FILE, 'r') as f:
            library_items = ujson.load(f)
    except json.JSONDecodeError as json_error:
        print("There seems to be an issue with {} at L{}:C{}.".format(JAP_MAP_FILE, json_error.lineno, json_error.colno))
    library_items = gather_library_tvdb_ids(library_items, instance, config['kitsu.io']['user_id'])
    for key, value in library_items.items():
        sonarr_add_show(config['sonarr']['url'], config['sonarr']['api_key'], value)


if __name__ == "__main__":
    main()
