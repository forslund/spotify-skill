from mycroft import MycroftSkill
from enum import Enum
from abc import ABC, abstractmethod
from mycroft.skills.audioservice import AudioService
from mycroft.messagebus.message import Message


class CPSMatchLevel(Enum):
        EXACT = 1
        MULTI_KEY = 2
        TITLE = 3
        ARTIST = 4
        CATEGORY = 5
        GENERIC = 6


class CommonPlaySkill(MycroftSkill, ABC):
    def __init__(self, name=None, bus=None):
        super().__init__(name, bus)
        self.audioservice = None

    def bind(self, bus):
        if bus:
            super().bind(bus)
            self.audioservice = AudioService(self.bus)
            self.add_event('play:query', self.__handle_play_query)
            self.add_event('play:start', self.__handle_play_start)

    def __handle_play_query(self, message):
        phrase = message.data["phrase"]
        result = self.CPS__match_query_phrase(phrase)
        print('##########################')
        print(result)
        if result:
            match = result[0]
            level = result[1]
            callback = result[2] if len(result) > 2 else None
            confidence = self.__calc_confidence(match, phrase, level)
            self.bus.emit(message.response({"phrase": phrase,
                                            "skill_id": self.skill_id,
                                            "callback_data": callback,
                                            "conf": confidence}))

    def __calc_confidence(self, match, phrase, level):
        if level == CPSMatchLevel.EXACT:
            return 1.0
        elif level == CPSMatchLevel.MULTI_KEY:
            return 0.9
        elif level == CPSMatchLevel.TITLE:
            return 0.8
        elif level == CPSMatchLevel.ARTIST:
            return 0.7
        elif level == CPSMatchLevel.CATEGORY:
            return 0.6
        elif level == CPSMatchLevel.GENERIC:
            return 0.5
        else:
            return 0.0  # should never happen

    def __handle_play_start(self, message):
        if message.data["skill_id"] != self.skill_id:
            # Not for this skill!
            return
        phrase = message.data["phrase"]
        data = message.data.get("callback_data")

        # Stop any currently playing audio
        if self.audioservice.is_playing:
            self.audioservice.stop()
        self.bus.emit(Message("mycroft.stop"))

        # Save for play() later, e.g. if phrase includes service modifiers like
        # "... on the chromecast"
        self.play_service_string = phrase

        # Invoke derived class to provide playback data
        self.CPS__start(phrase, data)

    def CPS__play(self, url):
        """
        Begin playback of media pointed to by 'url'

        Args:
            url (str): Audio to play
        """
        self.audioservice.play(url, self.play_service_string)

    def stop(self):
        if self.audioservice.is_playing:
            self.audioservice.stop()
            return True
        else:
            return False

    ######################################################################
    # Abstract methods
    # All of the following must be implemented by a skill that wants to
    # act as a CommonPlay Skill
    @abstractmethod
    def CPS__match_query_phrase(self, phrase):
        """
        Analyze phrase to see if it is a play-able phrase with this
        skill.

        Args:
            phrase (str): User phrase uttered after "Play", e.g. "some music"

        Returns:
            (match, CPSMatchLevel[, callback_data]) or None: Tupple containing
                 a string with the appropriate matching phrase, the PlayMatch
                 type, and optionally data to return in the callback if the
                 match is selected.
        """
        # Derived classes must implement this, e.g.
        #
        # if phrase in ["Zoosh"]:
        #     return ("Zoosh", CPSMatchLevel.Generic, {"hint": "music"})
        # or:
        # zoosh_song = find_zoosh(phrase)
        # if zoosh_song and "Zoosh" in phrase:
        #     # "play Happy Birthday in Zoosh"
        #     return ("Zoosh", CPSMatchLevel.MULTI_KEY, {"song": zoosh_song})
        # elif zoosh_song:
        #     # "play Happy Birthday"
        #     return ("Zoosh", CPSMatchLevel.TITLE, {"song": zoosh_song})
        # elif "Zoosh" in phrase
        #     # "play Zoosh"
        #     return ("Zoosh", CPSMatchLevel.GENERIC, {"cmd": "random"})
        return None

    @abstractmethod
    def CPS__start(self, phrase, data):
        """
        Begin playing whatever is specified in 'phrase'

        Args:
            phrase (str): User phrase uttered after "Play", e.g. "some music"
            data (dict): Callback data specified in match_query_phrase()
        """
        # Derived classes must implement this, e.g.
        # self.play("http://zoosh.com/stream_music")
        pass


