from test.integrationtests.skills.skill_tester import SkillTest

import mock

def test_runner(skill, example, emitter, loader):

    devices = [{u'name': u'TESTING', u'volume_percent': 65,
                u'is_active': False, u'is_restricted': False,
                u'type': u'Speaker',
                u'id': u'b2abb4a01ca748c4cee2c57aad1174141d531710'}]

    s = [s for s in loader.skills if s and s.root_dir == skill]
    s[0].spotify = mock.MagicMock()
    s[0].spotify.get_devices.return_value = devices
    s[0].spotify.is_playing.return_value = False
    return SkillTest(skill, example, emitter).run(loader)
