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

"""
INTRO:
Spotify is a little different than some music services.  The APIs encourage
a sort of network of music players.  So this skill will act as a remote
controller when another Spotify player is already running and it is invoked.
Otherwise it begins playing the music locally using the Mycroft-controlled
hardware.  (Which, depending on the audio setup, might not be the main
speaker on the equipment.)
"""
import re
from mycroft.skills.core import intent_handler, intent_file_handler
from mycroft.util.parse import match_one, fuzzy_match
from mycroft.api import DeviceApi
from requests import HTTPError
from adapt.intent import IntentBuilder

import time
from os.path import abspath, dirname, join
from subprocess import call, Popen, DEVNULL
import signal
from socket import gethostname

from .spotify import (MycroftSpotifyCredentials, SpotifyConnect,
                      get_album_info, get_artist_info, get_song_info)
import random

from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel


class SpotifyPlaybackError(Exception):
    pass


class NoSpotifyDevicesError(Exception):
    pass


class PlaylistNotFoundError(Exception):
    pass


class SpotifyNotAuthorizedError(Exception):
    pass


MANAGED_PLATFORMS = ['mycroft_mark_1']


def update_librespot():
    try:
        call(["bash", join(dirname(abspath(__file__)), "requirements.sh")])
    except Exception as e:
        print('Librespot Update failed, {}'.format(repr(e)))


class SpotifySkill(CommonPlaySkill):
    """Spotify control through the Spotify Connect API."""

    def __init__(self):
        super(SpotifySkill, self).__init__()
        self.index = 0
        self.spotify = None
        self.process = None
        self.device_name = None
        self.dev_id = None
        self.idle_count = 0
        self.ducking = False
        self.mouth_text = None
        self.librespot_starting = False

        self.__device_list = None
        self.__devices_fetched = 0
        self.OAUTH_ID = 1
        self.DEFAULT_VOLUME = 80
        self._playlists = None

    def launch_librespot(self):
        """ Launch the librespot binary for the Mark-1.
        TODO: Discovery mode
        """
        self.librespot_starting = True
        platform = self.config_core.get('enclosure').get('platform', 'unknown')
        path = self.settings.get('librespot_path', None)
        if platform == 'mycroft_mark_1' and not path:
            path = 'librespot'

        if (path and self.device_name and
                'user' in self.settings and 'password' in self.settings):

            # Disable librespot logging if not specifically requested
            outs = None if 'librespot_log' in self.settings else DEVNULL

            # TODO: Error message when provided username/password don't work
            self.process = Popen([path, '-n', self.device_name,
                                  '-u', self.settings['user'],
                                  '-p', self.settings['password']],
                                  stdout=outs, stderr=outs)

            time.sleep(3)  # give libreSpot time to start-up
            if self.process and self.process.poll() is not None:
                # libreSpot shut down immediately.  Bad user/password?
                if self.settings['user']:
                    self.speak_dialog("FailedToStart")
                self.process = None
                self.librespot_starting = False
                return

            # Lower the volume since max volume sounds terrible on the Mark-1
            dev = self.device_by_name(self.device_name)
            if dev:
                self.spotify.volume(dev['id'], self.DEFAULT_VOLUME)
        self.librespot_starting = False

    def initialize(self):
        # Make sure the spotify login scheduled event is shutdown
        super().initialize()
        self.cancel_scheduled_event('SpotifyLogin')
        # Setup handlers for playback control messages
        self.add_event('mycroft.audio.service.next', self.next_track)
        self.add_event('mycroft.audio.service.prev', self.prev_track)
        self.add_event('mycroft.audio.service.pause', self.pause)
        self.add_event('mycroft.audio.service.resume', self.resume)
        # Check and then monitor for credential changes
        self.settings.set_changed_callback(self.on_websettings_changed)
        # Retry in 5 minutes
        self.schedule_repeating_event(self.on_websettings_changed,
                                      None, 5*60,
                                      name='SpotifyLogin')
        platform = self.config_core.get('enclosure').get('platform', 'unknown')
        if platform in MANAGED_PLATFORMS:
            update_librespot()
        self.on_websettings_changed()

    def on_websettings_changed(self):
        # Only attempt to load credentials if the username has been set
        # will limit the accesses to the api.
        if not self.spotify and self.settings.get('user', None):
            try:
                self.load_credentials()
            except Exception as e:
                self.log.debug('Credentials could not be fetched. '
                              '({})'.format(repr(e)))

        if self.spotify:
            self.cancel_scheduled_event('SpotifyLogin')
            if 'user' in self.settings and 'password' in self.settings:
                if self.process:
                    self.stop_librespot()
                self.launch_librespot()

    def load_credentials(self):
        """ Retrieve credentials from the backend and connect to Spotify """
        try:
            creds = MycroftSpotifyCredentials(self.OAUTH_ID)
            self.spotify = SpotifyConnect(client_credentials_manager=creds)
        except HTTPError:
            self.log.info('Couldn\'t fetch credentials')
            self.spotify = None

        if self.spotify:
            # Spotfy connection worked, prepare for usage
            # TODO: Repeat occasionally on failures?
            # If not able to authorize, the method will be repeated after 60
            # seconds
            self.create_intents()
            # Should be safe to set device_name here since home has already
            # been connected
            self.device_name = DeviceApi().get().get('name')

    ######################################################################
    # Handle auto ducking when listener is started.

    def handle_listener_started(self, message):
        """ Handle auto ducking when listener is started.

        The ducking is enabled/disabled using the skill settings on home.

        TODO: Evaluate the Idle check logic
        """
        if self.spotify.is_playing() and \
                self.settings.get('use_ducking', False):
            self.__pause()
            self.ducking = True

            # Start idle check
            self.idle_count = 0
            self.cancel_scheduled_event('IdleCheck')
            self.schedule_repeating_event(self.check_for_idle, None,
                                          1, name='IdleCheck')

    def check_for_idle(self):
        """ Repeating event checking for end of auto ducking. """
        if not self.ducking:
            self.cancel_scheduled_event('IdleCheck')
            return

        active = self.enclosure.display_manager.get_active()
        if not active == '' or active == 'SpotifySkill':
            # No activity, start to fall asleep
            self.idle_count += 1

            if self.idle_count >= 5:
                # Resume playback after 5 seconds of being idle
                self.cancel_scheduled_event('IdleCheck')
                self.ducking = False
                self.resume()
        else:
            self.idle_count = 0

    ######################################################################
    # Mycroft display handling

    def start_monitor(self):
        """ Monitoring and current song display. """
        # Clear any existing event
        self.stop_monitor()

        # Schedule a new one every 5 seconds to monitor/update display
        self.schedule_repeating_event(self._update_display,
                                      None, 5,
                                      name='MonitorSpotify')
        self.add_event('recognizer_loop:record_begin',
                       self.handle_listener_started)

    def stop_monitor(self):
        # Clear any existing event
        self.cancel_scheduled_event('MonitorSpotify')

    def _update_display(self, message):
        # Checks once a second for feedback
        status = self.spotify.status() if self.spotify else {}

        if not status or not status.get('is_playing'):
            self.stop_monitor()
            self.mouth_text = None
            self.enclosure.mouth_reset()
            return

        # Get the current track info
        try:
            text = status['item']['artists'][0]['name'] + ': '
        except:
            text = ""
        try:
            text += status['item']['name']
        except:
            pass

        # Update the "Now Playing" display if needed
        if text != self.mouth_text:
            self.mouth_text = text
            self.enclosure.mouth_text(text)

    ######################################################################
    # Intent handling

    def CPS_match_query_phrase(self, phrase):
        # Not ready to play
        if not self.playback_prerequisits_ok():
            self.log.debug('Spotify is not available to play')
            if 'spotify' in phrase:
                return phrase, CPSMatchLevel.GENERIC
            else:
                return None

        if 'spotify' in phrase:
            bonus = 0.1
        else:
            bonus = 0

        phrase = re.sub(self.translate('on_spotify_regex'), '', phrase)

        confidence, data = self.continue_playback(phrase, bonus)
        if not data:
            confidence, data = self.specific_query(phrase, bonus)
            if not data:
                confidence, data = self.generic_query(phrase, bonus)

        if data:
            if confidence > 0.9:
                confidence = CPSMatchLevel.EXACT
            elif confidence > 0.7:
                confidence = CPSMatchLevel.MULTI_KEY
            elif confidence > 0.5:
                confidence = CPSMatchLevel.TITLE
            else:
                confidence = CPSMatchLevel.CATEGORY
            return phrase, confidence, data
        else:
            self.log.debug('Couldn\'t find anything to play on Spotify')

    def continue_playback(self, phrase, bonus):
        if phrase.strip() == 'spotify':
            return (1.0,
                    {
                        'data': None,
                        'name': None,
                        'type': 'continue'
                    })
        else:
            return None, None

    def specific_query(self, phrase, bonus):
        # Check if playlist
        match = re.match(self.translate('playlist_regex'), phrase)
        if match:
            bonus += 0.1
            playlist, conf = self.get_best_playlist(match.groupdict()['playlist'])
            confidence = min(conf + bonus, 1.0)
            if not playlist:
                return None, None
            uri = self.playlists[playlist]
            return (conf,
                    {
                        'data': uri,
                        'name': playlist,
                        'type': 'playlist'
                    })
        # Check album
        match = re.match(self.translate('album_regex'), phrase)
        if match:
            bonus += 0.1
            album = match.groupdict()['album']
            return self.query_album(album, bonus)

        # Check artist
        match = re.match(self.translate('artist_regex'), phrase)
        if match:
            bonus += 0.1
            artist = match.groupdict()['artist']
            data = self.spotify.search(artist, type='artist')
            if data and data['artists']['items']:
                best = data['artists']['items'][0]['name']
                confidence = min(fuzzy_match(best, artist.lower()) + bonus, 1.0)
                return (confidence,
                        {
                            'data': data,
                            'name': None,
                            'type': 'artist'
                        })
        match = re.match(self.translate('song_regex'), phrase)
        if match:
            data = self.spotify.search(match.groupdict()['track'],
                                       type='track')
            if data:
                return (1.0,
                        {
                            'data': data,
                            'name': None,
                            'type': 'track'
                        })
        return None, None

    def generic_query(self, phrase, bonus):
        playlist, conf = self.get_best_playlist(phrase)
        if conf > 0.5:
            uri = self.playlists[playlist]
            return (conf,
                    {
                        'data': uri,
                        'name': playlist,
                        'type': 'playlist'
                    })
        else:
            return self.query_album(phrase, bonus)

    def query_album(self, album, bonus):
        data = None
        by_word = ' {} '.format(self.translate('by'))
        if len(album.split(by_word)) > 1:
            album, artist = album.split(by_word)
            album='*{}* artist:{}'.format(album, artist)
            bonus += 0.1
        data = self.spotify.search(album, type='album')
        if data and data['albums']['items']:
            best = data['albums']['items'][0]['name']
            confidence = min(fuzzy_match(best.lower(), album) + bonus, 1.0)
            return (confidence,
                    {
                        'data': data,
                        'name': None,
                        'type': 'album'
                    })
        return None, None

    def CPS_start(self, phrase, data):
        try:
            if not self.spotify:
                raise SpotifyNotAuthorizedError
            # Wait for librespot to start
            if self.librespot_starting:
                self.log.info('Restarting Librespot...')
                for i in range(10):
                    time.sleep(0.5)
                    if not self.librespot_starting:
                        break
                else:
                    self.log.error('LIBRESPOT NOT STARTED')

            dev = self.get_default_device()
            if not dev:
                raise NoSpotifyDevicesError

            if data['type'] == 'continue':
                self.continue_current_playlist(dev)
            elif data['type'] == 'playlist':
                self.start_playlist_playback(dev, data['name'],
                                             data['data'])
            else:  # artist, album track
                self.log.info('playing {}'.format(data['type']))
                self.play(dev, data=data['data'], data_type=data['type'])

        except NoSpotifyDevicesError:
            self.log.error("Unable to get a default device while trying "
                           "to play something.")
            self.speak_dialog('PlaybackFailed',
                {'reason': self.translate('NoDevicesAvailable')})
        except SpotifyNotAuthorizedError:
            self.speak_dialog('PlaybackFailed',
                {'reason': self.translate('NotAuthorized')})
        except PlaylistNotFoundError:
            self.speak_dialog('PlaybackFailed',
                {'reason': self.translate('PlaylistNotFound')})
        except Exception as e:
            self.speak_dialog('PlaybackFailed', {'reason': str(e)})

    def create_intents(self):
        # Create intents
        intent = IntentBuilder('').require('Spotify').require('Search') \
                                  .require('For')
        self.register_intent(intent, self.search_spotify)
        self.register_intent_file('ShuffleOn.intent', self.shuffle_on)
        self.register_intent_file('ShuffleOff.intent', self.shuffle_off)

    @property
    def playlists(self):
        """ Playlists, cached for 5 minutes """
        if not self.spotify:
            return []  # No connection, no playlists
        now = time.time()
        if not self._playlists or (now - self.__playlists_fetched > 5 * 60):
            self._playlists = {}
            playlists = self.spotify.current_user_playlists().get('items', [])
            for p in playlists:
                self._playlists[p['name'].lower()] = p
            self.__playlists_fetched = now
        return self._playlists

    @property
    def devices(self):
        """ Devices, cached for 60 seconds """
        if not self.spotify:
            return []  # No connection, no devices
        now = time.time()
        if not self.__device_list or (now - self.__devices_fetched > 60):
            self.__device_list = self.spotify.get_devices()
            self.__devices_fetched = now
        return self.__device_list

    def device_by_name(self, name):
        """ Get a Spotify devices from the API

        Args:
            name (str): The device name (fuzzy matches)
        Returns:
            (dict) None or the matching device's description
        """
        devices = self.devices
        if devices and len(devices) > 0:
            # Otherwise get a device with the selected name
            devices_by_name = {d['name']: d for d in devices}
            key, confidence = match_one(name, list(devices_by_name.keys()))
            if confidence > 0.5:
                return devices_by_name[key]
        return None

    def get_default_device(self):
        """ Get preferred playback device """
        if self.spotify:
            # When there is an active Spotify device somewhere, use it
            if (self.devices and len(self.devices) > 0 and
                    self.spotify.is_playing()):
                for dev in self.devices:
                    if dev['is_active']:
                        return dev  # Use this device

            # No playing device found, use the default Spotify device
            default_device = self.settings.get('default_device', '')
            dev = None
            if default_device:
                dev = self.device_by_name(default_device)
            # if not set or missing try playing on this device
            if not dev:
                dev = self.device_by_name(self.device_name)
            # if not check if a desktop spotify client is playing
            if not dev:
                dev = self.device_by_name(gethostname())
            # use first best device if none of the prioritized works
            if not dev and len(self.devices) > 0:
                dev = self.devices[0]
            if dev and not dev['is_active']:
                self.spotify.transfer_playback(dev['id'], False)
            return dev

        return None

    def get_best_playlist(self, playlist):
        """ Get best playlist matching the provided name

        Arguments:
            playlist (str): Playlist name

        Returns: ((str)best match, (float)confidence)
        """
        playlists = list(self.playlists.keys())
        if len(playlists) > 0:
            # Only check if the user has playlists
            key, confidence = match_one(playlist.lower(), playlists)
            if confidence > 0.7:
                return key, confidence
        return None, 0

    def continue_current_playlist(self, dev):
        """ Send the play command to the selected device. """
        time.sleep(2)
        self.spotify_play(dev['id'])

    def playback_prerequisits_ok(self):
        """ Check that playback is possible, launch client if neccessary. """
        if self.spotify is None:
            return False

        devs = [d['name'] for d in self.devices]
        if self.process and self.device_name not in devs:
            self.log.info('Librespot not responding, restarting...')
            self.stop_librespot()
            self.__devices_fetched = 0  # Make sure devices are fetched again
        if not self.process:
            self.schedule_event(self.launch_librespot, 0,
                                name='launch_librespot')
        return True

    def spotify_play(self, dev_id, uris=None, context_uri=None):
        """ Start spotify playback and log any exceptions. """
        try:
            self.log.info(u'spotify_play: {}'.format(dev_id))
            self.spotify.play(dev_id, uris, context_uri)
            self.start_monitor()
            self.dev_id = dev_id
        except spotipy.SpotifyException as e:
            # TODO: Catch other conditions?
            raise SpotifyNotAuthorizedError
        except Exception as e:
            self.log.exception(e)
            raise

    def start_playlist_playback(self, dev, name, uri):
        if uri:
            self.log.info(u'playing {} using {}'.format(name, dev['name']))
            self.speak_dialog('ListeningToPlaylist',
                              data={'playlist': name})
            time.sleep(2)
            tracks = self.spotify.user_playlist_tracks(uri['owner']['id'],
                                                       uri['id'])
            uris = [t['track']['uri'] for t in tracks['items']]
            self.spotify_play(dev['id'], uris=uris)
        else:
            self.log.info('No playlist found')
            raise PlaylistNotFoundError

    def play(self, dev, data, data_type='track', genre_name=None):
        """
        Plays the provided data in the manner appropriate for 'data_type'
        If the type is 'genre' then genre_name should be specified to populate
        the output dialog.

        A 'track' is played as just an individual track.
        An 'album' queues up all the tracks contained in that album and starts
        with the first track.
        A 'genre' expects data returned from self.spotify.search, and will use
        that genre to play a selection similar to it.

        Args:
            data (dict):        Data returned by self.spotify.search
            data_type (str):    The type of data contained in the passed-in
                                object. 'track', 'album', or 'genre' are
                                currently supported.
            genre_name (str):   If type is 'genre', also include the genre's
                                name here, for output purposes. default None
        """
        try:
            if data_type == 'track':
                (song, artists, uri) = get_song_info(data)
                self.speak_dialog('ListeningToSongBy',
                                  data={'tracks': song,
                                        'artist': artists[0]})
                time.sleep(2)
                self.spotify_play(dev['id'], uris=[uri])
            elif data_type == 'artist':
                (artist, uri) = get_artist_info(data)
                self.speak_dialog('ListeningToArtist',
                                  data={'artist': artist})
                time.sleep(2)
                self.spotify_play(dev['id'], context_uri=uri)
            elif data_type == 'album':
                (album, artists, uri) = get_album_info(data)
                self.speak_dialog('ListeningToAlbumBy',
                                  data={'album': album,
                                        'artist': artists[0]})
                time.sleep(2)
                self.spotify_play(dev['id'], context_uri=uri)
            elif data_type == 'genre':
                items = data['tracks']['items']
                random.shuffle(items)
                uris = []
                for item in items:
                    uris.append(item['uri'])
                data = {'genre': genre_name, 'track': items[0]['name'],
                        'artist': items[0]['artists'][0]['name']}
                self.speak_dialog('ListeningToGenre', data)
                time.sleep(2)
                self.spotify_play(dev['id'], uris=uris)
            else:
                self.log.error('wrong data_type')
                raise ValueError("Invalid type")
        except Exception as e:
            self.log.error("Unable to obtain the name, artist, "
                           "and/or URI information while asked to play "
                           "something. " + str(e))
            raise

    def search(self, query, search_type):
        """ Search for an album, playlist or artist.
        Arguments:
            query:       search query (album title, artist, etc.)
            search_type: whether to search for an 'album', 'artist',
                         'playlist', 'track', or 'genre'

            TODO: improve results of albums by checking artist
        """
        res = None
        if search_type == 'album' and len(query.split('by')) > 1:
            title, artist = query.split('by')
            result = self.spotify.search(title, type=search_type)
        else:
            result = self.spotify.search(query, type=search_type)

        if search_type == 'album':
            if len(result['albums']['items']) > 0:
                album = result['albums']['items'][0]
                self.log.info(album)
                res = album
        elif search_type == 'artist':
            self.log.info(result['artists'])
            if len(result['artists']['items']) > 0:
                artist = result['artists']['items'][0]
                self.log.info(artist)
                res = artist
        elif search_type == 'genre':
            self.log.debug("TODO! Genre")
        else:
            self.log.error('Search type {} not supported'.format(search_type))
            return

        return res

    def search_spotify(self, message):
        """ Intent handler for "search spotify for X". """

        try:
            dev = self.get_default_device()
            if not dev:
                raise NoSpotifyDevicesError

            utterance = message.data['utterance']
            if len(utterance.split(self.translate('ForAlbum'))) == 2:
                query = utterance.split(self.translate('ForAlbum'))[1].strip()
                data = self.spotify.search(query, type='album')
                self.play(dev, data=data, data_type='album')
            elif len(utterance.split(self.translate('ForArtist'))) == 2:
                query = utterance.split(self.translate('ForArtist'))[1].strip()
                data = self.spotify.search(query, type='artist')
                self.play(dev, data=data, data_type='artist')
            else:
                for_word = ' ' + self.translate('For')
                query = for_word.join(utterance.split(for_word)[1:]).strip()
                data = self.spotify.search(query, type='track')
                self.play(dev, data=data, data_type='track')
        except NoSpotifyDevicesError:
            self.log.error("Unable to get a default device while trying "
                           "to play something.")
            self.speak_dialog('PlaybackFailed',
                {'reason': self.translate('NoDevicesAvailable')})
        except SpotifyNotAuthorizedError:
            self.speak_dialog('PlaybackFailed',
                {'reason': self.translate('NotAuthorized')})
        except PlaylistNotFoundError:
            self.speak_dialog('PlaybackFailed',
                {'reason': self.translate('PlaylistNotFound')})
        except Exception as e:
            self.speak_dialog('PlaybackFailed', {'reason': str(e)})

    def shuffle_on(self):
        """ Turn on shuffling """
        if self.spotify:
            self.spotify.shuffle(True)
        else:
            self.speak_dialog('NotAuthorized')

    def shuffle_off(self):
        """ Turn off shuffling """
        if self.spotify:
            self.spotify.shuffle(False)
        else:
            self.speak_dialog('NotAuthorized')

    def __pause(self):
        # if authorized and playback was started by the skill
        if self.spotify:
            self.log.info('Pausing Spotify...')
            self.spotify.pause(self.dev_id)

    def pause(self, message=None):
        """ Handler for playback control pause. """
        self.ducking = False
        self.__pause()

    def resume(self, message=None):
        """ Handler for playback control resume. """
        # if authorized and playback was started by the skill
        if self.spotify:
            self.log.info('Resume Spotify')
            if not self.dev_id:
                self.dev_id = self.get_default_device()
            self.spotify_play(self.dev_id)

    def next_track(self, message):
        """ Handler for playback control next. """
        # if authorized and playback was started by the skill
        if self.spotify and self.dev_id:
            self.log.info('Next Spotify track')
            self.spotify.next(self.dev_id)
            self.start_monitor()
            return True
        return False

    def prev_track(self, message):
        """ Handler for playback control prev. """
        # if authorized and playback was started by the skill
        if self.spotify and self.dev_id:
            self.log.info('Previous Spotify track')
            self.spotify.prev(self.dev_id)
            self.start_monitor()

    @intent_handler(IntentBuilder('').require('Spotify').require('Device'))
    def list_devices(self, message):
        """ List available devices. """
        if self.spotify:
            devices = [d['name'] for d in self.spotify.get_devices()]
            if len(devices) == 1:
                self.speak(devices[0])
            elif len(devices) > 1:
                self.speak_dialog('AvailableDevices',
                                  {'devices': ' '.join(devices[:-1]) + ' ' +
                                              self.translate('And') + ' ' +
                                              devices[-1]})
            else:
                self.speak_dialog('NoDevicesAvailable')
        else:
            self.speak_dialog('NotAuthorized')

    @intent_handler(IntentBuilder('').require('Transfer').require('Spotify')
                                     .require('ToDevice'))
    def transfer_playback(self, message):
        """ Move playback from one device to another. """
        if self.spotify and self.spotify.is_playing():
            dev = self.device_by_name(message.data['ToDevice'])
            if dev:
                self.log.info('Transfering playback to {}'.format(dev['name']))
                self.spotify.transfer_playback(dev['id'])
            else:
                self.speak_dialog('DeviceNotFound',
                                  {'name': message.data['ToDevice']})
        elif not self.spotify:
            self.speak_dialog('NotAuthorized')
        else:
            self.speak_dialog('NothingPlaying')

    def stop(self):
        """ Stop playback. """
        if self.spotify and self.spotify.is_playing():
            dev = self.get_default_device()
            self.dev_id = dev['id']
            if self.dev_id:
                self.pause(None)

                # Clear playing device id
                self.dev_id = None
                return True
        self.dev_id = None
        return False

    def stop_librespot(self):
        """ Send Terminate signal to librespot if it's running. """
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            self.process.communicate()  # Communicate to remove zombie
            self.process = None

    def shutdown(self):
        """ Remove the monitor at shutdown. """
        self.cancel_scheduled_event('SpotifyLogin')
        self.stop_monitor()
        self.stop_librespot()

        # Do normal shutdown procedure
        super(SpotifySkill, self).shutdown()


def create_skill():
    return SpotifySkill()

# WORKING COMMANDS:
# play spotify
# search spotify for the album nighthawks at the diner
# list spotify devices
# skip track
# next track
# pause
# resume
# pause music
# resume music
#
# FAILING COMMANDS:
# play tom waits on spotify
# search spotify for nighthawks at the diner
