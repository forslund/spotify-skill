import sys
from os.path import dirname, abspath, basename
import time

from mycroft.skills.core import MycroftSkill, intent_handler
from mycroft.util.log import getLogger
from adapt.intent import IntentBuilder

from spotipy import Spotify

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

    def stop(self):
        print "stopping spotify"
        device = self.spotify.get_devices()
        print device
        if device:
            dev_id = device['devices'][0]['id']
            self.spotify.pause(dev_id)


def create_skill():
    return SpotifySkill()
