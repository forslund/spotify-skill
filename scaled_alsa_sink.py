import spotify
from spotify.audio import SampleType
from array import array

class ScaledAlsaSink(spotify.AlsaSink):
    """ A simple wrapper around the AlsaSink scaling down the audio data
    samples to provid a more suitable audio volume compared to speech etc.
    """
    def __init__(self, session, scale_factor=4):
        super().__init__(session)
        self.factor = scale_factor

    def _on_music_delivery(self, session, audio_format, frames, num_frames):
        if audio_format.sample_type == SampleType.INT16_NATIVE_ENDIAN:
            wavdata = array('h', frames)
            for i in range(len(wavdata)):
                wavdata[i] //= self.factor
            wavdata = wavdata.tobytes()
        else:
            print('Scaling not possible, Unsupported sample format '
                  '({})'.format(audio_format.sample_type))
            wavdata = frames
        return super()._on_music_delivery(session, audio_format,
                                          wavdata, num_frames)
