import configparser
import requests
import json
from slugify import slugify
from Pymoe import Kitsu

KITSU_HEADER = {
    'User-Agent': 'Kitsu2Sonarr',
    'Accept': 'application/vnd.api+json',
    'Content-Type': 'application/vnd.api+json'
}

JAP_MAP_FILE = "library.json"

SONARR_API_KEY = ""

SONARR_API_PATH = ""


def save_map(map_var):
    with open(JAP_MAP_FILE, "w") as f:
        json.dump(map_var, f)


def get_library(instance, user_id):
    return instance.library.get(user_id)


def get_library_item(item_id):
    data_stuff = requests.get("https://kitsu.io/api/edge/library-entries/{}/media".format(item_id))
    if data_stuff.status_code == 200:
        return data_stuff.json()['data']


def gather_library_tvdb_ids(library_items, instance, user_id):
    library = get_library(instance, user_id)
    for item in library:
        if item['attributes']['status'] != 'dropped':
            lib_item = get_library_item(item['id'])
            if lib_item is not None and lib_item['id'] not in library_items and lib_item['type'] == "anime" and \
                    lib_item['attributes']['subtype'] == "TV":
                mapping = instance.mappings.get("thetvdb/series", lib_item['id'])
                if mapping is not None:
                    en_name = None
                    try:
                        en_name = lib_item['attributes']['titles']['en']
                    except KeyError:
                        print("The English name does not exist on Kitsu")
                    library_items[lib_item['id']] = {
                        'name': {"romaji": lib_item['attributes']['titles']['en_jp'], 'english': en_name},
                        'tvdbId': mapping}
                    save_map(library_items)
    return library_items


def get_sonarr_profiles(sonarr_api_path, sonarr_api_key):  # 3
    profiles = requests.get("{}/profile?apiKey={}".format(sonarr_api_path, sonarr_api_key))
    if profiles.status_code == 200:
        return profiles.json()


def get_sonarr_paths(sonarr_api_path, sonarr_api_key):  # 1
    paths = requests.get("{}/rootfolder?apiKey={}".format(sonarr_api_path, sonarr_api_key))
    if paths.status_code == 200:
        return paths.json()


def sonarr_add_show(api_path, api_key, item):
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
        return
    return


config = configparser.ConfigParser()
config.read('kitsu2sonarr.ini')
kitsu = {}
if 'kitsu.io' in config:
    kitsu = config['kitsu.io']
else:
    print("Oops! You need to add the kitsu api shit")
    config['kitsu.io'] = {}
    config['kitsu.io']['client_id'] = ''
    config['kitsu.io']['client_secret'] = ''
    config['kitsu.io']['user_id'] = ''
    with open('kitsu2sonarr.ini', 'w') as configfile:
        config.write(configfile)
instance = Kitsu(kitsu['client_id'], kitsu['client_secret'])
library_items = dict()
try:
    with open(JAP_MAP_FILE, 'r') as f:
        library_items = json.load(f)
except json.JSONDecodeError as json_error:
    print("There seems to be an issue with {} at L{}:C{}.".format(JAP_MAP_FILE, json_error.lineno, json_error.colno))
library_items = gather_library_tvdb_ids(library_items, instance, kitsu['user_id'])
for key, value in library_items.items():
    sonarr_add_show(SONARR_API_PATH, SONARR_API_KEY, value)
