import time
import datetime

from mycroft.skills.core import MycroftSkill, intent_handler, \
                                intent_file_handler
from mycroft.util.log import LOG
from adapt.intent import IntentBuilder

import mycroft.client.enclosure.display_manager as DisplayManager

from subprocess import Popen

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from mycroft.api import DeviceApi
from requests import HTTPError

from fuzzywuzzy.process import extractOne

def get_token(dev_cred):
    retry = False
    try:
        d = DeviceApi().get_oauth_token(dev_cred)
    except HTTPError as e:
        if e.response.status_code == 404: # Token doesn't exist
            raise
        else:
            retry = True
    if retry:
        d = DeviceApi().get_oauth_token(dev_cred)
    return d


class MycroftSpotifyCredentials(SpotifyClientCredentials):
    def __init__(self, dev_cred):
        self.dev_cred = dev_cred
        self.access_token = None
        self.expiration_time = None

    def get_access_token(self):
        if not self.access_token or time.time() > self.expiration_time:
            d = get_token(self.dev_cred)
            self.access_token = d['access_token']
            # get expiration time from message, if missing assume 1 hour
            self.expiration_time = d.get('expiration') or time.time() + 3600
        return self.access_token


class SpotifyConnect(spotipy.Spotify):
    def get_devices(self):
        LOG.debug('getting devices')
        devices = self._get('me/player/devices')['devices']
        return devices

    def play(self, device, playlist=None, album=None):
        data = {}
        if playlist:
            tracks = self.user_playlist_tracks(playlist['owner']['id'],
                                               playlist['id'])
            uris = [t['track']['uri'] for t in tracks['items']]
        elif album:
            tracks = self.album_tracks(album['id'])
            uris =[t['uri'] for t in tracks['items']]
        data['uris'] = uris
        path = 'me/player/play?device_id={}'.format(device)
        self._put(path, payload=data)

    def pause(self, device):
        """ Pause user's playback.

            Parameters:
                - device_id - device target for playback
        """
        LOG.info('Pausing spotify playback')
        try:
            self._put('me/player/pause?device_id={}'.format(device))
        except Exception as e:
            LOG.error(e)

    def next(self, device):
        """ Pause user's playback.

            Parameters:
                - device_id - device target for playback
        """
        LOG.info('Pausing spotify playback')
        try:
            self._post('me/player/next?device_id={}'.format(device))
        except Exception as e:
            LOG.error(e)

    def prev(self, device):
        """ Pause user's playback.

            Parameters:
                - device_id - device target for playback
        """
        LOG.info('Pausing spotify playback')
        try:
            self._post('me/player/previous?device_id={}'.format(device))
        except Exception as e:
            LOG.error(e)

    def volume(self, device, volume):
        """
            Set volume of device:

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
    def __init__(self):
        super(SpotifySkill, self).__init__()
        self.index = 0
        self.spotify = None
        self.spoken_goto_home = False
        self.process = None
        self.device_name = DeviceApi().get().get('name')
        self.dev_id = None
        self.launch_librespot()

    def launch_librespot(self):
        platform = self.config_core.get("enclosure").get("platform", "unknown")
        path = self.settings.get('librespot_path', None)
        if platform == 'mycroft_mark_1' and not path:
            path = 'librespot'

        if path and 'user' in self.settings and 'password' in self.settings:
            self.process = Popen([path, '-n', self.device_name,
                                  '-u', self.settings['user'],
                                  '-p', self.settings['password']])
            time.sleep(2)
            # Lower the volume since max volume sounds terrible on the Mark-1
            dev = self.get_device(self.device_name)
            self.spotify.volume(dev['id'], 30)

    def initialize(self):
        self.add_event('mycroft.audio.service.next', self.next_track)
        self.add_event('mycroft.audio.service.prev', self.prev_track)
        self.add_event('mycroft.audio.service.pause', self.pause)
        self.add_event('mycroft.audio.service.resume', self.resume)

        self.schedule_repeating_event(self.load_credentials,
                                      datetime.datetime.now(), 60,
                                      name='get_creds')

    def load_credentials(self):
        """ Repeating method trying to retrieve credentials from the
            backend.

            When credentials are found the skill connects
        """
        try:
            creds = MycroftSpotifyCredentials(1)
            self.spotify = SpotifyConnect(client_credentials_manager = creds)
        except HTTPError:
            pass

        if self.spotify:
            # Spotfy connection worked, cancel recurring event and
            # prepare for usage
            # If not able to authorize, the method will be repeated after 60
            # seconds
            self.cancel_scheduled_event('get_creds')
            self.get_playlists()
        elif not self.spoken_goto_home:
            # First time loading the skill speak a request to go to home
            # to authorize
            self.speak_dialog('Authorize')
            self.spoken_goto_home = True

    def get_playlists(self):
        """
            Fetch user's playlists.
        """
        self.playlists = {}
        playlists = self.spotify.current_user_playlists().get('items', [])
        for p in playlists:
            self.playlists[p['name']] = p

    def get_device(self, name):
        """
            Get best device matching the provided name.
        """
        # Check that there is a spotify connection
        if self.spotify is None:
            self.speak('Not authorized')
            return

        device = self.spotify.get_devices()
        if device and len(device) > 0:
            devices = {d['name']: d for d in device}
            key, confidence = extractOne(name, devices.keys())
            if confidence > 0.5:
                dev = devices[key]
            else:
                dev = device[0]
            return dev

    def get_best_playlist(self, playlist):
        """
            Get best playlist matching the desired playlist name
        """
        key, confidence = extractOne(playlist, self.playlists.keys())
        if confidence > 50:
            return key
        else:
            return None

    @intent_file_handler('Play.intent')
    def play_playlist(self, message):
        """
            Play user playlist on default device.
        """
        if self.spotify is None:
            self.speak('Not authorized')
            return
        if not self.process:
            self.launch_librespot()

        playlist = self.get_best_playlist(message.data.get('playlist'))
        dev = self.get_device(self.device_name)
        self.start_playback(dev, playlist)

    def start_playback(self, dev, playlist):
        if dev and playlist:
            LOG.info('playing {} using {}'.format(playlist, dev['name']))
            self.speak_dialog('listening_to', data={'tracks': playlist})
            time.sleep(2)
            self.spotify.play(dev['id'], self.playlists[playlist])
            self.dev_id = dev['id']
            #self.show_notes()
        elif not playlist:
            LOG.info('couldn\'t find {}'.format(playlist))
        else:
            LOG.info('No spotify devices found')

    @intent_file_handler('PlayOn.intent')
    def play_playlist_on(self, message):
        """
            Play playlist on specific device.
        """
        if self.spotify is None:
            self.speak('Not authorized')
            return
        if not self.process:
            self.launch_librespot()
        device = message.data.get('device')
        playlist = self.get_best_playlist(message.data.get('playlist'))
        dev = self.get_device(message.data.get('device'))
        self.start_playback(dev, playlist)

    @intent_file_handler('SearchAlbum.intent')
    def search_album(self, message):
        if self.spotify is None:
            self.speak('Not authorized')
            return
        if not self.process:
            self.launch_librespot()
        dev = self.get_device(self.device_name)
        result = self.spotify.search(message.data['title'], type='album')
        if len(result['albums']['items']) > 0 and dev:
            album = result['albums']['items'][0]
            self.speak_dialog('listening_to',
                              data={'tracks': album['name']})
            time.sleep(2)
            self.spotify.play(dev['id'], album=album)
            self.dev_id = dev['id']
            #self.show_notes()

    def pause(self, message):
        """
            Handler for playback control pause
        """
        LOG.info('Pause Spotify')
        if self.spotify and self.dev_id:
            self.spotify.pause(self.dev_id)

    def resume(self, message):
        """
            Handler for playback control resume
        """
        LOG.info('Resume Spotify')
        if self.spotify and self.dev_id:
            self.spotify.play(self.dev_id)

    def next_track(self, message):
        """
            Handler for playback control next
        """
        LOG.info('Next Spotify track')
        if self.spotify and self.dev_id:
            self.spotify.next(self.dev_id)

    def prev_track(self, message):
        """
            Handler for playback control prev
        """
        LOG.info('Previous Spotify track')
        if self.spotify and self.dev_id:
            self.spotify.prev(self.dev_id)

    @intent_handler(IntentBuilder('').require('Spotify').require('Device'))
    def list_devices(self, message):
        if self.spotify:
            devices = [d['name'] for d in self.spotify.get_devices()]
            if len(devices) == 1:
                self.speak(devices[0])
            elif len(devices) > 1:
                self.speak_dialog('AvailableDevices')
                for d in devices[:-1]:
                    self.speak(d)
                self.speak_dialog('And')
                self.speak(devices[-1])
            else:
                self.speak_dialog('NoDevicesAvailable')
        else:
            self.speak_dialog('NotAuthorized')

    def show_notes(self):
        """ show notes, HA HA """
        self.schedule_repeating_event(self._update_notes,
                                      datetime.datetime.now(), 2,
                                      name='dancing_notes')

    def display_notes(self):
        """
            Start timer thread displaying notes on the display.
        """
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
        """
            Repeating event updating the display.
        """
        if self._should_display_notes():
            self.draw_notes(self.index)
            self.index = ((self.index + 1) % 2)

    def stop(self):
        #self.remove_event('dancing_notes')
        self.enclosure.reset()
        self.pause(None)

        # Clear playing device id
        self.dev_id = None

    def _should_display_notes(self):
        _get_active = DisplayManager.get_active
        if _get_active() == '' or _get_active() == self.name:
            return True
        else:
            return False


def create_skill():
    return SpotifySkill()
