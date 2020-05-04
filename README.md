# <img src='https://rawcdn.githack.com/forslund/spotify-skill/05c19c0fba8a4af150c6eb8cf2e955d59ac83d15/Spotify_Icon.png' card_color='#40db60' width='50' height='50' style='vertical-align:bottom'/> Play Spotify
Listen to music from your Spotify Premium music account

## About
Stream your favorite music from the popular Spotify music service. Spotify
Premium users can search and play tracks from their own playlists or the huge
Spotify music library.

You can also control your Mycroft device using the Spotify Connect system.
So play DJ on your phone while listening on Mycroft!

### Authorization:
This Skill uses two different methods of authentication. Both need to be filled in correctly for the **Skill** to function correctly.

#### API connection to your Spotify account
After installing `mycroft-spotify`, in your [Skill
settings for Spotify](https://home.mycroft.ai/#/skill) in home.mycroft.ai you will see settings for the Spotify Skill. You will see a username and password field and a 'Connect' button. Ignore the username and password field for now, and click the 'Connect' button. You will be prompted to log in to Spotify, and to authorize Mycroft AI to use your Spotify account using OAuth. This allows Mycroft access to your account details such as Playlists.

#### Username and password to authenticate a Mycroft device
In addition to account details, Mycroft needs to be authorized as a **device** for Spotify. To do this, we use your username and password for Spotify. These must be entered as well, or you will receive an error message like:

`I couldn't find any Spot-ify devices.  This skill requires a Spotify Premium account to work properly.`

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
