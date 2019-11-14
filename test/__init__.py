import json
from os.path import dirname, join

from test.integrationtests.skills.skill_tester import SkillTest

import mock


def load_mock_data(filename):
    path = join(dirname(__file__), 'data', filename)
    with open(path) as f:
        return json.load(f)


def test_runner(skill, example, emitter, loader):

    s = [s for s in loader.skills if s and s.root_dir == skill]
    mockify = mock.MagicMock()
    if example.endswith('what.devices.json'):
        devices = [{u'name': u'TESTING', u'volume_percent': 65,
                    u'is_active': False, u'is_restricted': False,
                    u'type': u'Speaker',
                    u'id': u'b2abb4a01ca748c4cee2c57aad1174141d531710'}]

        s[0].spotify = mockify
        s[0].spotify.get_devices.return_value = devices
        s[0].spotify.is_playing.return_value = False
        res = SkillTest(skill, example, emitter).run(loader)
    elif (example.endswith('something.by.the.beatles.json') or
          example.endswith('the.artist.the.beatles.json')):
        mockify.search.return_value = load_mock_data('beatles.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('the beatles', type='artist')
    elif example.endswith('music.by.miley.cyrus.json'):
        mockify.search.return_value = load_mock_data('miley_cyrus.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('miley cyrus', type='artist')
    elif example.endswith('songs.by.queen.json'):
        mockify.search.return_value = load_mock_data('queen.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('queen', type='artist')
    elif example.endswith('the.album.abbey.road.json'):
        mockify.search.return_value = load_mock_data('abbey_road.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('abbey road', type='album')
    elif example.endswith('the.album.appetite.for.destruction.json'):
        mockify.search.return_value = load_mock_data(
                'appetite_for_destruction.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('appetite for destruction',
                                          type='album')
    elif (example.endswith('track.1999.json') or
          example.endswith('song.1999.json')):
        mockify.search.return_value = load_mock_data('1999.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('1999', type='track')
    elif example.endswith('track.dont.stop.believin.json'):
        mockify.search.return_value = load_mock_data('dont_stop_believin.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('don\'t stop believin', type='track')
    elif example.endswith('the.song.enter.sandman.json'):
        mockify.search.return_value = load_mock_data('enter_sandman.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('enter sandman', type='track')
    elif example.endswith('the.track.crazy.json'):
        mockify.search.return_value = load_mock_data('crazy.json')
        s[0].spotify = mockify
        res = SkillTest(skill, example, emitter).run(loader)
        mockify.search.assert_called_with('crazy', type='track')
    else:
        print('\n\nERROR: Example {} has no mock!\n\n'.format(example))

    return res
