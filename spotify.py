import json
import os
from os.path import join, exists
from shutil import move
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
from requests import HTTPError
import time

from mycroft.api import DeviceApi
from mycroft.util.log import LOG

from .auth import AUTH_DIR, SCOPE


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

    def get_access_token(self, force=False):
        if (not self.access_token or time.time() > self.expiration_time or
                force):
            d = get_token(self.dev_cred)
            self.access_token = d['access_token']
            # get expiration time from message, if missing assume 1 hour
            self.expiration_time = d.get('expiration') or time.time() + 3600
        return self.access_token


def refresh_auth(func):
    """This refresh is only for the old Mycroft OAuth2 auth backend."""
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except HTTPError as e:
            if (e.response.status_code == 401 and
                    isinstance(self.credentials_manager,
                               MycroftSpotifyCredentials)):
                self.client_credentials_manager.get_access_token(force=True)
                return func(self, *args, **kwargs)
            else:
                raise
    return wrapper


def load_local_credentials(user):
    if not exists(AUTH_DIR):
        os.mkdir(AUTH_DIR)

    token_cache = join(AUTH_DIR, 'token')

    # Move old creds to config path
    old_cache_file = '.cache-{}'.format(user)
    if not exists(token_cache) and exists(old_cache_file):
        move(old_cache_file, token_cache)

    # Load stored oauth credentials if exists
    auth_cache = join(AUTH_DIR, 'auth')
    if exists(auth_cache):
        with open(auth_cache) as f:
            auth = json.load(f)
        os.environ['SPOTIPY_CLIENT_ID'] = auth['client_id']
        os.environ['SPOTIPY_CLIENT_SECRET'] = auth['client_secret']

    return SpotifyOAuth(username=user,
                        redirect_uri='https://localhost:8888',
                        scope=SCOPE,
                        cache_path=token_cache)


class SpotifyConnect(spotipy.Spotify):
    """ Implement the Spotify Connect API.
    See:  https://developer.spotify.com/web-api/

    This class extends the spotipy.Spotify class with Spotify Connect
    methods since the Spotipy module including these isn't released yet.
    """

    @refresh_auth
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
            return []

    @refresh_auth
    def status(self):
        """ Get current playback status (across the Spotify system) """
        try:
            return self._get('me/player/currently-playing')
        except Exception as e:
            LOG.error(e)
            return None

    @refresh_auth
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
        except Exception:
            # Technically a 204 return from status() request means 'no track'
            return False  # assume not playing

    @refresh_auth
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

    @refresh_auth
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

    @refresh_auth
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

    @refresh_auth
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

    @refresh_auth
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

    @refresh_auth
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

    @refresh_auth
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


def get_show_info(data):
    """ Get podcast info from data object.
    Arguments:
        data: data structure from spotify
    Returns: tuple with (name, uri)
    """
    from pprint import pprint
    pprint(data['shows']['items'][0])
    return (data['shows']['items'][0]['name'],
            data['shows']['items'][0]['uri'])


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
