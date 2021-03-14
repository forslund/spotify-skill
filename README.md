# <img src='https://rawcdn.githack.com/forslund/spotify-skill/05c19c0fba8a4af150c6eb8cf2e955d59ac83d15/Spotify_Icon.png' card_color='#40db60' width='50' height='50' style='vertical-align:bottom'/> Play Spotify

**Spotify has disabled my API access for the skill, it was violating their Terms of Service by enabling voice control. I must have missed this back in 2017 when I created the skill.**

To use this skill currently you will need to create your own "application using
https://developer.spotify.com". See instructions under the heading "Personal access token"
.
Listen to music from your Spotify Premium music account

## About
Stream your favorite music from the popular Spotify music service. Spotify
Premium users can search and play tracks from their own playlists or the huge
Spotify music library.

You can also control your Mycroft device using the Spotify Connect system.
So play DJ on your phone while listening on Mycroft!

### This skill doesn't do any playback
This skill works with the Spotify Connect protocol to interact with Spotify devices, but doesn't perform any playback itself. If you want playback on the hosting Mycroft device, you'll need to set up a player yourself.

For Picroft users, [raspotify](https://github.com/dtcooper/raspotify) is a good choice.

Install it and then make changes to `/etc/default/raspotify.conf` as follows

- It is recommended to set the DEVICE_NAME to the name of the Mycroft unit (as registered at home.mycroft.ai) for automatic identification:

`DEVICE_NAME="<My Mycroft Unit>"

- set your Spotify username and password under `OPTIONS`

`OPTIONS="--username <My Username> --password <My Password>"`


You make sound work with raspotify you may need to edit `/lib/systemd/system/raspotify.service` and there change `User` and `Group` from `raspotify`to `pi`.


For desktop users the official spotify player works well.

The exception to this is the Mark-1 which is shipped with a spotify player library.

### Authorization:
This Skill uses two different methods of authentication. Both need to be filled in correctly for the **Skill** to function correctly.

#### API connection to your Spotify account
After installing `mycroft-spotify`, from the mycroft-core folder run the auth.py script in the mycroft-spotify folder

```
source venv-activate-sh
python skills/mycroft-spotify/auth.py
```

The script will try to guide you through connecting a developer account to the skill and store the credentials locally.

#### Username and password to authenticate a Mycroft device
In addition to account details, Mycroft needs to be authorized as a **device** for Spotify. To do this, we use your username and password for Spotify. These must be entered as well, or you will receive an error message like:

`I couldn't find any Spotify devices.  This skill requires a Spotify Premium account to work properly.`

when you try to use the **Skill** on a Mycroft device.

If you log in to Spotify using Facebook, your password will be your _Facebook_ password, but your Spotify device username. You can get your Spotify device username [here](https://www.spotify.com/us/account/set-device-password/).

_NOTE: You MUST have a Premium Spotify account to use this **Skill**. It will NOT work with a free Spotify account._


## Examples 
* "What Spotify devices are available?"
* "Play discover weekly"
* "Play Hello Nasty on Spotify"
* "Play something by Covenant"
* "Play the album Hello Nasty on Spotify"
* "Play my liked songs"

## Commands

### Playing music:

* "Play something by Covenant" - Will queue songs by Covenant
* "Play Background" - Will play either your playlist named "Background" or the first song result
* "Play Hello Nasty on Spotify" - Will play first song result matching the query

### Controls:
* "Play the next/previous song" - Will skip the track either forward or backwards, respectively
* "Stop/Pause the music" - Will pause the current track
* "Turn on/off spotify shuffle" - Will enable/disable shuffling on the current song queue

### Misc:
* "What Spotify devices are available?" - Will list currently available Spotify devices

## Credits 
@forslund
The Mycroft devs

## Category
**Music**

## Tags
#spotify
#music
