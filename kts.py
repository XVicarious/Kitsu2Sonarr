"""
Import your shows from Kitsu to Sonarr!
"""

import configparser
import json
import requests
from slugify import slugify
from Pymoe import Kitsu
import ujson


JAP_MAP_FILE = "library.json"

requests.models.json = ujson


def load_map():
    """ Load the library from file """
    try:
        with open(JAP_MAP_FILE, 'r') as map_file:
            return ujson.load(map_file)
    except json.JSONDecodeError as json_error:
        print("There seems to be an issue with {} at L{}:C{}."
              .format(JAP_MAP_FILE, json_error.lineno, json_error.colno))
        return None


def save_map(map_var):
    """
    Save the map of shows.
    :param map_var: the map dictionary
    """
    with open(JAP_MAP_FILE, "w") as map_file:
        json.dump(map_var, map_file)


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
    """
    Gather any shows from Kitsu from your library
    :param library_items: the current library of shows
    :param instance: the Kitsu api instance to find things with
    :param user_id: the user id of the user you want to get the library from
    :return: the new library, updated with new items
    """
    library = get_library(instance, user_id)
    for item in library:
        if item['attributes']['status'] != 'dropped':
            lib_item = get_library_item(item['id'])
            if lib_item is not None and lib_item['id'] not in library_items \
                    and lib_item['type'] == "anime" \
                    and (lib_item['attributes']['subtype'] == "TV"
                         or lib_item['attributes']['subtype'] == "movie"):
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
                        'tvdbId': mapping,
                        'type': lib_item['attributes']['subtype']}
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
    raise ConnectionError(profiles.status_code)


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
    raise ConnectionError(paths.status_code)


def sonarr_add_show(api_path, api_key, item, profile_id=1):
    """
    Add a show to Sonarr
    :param api_path: where your Sonarr instance is located
    :param api_key: API key for your Sonarr instance
    :param item: the item you want to add to Sonarr
    :param profile_id: the profile id you want to use for anime going forward, defaults to 1
    """
    item_name = item["name"]["romaji"]
    try:
        item_name = item["name"]["en"]
    except KeyError:
        print("The english name was None")
    item_id = item["tvdbId"].split("/")[0]
    sonarr_data = {
        "tvdbId": int(item_id),
        "title": item_name,
        "qualityProfileId": profile_id,
        "titleSlug": slugify(item_name),
        "images": [],
        "seasons": [],
        "rootFolderPath": "/anime",
        "seriesType": "anime"
    }
    show = requests.post("{}/series?apiKey={}".format(api_path, api_key), json=sonarr_data)
    if show.status_code == 200:
        return True
    elif show.status_code == 400 and \
            show.json()[0]['errorMessage'] == 'This series has already been added':
        return False
    raise ConnectionError(show.status_code, show.url, show.json())


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
        raise configparser.NoSectionError(section='kitsu.io')
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


def establish_sonarr_profile(sonarr_api_path, sonarr_api_key):
    """
    Have the user tell us what Sonarr profile they want to use
    :param sonarr_api_path: path to the Sonarr instance
    :param sonarr_api_key: Sonarr instance API key
    :return: the index of the profile to use for the config
    """
    profiles = get_sonarr_profiles(sonarr_api_path, sonarr_api_key)
    print("-----------------------")
    for profile in profiles:
        print("{profile_id}. {profile_name}, Cutoff: {profile_cutoff}".format(
            profile_id=profile['id'],
            profile_name=profile['name'],
            profile_cutoff=profile['cutoff']['name']
        ))
    input_profile = input("Please select the profile number: ")
    while True:
        try:
            input_profile = int(input_profile)
            if input_profile > len(profiles) - 1:
                raise IndexError
            break
        except ValueError:
            input_profile = input("Please input a profile id: ")
        except IndexError:
            input_profile = input("Please input a profile id: ")
    return input_profile


def main():
    """ Do the things """
    config = load_config()
    try:
        profile_id = config['sonarr']['profile_id']
    except KeyError:
        profile_id = establish_sonarr_profile(config['sonarr']['url'], config['sonarr']['api_key'])
        config['sonarr']['profile_id'] = str(profile_id)
        with open('kitsu2sonarr.ini', 'w') as config_file:
            config.write(config_file)
    instance = Kitsu(config['kitsu.io']['client_id'], config['kitsu.io']['client_secret'])
    print("Trying to open your library file.")
    library_items = load_map()
    print("Gathering new shows from Kitsu")
    library_items = gather_library_tvdb_ids(library_items, instance, config['kitsu.io']['user_id'])
    print("Adding shows to Sonarr")
    for key, value in library_items.items():
        if ('inSonarr' not in value or not value['inSonarr'])\
                and ('type' not in value or value['type'] == 'TV'):
            sonarr_add_show(config['sonarr']['url'], config['sonarr']['api_key'], value, profile_id)
            library_items[key]['inSonarr'] = True
            save_map(library_items)


if __name__ == "__main__":
    main()
