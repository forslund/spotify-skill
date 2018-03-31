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
from pprint import pformat

import re
from mycroft.skills.core import MycroftSkill, intent_handler, \
                                intent_file_handler
import mycroft.client.enclosure.display_manager as DisplayManager
from mycroft.util.parse import match_one
from mycroft.util.log import LOG
from mycroft.api import DeviceApi
from requests import HTTPError
from adapt.intent import IntentBuilder

import time
import datetime
from subprocess import Popen
import signal
from socket import gethostname

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import random


def get_token(dev_cred):
    """ Get token with a single retry.
    Args:
        dev_cred: OAuth Credentials to fetch
     """
    retry = False
    try:
        d = DeviceApi().get_oauth_token(dev_cred)
    except HTTPError as e:
        if e.response.status_code == 404:  # Token doesn't exist
            raise
        else:
            retry = True
    if retry:
        d = DeviceApi().get_oauth_token(dev_cred)
    return d


class MycroftSpotifyCredentials(SpotifyClientCredentials):
    """ Credentials object renewing through the Mycroft backend."""
    def __init__(self, dev_cred):
        self.dev_cred = dev_cred
        self.access_token = None
        self.expiration_time = None
        self.get_access_token()

    def get_access_token(self):
        if not self.access_token or time.time() > self.expiration_time:
            d = get_token(self.dev_cred)
            self.access_token = d['access_token']
            # get expiration time from message, if missing assume 1 hour
            self.expiration_time = d.get('expiration') or time.time() + 3600
        return self.access_token


class SpotifyConnect(spotipy.Spotify):
    """ Implement the Spotify Connect API.
    See:  https://developer.spotify.com/web-api/

    This class extends the spotipy.Spotify class with Spotify Connect
    methods since the Spotipy module including these isn't released yet.
    """
    def get_devices(self):
        """ Get a list of Spotify devices from the API.

        Returns:
            list of spotify devices connected to the user.
        """
        try:
            # TODO: Cache for a brief time
            devices = self._get('me/player/devices')['devices']
            return devices
        except Exception as e:
            LOG.error(e)

    def status(self):
        """ Get current playback status (across the Spotify system) """
        try:
            return self._get('me/player/currently-playing')
        except Exception as e:
            LOG.error(e)
            return None

    def is_playing(self, device=None):
        """ Get playback state, either across Spotify or for given device.
        Args:
            device (int): device id to check, if None playback on any device
                          will be reported.

        Returns:
            True if specified device is playing
        """
        try:
            status = self.status()
            if not status["is_playing"] or device is None:
                return status["is_playing"]

            # Verify it is playing on the given device
            dev = self.get_device(device)
            return dev and dev["is_active"]
        except:
            # Technically a 204 return from status() request means 'no track'
            return False  # assume not playing

    def transfer_playback(self, device_id, force_play=True):
        """ Transfer playback to another device.
        Arguments:
            device_id (int):      transfer playback to this device
            force_play (boolean): true if playback should start after
                                  transfer
        """
        data = {
            'device_ids': [device_id],  # Doesn't allow more than one
            'play': force_play
        }
        try:
            return self._put("me/player", payload=data)
        except Exception as e:
            LOG.error(e)

    def play(self, device, uris=None, context_uri=None):
        """ Start playback of tracks, albums or artist.

        Can play either a list of uris or a context_uri for things like
        artists and albums. Both uris and context_uri shouldn't be provided
        at the same time.

        Args:
            device (int):      device id to start playback on
            uris (list):       list of track uris to play
            context_uri (str): Spotify context uri for playing albums or
                               artists.
        """
        data = {}
        if uris:
            data['uris'] = uris
        elif context_uri:
            data['context_uri'] = context_uri
        path = 'me/player/play?device_id={}'.format(device)
        try:
            self._put(path, payload=data)
        except Exception as e:
            LOG.error(e)

    def pause(self, device):
        """ Pause user's playback on device.

        Arguments:
            device_id: device to pause
        """
        LOG.debug('Pausing Spotify playback')
        try:
            self._put('me/player/pause?device_id={}'.format(device))
        except Exception as e:
            LOG.error(e)

    def next(self, device):
        """ Skip track.

        Arguments:
            device_id: device id for playback
        """
        LOG.info('This was terrible, let\'s play the next track')
        try:
            self._post('me/player/next?device_id={}'.format(device))
        except Exception as e:
            LOG.error(e)

    def prev(self, device):
        """ Move back in playlist.

        Arguments
            device_id: device target for playback
        """
        LOG.debug('That was pretty good, let\'s listen to that again')
        try:
            self._post('me/player/previous?device_id={}'.format(device))
        except Exception as e:
            LOG.error(e)

    def volume(self, device, volume):
        """ Set volume of device:

        Parameters:
            device: device id
            volume: volume in percent
        """
        uri = 'me/player/volume?volume_percent={}&device_id={}'.format(volume,
                                                                       device)
        try:
            self._put(uri)
        except Exception as e:
            LOG.error(e)


class SpotifySkill(MycroftSkill):
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

        self.__device_list = None
        self.__devices_fetched = 0
        self.OAUTH_ID = 1
        self.DEFAULT_VOLUME = 65
        self._playlists = None

    def launch_librespot(self):
        """ Launch the librespot binary for the Mark-1.
        TODO: Discovery mode
        """
        platform = self.config_core.get("enclosure").get("platform", "unknown")
        path = self.settings.get('librespot_path', None)
        if platform == 'mycroft_mark_1' and not path:
            path = 'librespot'

        if (path and self.device_name and
                'user' in self.settings and 'password' in self.settings):
            # TODO: Error message when provided username/password don't work
            self.process = Popen([path, '-n', self.device_name,
                                  '-u', self.settings['user'],
                                  '-p', self.settings['password']])

            time.sleep(3)  # give libreSpot time to start-up

            # Lower the volume since max volume sounds terrible on the Mark-1
            dev = self.device_by_name(self.device_name)
            if dev:
                self.spotify.volume(dev['id'], self.DEFAULT_VOLUME)

    def initialize(self):
        # Make sure the spotify login scheduled event is shutdown
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
        self.on_websettings_changed()

    def on_websettings_changed(self):
        if not self.spotify:
            try:
                self.load_credentials()
            except Exception:
                pass
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
            LOG.info('Couldn\'t fetch credentials')
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
        """ Handle auto ducking when listener is started. """
        if self.spotify.is_playing():
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

        active = DisplayManager.get_active()
        if not active == '' or active == "SpotifySkill":
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
            text = status["item"]["artists"][0]["name"] + ": "
        except:
            text = ""
        try:
            text += status["item"]["name"]
        except:
            pass

        # Update the "Now Playing" display if needed
        if text != self.mouth_text:
            self.mouth_text = text
            self.enclosure.mouth_text(text)

    ######################################################################
    # Intent handling

    def create_intents(self):
        """ Create intents for start playback handlers."""
        self.register_intent_file('PlaySomeMusic.intent', self.play_something)
        self.register_intent_file('PlayAlbum.intent', self.play_album)
        self.register_intent_file('PlaySong.intent', self.play_song)

        # play playlists
        self.register_intent_file('Play.intent', self.play_playlist)
        self.register_intent_file('PlayOn.intent', self.play_playlist_on)

    @property
    def playlists(self):
        """ Playlists, cached for 5 minutes """
        now = time.time()
        if not self._playlists or (now - self.__playlists_fetched > 5 * 60):
            self._playlists = {}
            playlists = self.spotify.current_user_playlists().get('items', [])
            for p in playlists:
                self._playlists[p['name']] = p
            self.__playlists_fetched = now
        return self._playlists

    @property
    def devices(self):
        """ Devices, cached for 60 seconds """
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
            key, confidence = match_one(name, devices_by_name.keys())
            return devices_by_name[key]

    def get_default_device(self):
        """ Get preferred playback device """
        if self.spotify:
            # When there is an active Spotify device somewhere, use it
            if (self.devices and len(self.devices) > 0 and
                    self.spotify.is_playing()):
                for dev in self.devices:
                    if dev['is_active']:
                        return dev  # Use this device

            # No playing device found, use the local Spotify instance
            dev = self.device_by_name(self.device_name)
            if not dev:
                dev = self.device_by_name(gethostname())
            if dev and not dev['is_active']:
                self.spotify.transfer_playback(dev["id"], False)
            return dev

        return None

    def get_best_playlist(self, playlist):
        """ Get best playlist matching the provided name

        Arguments:
            playlist (str): Playlist name

        Returns: (str) best match
        """
        key, confidence = match_one(playlist, self.playlists.keys())
        if confidence > 0.5:
            return key
        else:
            return None

    def play_song(self, message):
        """
        When the user wants to hear a song, optionally with artist and/or album information attached
        play the song <song>
        play the song <song> by <artist>
        play the song <song> off <album>
        play <song> by <artist> off the album <album>
        etc.
        :param message: the utterance as interpreted by Padatious
        """
        song = message.data.get('track')
        artist = message.data.get('artist')
        album = message.data.get('album')
        # workaround for Padatious training:
        if song and not album:
            m = re.match(r'^play (some |a )?(something|music|track)( by ([\w\s]+?))?$', message.data['utterance'], re.M|re.I)
            if m:
                LOG.info("I'm in the play_song handler but I think I'm actually being asked to play something indeterminate. Switching handlers.")
                self.play_something(message)
                return

        query = song
        LOG.info("I've been asked to play a particular song.")
        LOG.info("\tI think the song is: " + song)
        if artist:
            query += " artist:" + artist
            LOG.info("\tI also think the artist is: " + artist)

        if album:
            query +=" album:" + album
            LOG.info("\tI also think the album is: " + album)

        LOG.info("The query I want to send to Spotify is: '" + query + "'")
        res = self.spotify.search(query, type='track')
        self.play(data=res, type='track')

    def play_album(self, message):
        """
        When the user wants to hear an album, optionally with artist informaiton attached
        "Play the album <album> by <artist>
        :param message: the utterance as interpreted by Padatious
        """
        album = message.data.get('album')
        artist = message.data.get('artist')
        query = album
        LOG.info("I've been asked to play a particular album.")
        LOG.info("\tI think the album is: " + album)
        if artist:
            query += " artist:" + artist
            LOG.info("\tI also think the artist is: " + artist)

        LOG.info("The query I want to send to Spotify is: '" + query + "'")
        res = self.spotify.search(query, type='album')
        self.play(data=res, type='album')

    def play_something(self, message):
        """
        When the user wants to hear something (optionally by an artist), but they don't know what
        play something
        play something by <artist>
        :param message: the utterance as interpreted by Padatious
        """
        LOG.info("I've been asked to play pretty much anything.")
        artist = message.data.get('artist')
        genres = ["rap", "dance", "pop", "hip hop", "rock", "trap", "classic rock", "metal", "edm", "techno", "house"]
        query = ""
        if artist:
            LOG.info("\tBut it has to be by " + artist)
            query = "artist:" + artist
        else:
            genre = random.choice(genres)
            LOG.info("\tI'm going to pick the genre " + genre)
            query = "genre:" + genre
            res = self.spotify.search(query, type='track')
            LOG.info("\tgot results")
            self.play(data=res, type='genre', genreName = genre)


    def play_playlist(self, message):
        """ Play user playlist on default device. """
        playlist = message.data.get('playlist')
        if not playlist or playlist == 'spotify':
            self.continue_current_playlist(message)
        elif self.playback_prerequisits_ok():
            dev = self.get_default_device()
            self.start_playback(dev, self.get_best_playlist(playlist))

    def playback_prerequisits_ok(self):
        """ Check that playback is possible, launch client if neccessary. """
        if self.spotify is None:
            self.speak_dialog('NotAuthorized')
            return False

        if not self.process:
            self.launch_librespot()
        return True

    @intent_handler(IntentBuilder('').require('Play').require('Spotify'))
    def play_spotify(self, message):
        # Play anything
        if self.playback_prerequisits_ok():
            message.data['utterance'] = 'play spotify'  # play anything!
            self.play_playlist(message)
        else:
            self.speak_dialog("NotAuthorized")

    def spotify_play(self, dev_id, uris=None, context_uri=None):
        """ Start spotify playback and catch any exceptions. """
        try:
            LOG.info(u'spotify_play: {}'.format(dev_id))
            self.spotify.play(dev_id, uris, context_uri)
            self.start_monitor()
            self.dev_id = dev_id
            # self.show_notes()
        except spotipy.SpotifyException as e:
            # TODO: Catch other conditions?
            self.speak_dialog('NotAuthorized')
        except Exception as e:
            LOG.exception(e)
            self.speak_dialog('NotAuthorized')

    def start_playback(self, dev, playlist_name):
        LOG.info(u'Playlist: {}'.format(playlist_name))
        
        playlist = None
        if playlist_name:
            playlist = self.get_best_playlist(playlist_name)
        if not playlist:
            LOG.info(u'Playlists: {}'.format(self.playlists))
            if not self.playlists:
                return  # different default action when no lists defined?
            playlist = self.get_best_playlist(self.playlists.keys()[0])
            
        if dev and playlist:
            LOG.info(u'playing {} using {}'.format(playlist, dev['name']))
            self.speak_dialog('listening_to', data={'tracks': playlist})
            time.sleep(2)
            pl = self.playlists[playlist]
            tracks = self.spotify.user_playlist_tracks(pl['owner']['id'],
                                                       pl['id'])
            uris = [t['track']['uri'] for t in tracks['items']]
            self.spotify_play(dev['id'], uris=uris)
            # self.show_notes()
        elif dev:
            LOG.info(u'couldn\'t find {}'.format(playlist))
        else:
            LOG.info('No spotify devices found')

    def play_playlist_on(self, message):
        """ Play playlist on specific device. """
        if self.playback_prerequisits_ok():
            playlist = self.get_best_playlist(message.data.get('playlist'))
            dev = self.device_by_name(message.data.get('device'))
            if dev:
                # Assume we are about to act on this device,
                # transfer playback to it.
                if not dev['is_active']:
                    self.spotify.transfer_playback(dev["id"], False)
                self.start_playback(dev, playlist)

#    @intent_file_handler('PlaySpotify.intent')
#    def continue_current_playlist(self, message):
#        if self.playback_prerequisits_ok():
#            dev = self.get_default_device()
#            if dev:
#                self.spotify_play(dev['id'])
#            else:
#                self.speak_dialog('NoDevicesAvailable')

    def play(self, data, type='track', genreName=None):
        """

        :param data: data returned by self.search_spotify
        :param type: the type of data. 'track', 'album', or 'genre' are currently supported
        :param genreName: if type is 'genre', also include the genre's name here, for output purposes
        """
        dev = self.get_default_device()
        if dev is None:
            LOG.error("Unable to get a default device while trying to play something.")
            self.speak_dialog('NoDevicesAvailable')
        else:
            try:
                if type is 'track':
                    song = data['tracks']['items'][0]
                    self.speak_dialog('listening_to_song_by', data={'tracks': song['name'], 'artist': song['artists'][0]['name']})
                    time.sleep(2)
                    self.spotify_play(dev['id'], uris=[song['uri']])
                elif type is 'album':
                    album = data['albums']['items'][0]
                    self.speak_dialog('listening_to_album_by', data={'album': album['name'], 'artist': album['artists'][0]['name']})
                    self.speak_dialog('listening_to_album_by', data={'album': album['name'], 'artist': album['artists'][0]['name']})
                    time.sleep(2)
                    self.spotify_play(dev['id'], context_uri=album['uri'])
                elif type is 'genre':
                    items = data['tracks']['items']
                    random.shuffle(items)
                    uris = []
                    for item in items:
                        uris.append(item['uri'])
                    self.speak_dialog('listening_to_genre', data={'genre': genreName, 'track': items[0]['name'], 'artist': items[0]['artists'][0]['name']})
                    time.sleep(2)
                    self.spotify_play(dev['id'], uris=uris)
            except Exception as e:
                LOG.error("Unable to obtain the name, artist, and/or URI information while asked to play something. " + str(e))

    def search(self, query, search_type):
        """ Search for an album, playlist or artist.
        Arguments:
            query:       search query (album title, artist, etc.)
            search_type: weather to search for an 'album', 'artist',
                         'playlist', 'track', or 'genre'

            TODO: improve results of albums by checking artist
        """
        dev = self.get_default_device()
        res = None
        if search_type == 'album' and len(query.split('by')) > 1:
            title, artist = query.split('by')
            result = self.spotify.search(title, type=search_type)
        else:
            result = self.spotify.search(query, type=search_type)

        if search_type == 'album':
            if len(result['albums']['items']) > 0 and dev:
                album = result['albums']['items'][0]
                LOG.info(album)
                res = album
        elif search_type == 'artist':
            LOG.info(result['artists'])
            if len(result['artists']['items']) > 0:
                artist = result['artists']['items'][0]
                LOG.info(artist)
                res = artist
        elif search_type == 'genre':
            LOG.info("TODO! Genre")
        else:
            LOG.info('ERROR')
            return

        #if res:
        #    self.speak_dialog('listening_to', data={'tracks': res['name']})
        #    time.sleep(2)
        #    self.spotify_play(dev['id'], context_uri=res['uri'])
        #else:
        #    self.speak_dialog('NoResults')
        return res

    def __pause(self):
        # if authorized and playback was started by the skill
        if self.spotify:
            LOG.info('Pausing Spotify...')
            self.spotify.pause(self.dev_id)

    def pause(self, message=None):
        """ Handler for playback control pause. """
        self.ducking = False
        self.__pause()

    def resume(self, message=None):
        """ Handler for playback control resume. """
        # if authorized and playback was started by the skill
        if self.spotify:
            LOG.info('Resume Spotify')
            if not self.dev_id:
                self.dev_id = self.get_default_device()
            self.spotify_play(self.dev_id)

    def next_track(self, message):
        """ Handler for playback control next. """
        # if authorized and playback was started by the skill
        if self.spotify and self.dev_id:
            LOG.info('Next Spotify track')
            self.spotify.next(self.dev_id)
            self.start_monitor()

    def prev_track(self, message):
        """ Handler for playback control prev. """
        # if authorized and playback was started by the skill
        if self.spotify and self.dev_id:
            LOG.info('Previous Spotify track')
            self.spotify.prev(self.dev_id)
            self.start_monitor()

    @intent_handler(IntentBuilder('').require('Spotify').require('Device'))
    def list_devices(self, message):
        """ List available devices. """
        LOG.info(self)
        if self.spotify:
            devices = [d['name'] for d in self.spotify.get_devices()]
            if len(devices) == 1:
                self.speak(devices[0])
            elif len(devices) > 1:
                self.speak_dialog('AvailableDevices',
                                  {"devices": '. '.join(devices[:-1]) + ". " +
                                              self.translate("And") + ". " +
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
                self.spotify.transfer_playback(dev['id'])

    def show_notes(self):
        """ show notes, HA HA """
        self.schedule_repeating_event(self._update_notes,
                                      datetime.datetime.now(), 2,
                                      name='dancing_notes')

    def display_notes(self):
        """ Start timer thread displaying notes on the display. """
        pass

    def clear_display(self):
        """ Clear display. """
        self.enclosure.mouth_display(img_code="HIAAAAAAAAAAAAAA",
                                     refresh=False)
        self.enclosure.mouth_display(img_code="HIAAAAAAAAAAAAAA",
                                     x=24, refresh=False)

    def draw_notes(self, index):
        """ Draw notes on display. """

        notes = [['IIAEAOOHGAGEGOOHAA', 'IIAAACAHPDDADCDHPD'],
                 ['IIAAACAHPDDADCDHPD', 'IIAEAOOHGAGEGOOHAA']]

        #  draw notes
        for pos in range(4):
            self.enclosure.mouth_display(img_code=notes[index][pos % 2],
                                         x=pos * 8,
                                         refresh=False)

    def _update_notes(self):
        """ Repeating event updating the display. """
        if self._should_display_notes():
            self.draw_notes(self.index)
            self.index = ((self.index + 1) % 2)

    def stop(self):
        """ Stop playback. """
        if not self.spotify or not self.spotify.is_playing():
            self.dev_id = None
            return False

        dev = self.get_default_device()
        self.dev_id = dev['id']
        if self.dev_id:
            # self.remove_event('dancing_notes')
            self.pause(None)

            # Clear playing device id
            self.dev_id = None
            return True

    def stop_librespot(self):
        """ Send Terminate signal to librespot if it's running. """
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            self.process.communicate() # Communicate to remove zombie

    def shutdown(self):
        """ Remove the monitor at shutdown. """
        self.stop_monitor()
        self.stop_librespot()

        # Do normal shutdown procedure
        super(SpotifySkill, self).shutdown()

    def _should_display_notes(self):
        _get_active = DisplayManager.get_active
        if _get_active() == '' or _get_active() == self.name:
            return True
        else:
            return False


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
