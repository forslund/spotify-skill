import sys
from os.path import dirname, abspath, basename
import time
from threading import Timer

from mycroft.version import CORE_VERSION_MAJOR, \
     CORE_VERSION_MINOR, CORE_VERSION_BUILD
from mycroft.skills.core import MycroftSkill, intent_handler
from mycroft.util.log import getLogger
from adapt.intent import IntentBuilder

from spotipy import Spotify

compatible_core_version_sum = 27

sum_of_core = CORE_VERSION_MAJOR + CORE_VERSION_MINOR + CORE_VERSION_BUILD
if sum_of_core >= compatible_core_version_sum:
    import mycroft.client.enclosure.display_manager as DisplayManager


sys.path.append(abspath(dirname(__file__)))
auth = __import__('auth')

logger = getLogger(abspath(__file__).split('/')[-2])


class SpotifyConnect(Spotify):
    def get_devices(self):
        print "getting devices!"
        return self._get('me/player/devices')


    def play(self, device, playlist):
        tracks = self.user_playlist_tracks(playlist['owner']['id'],
                                           playlist['id'])
        uris = [t['track']['uri'] for t in tracks['items']]
        data = {}
        data['uris'] = uris
        path = 'me/player/play?device_id={}'.format(device)
        self._put(path, payload=data)


    def pause(self, device):
        """ Pause user's playback.

            Parameters:
                - device_id - device target for playback
        """
        print 'Pausing spotify playback'
        try:
            self._put('me/player/pause?device_id={}'.format(device))
        except Exception as e:
            print e


class SpotifySkill(MycroftSkill):
    def initialize(self):
        self.index = 0
        self.timer = None
        self.tok = auth.prompt_for_user_token(self.settings['username'],
                                              auth.scope,
                                              cache_dir=dirname(__file__))
        self.spotify = SpotifyConnect(auth=self.tok)

        self.playlists = {}
        playlists = self.spotify.current_user_playlists().get('items', [])
        for p in playlists:
            self.playlists[p['name']] = p
            self.register_vocabulary(p['name'], 'PlaylistKeyword')

    @intent_handler(IntentBuilder('PlayPlaylistIntent')\
        .require('PlayKeyword')\
        .require('PlaylistKeyword')\
        .build())
    def play_playlist(self, message):
        p = message.data.get('PlaylistKeyword')
        device = self.spotify.get_devices()
        if device and len(device) > 0:
            dev_id = device['devices'][0]['id']
            print device, dev_id
            self.speak_dialog('listening_to', data={'tracks': p})
            time.sleep(2)
            self.spotify.play(dev_id, self.playlists[p])

    def display_notes(self):
        """
            Start timer thread displaying notes on the display
        """
        if not self.timer:
            self.clear_display()
            self.timer = Timer(3, self._update_notes)
            self.timer.start()

    def clear_display(self):
        #  clear screen
        self.enclosure.mouth_display(img_code="HIAAAAAAAAAAAAAA",
                                     refresh=False)
        self.enclosure.mouth_display(img_code="HIAAAAAAAAAAAAAA",
                                     x=24, refresh=False)

    def draw_notes(self, index):
        notes = [['IIAEAOOHGAGEGOOHAA', 'IIAAACAHPDDADCDHPD'],
                 ['IIAAACAHPDDADCDHPD', 'IIAEAOOHGAGEGOOHAA']]

        #  draw notes
        for pos in range(4):
            self.enclosure.mouth_display(img_code=notes[index][pos % 2],
                                         x=pos * 8,
                                         refresh=False)

    def _update_notes(self):
        """
            Timer function updating the display
        """
        if self._should_display_notes():
            self.draw_notes(self.index)
            self.index = ((self.index + 1) % 2)
        self.timer = Timer(3, self._draw_notes)
        self.timer.start()

    def stop(self):
        print "stopping spotify"
        if self.timer:
            self.timer.cancel()
            self.timer = None

        self.enclosure.reset()
        device = self.spotify.get_devices()
        print device
        if device:
            self.enclosure.reset()
            dev_id = device['devices'][0]['id']
            self.spotify.pause(dev_id)

    def _should_display_notes(self):
        _get_active = DisplayManager.get_active
        if _get_active() == '' or _get_active() == self.name:
            return True
        else:
            return False


def create_skill():
    return SpotifySkill()
