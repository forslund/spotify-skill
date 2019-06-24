import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from requests import HTTPError
import time

from mycroft.api import DeviceApi
from mycroft.util.log import LOG

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
        if e.response.status_code == 401:  # Device isn't paired
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
            if not status['is_playing'] or device is None:
                return status['is_playing']

            # Verify it is playing on the given device
            dev = self.get_device(device)
            return dev and dev['is_active']
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
            return self._put('me/player', payload=data)
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
            raise

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

    def shuffle(self, state):
        """ Toggle shuffling

            Parameters:
                state: Shuffle state
        """
        uri = 'me/player/shuffle?state={}'.format(state)
        try:
            self._put(uri)
        except Exception as e:
            LOG.error(e)

    def shutdown(self):
        """ Shutdown instance. """
        pass


def get_album_info(data):
    """ Get album info from data object.
    Arguments:
        data: data structure from spotify
    Returns: tuple with name, [artists], uri)
    """
    return (data['albums']['items'][0]['name'],
            [a['name'] for a in data['albums']['items'][0]['artists']],
            data['albums']['items'][0]['uri'])


def get_artist_info(data):
    """ Get artist info from data object.
    Arguments:
        data: data structure from spotify
    Returns: tuple with name, uri)
    """
    return (data['artists']['items'][0]['name'],
            data['artists']['items'][0]['uri'])


def get_song_info(data):
    """ Get song info from data object.
    Arguments:
        data: data structure from spotify
    Returns: tuple with name, [artists], uri)
    """
    return (data['tracks']['items'][0]['name'],
            [a['name'] for a in data['tracks']['items'][0]['artists']],
            data['tracks']['items'][0]['uri'])


session = None


class LibSpotify(SpotifyConnect):
    def __init__(self, user, password, client_credentials_manager=None):
        super().__init__(
            client_credentials_manager=client_credentials_manager)
        global spotify
        global session

        print('!!!!!!!!!!!!')
        print(session)
        import spotify
        from threading import Event

        if not session:
            config = spotify.Config()
            config.load_application_key_file('/home/ake/appkey.key')
            config.tracefile = b'/tmp/spotify.log'
            session = spotify.Session(config)

        self.session = session
        # Process events in the background
        self.loop = spotify.EventLoop(session)
        self.loop.start()

        # Connect an audio sink
        self.audio = spotify.AlsaSink(self.session)

        self.session.on(spotify.SessionEvent.END_OF_TRACK,
                        self.on_track_end)
        self.session.on(spotify.SessionEvent.CONNECTION_STATE_UPDATED,
                        self.on_connection_state_updated)
        self.logged_in = Event()
        self.session.login(user, password)
        self.logged_in.wait()

    def on_connection_state_updated(self, session):
        print('CONNECTION STATE UPDATED!')
        print(session.connection.state)
        if session.connection.state is spotify.ConnectionState.LOGGED_IN:
            self.logged_in.set()
            print("LOGGED IN")

    def _play_current_track(self):
        track = track = self.session.get_track(self.track_list[self.track]) \
                                               .load()
        self.session.player.load(track)
        self.session.player.play()

    def on_track_end(self, session):
        print("TRACK END, Jumping to next!")
        self.track += 1
        if self.track < len(self.track_list):
            self._play_current_track()
        else:
            self.track = 0

    def play(self, _, uri=None, context_uri=None):
        print(uri, context_uri)
        if isinstance(uri, str):
            self.track_list = [uri]
        elif isinstance(uri, list):
            self.track_list = uri
        elif context_uri and context_uri.startswith('spotify:album:'):
            # Extract uri's from album tracklist
            tracks = self.album_tracks(context_uri)
            self.track_list = [t['uri'] for t in tracks['items']]
        elif context_uri and context_uri.startswith('spotify:artist:'):
            tracks = self.artist_top_tracks(context_uri)
            print(tracks.keys())
            self.track_list = [t['uri'] for t in tracks['tracks']]
        else:
            raise ValueError('Invalid uri/context_uri')

        self.track = 0
        self._play_current_track()

    def pause(self, _=None):
        self.session.player.pause()

    def resume(self, _=None):
        self.session.player.play()

    def next(self):
        self.on_track_end(None)

    def shutdown(self):
        self.loop.stop()


if __name__ == '__main__':
    creds = MycroftSpotifyCredentials(1)
    s = LibSpotify(user='cazed', password='b0mberman',
                   client_credentials_manager=creds)

    artist_uri = 'spotify:artist:4rwTNBFIOwNFbHIraFCNl6'
    s.play('', context_uri=artist_uri)
