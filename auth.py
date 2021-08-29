# Copyright 2017 Mycroft AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import os
from os import mkdir
from os.path import exists, join

import spotipy
from spotipy import SpotifyOAuth
from xdg import BaseDirectory

AUTH_DIR = os.environ.get('SPOTIFY_SKILL_CREDS_DIR',
                          BaseDirectory.save_config_path('spotipy'))
SCOPE = ('user-library-read streaming playlist-read-private user-top-read '
         'user-read-playback-state')


def ensure_auth_dir_exists():
    if not exists(AUTH_DIR):
        mkdir(AUTH_DIR)


if __name__ == '__main__':
    print(
        """This script creates the token information needed for running spotify
        with a set of personal developer credentials.

        It requires the user to go to developer.spotify.com and set up a
        developer account, create an "Application" and make sure to whitelist
        "https://localhost:8888".

        After you have done that enter the information when prompted and follow
        the instructions given.
        """)

    CLIENT_ID = input('YOUR CLIENT ID: ')
    CLIENT_SECRET = input('YOUR CLIENT SECRET: ')
    REDIRECT_URI = 'https://localhost:8888'

    ensure_auth_dir_exists()
    am = SpotifyOAuth(scope=SCOPE, client_id=CLIENT_ID,
                      client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI,
                      cache_path=join(AUTH_DIR, 'token'),
                      open_browser=False)

    token_info = am.validate_token(am.cache_handler.get_cached_token())
    if not token_info:
        code = am.get_auth_response()
        token = am.get_access_token(code, as_dict=False)
    sp = spotipy.Spotify(auth_manager=am)

    choice_valid = False
    while not choice_valid:
        choice = input('Do you want to save the Client Secrets? (y/n) ')
        choice_valid = choice.lower() in ('yes', 'y', 'no', 'n')

    if choice in ('yes', 'y'):
        info = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET}
        with open(join(AUTH_DIR, 'auth'), 'w') as f:
            json.dump(info, f)
