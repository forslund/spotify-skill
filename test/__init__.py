import sys

from test.integrationtests.skills.skill_tester import SkillTest

import mock

def test_runner(skill, example, emitter, loader):

    devices = [{u'name': u'TESTING', u'volume_percent': 65,
                u'is_active': False, u'is_restricted': False,
                u'type': u'Speaker',
                u'id': u'b2abb4a01ca748c4cee2c57aad1174141d531710'}]

    if not loader.skills:
        print('Skill did not load')
        sys.exit(0)
    s = [s for s in loader.skills if s and s.root_dir == skill][0]
    s.spotify = mock.MagicMock()
    s.spotify.get_devices.return_value = devices
    s.spotify.is_playing.return_value = False
    return SkillTest(skill, example, emitter).run(loader)
