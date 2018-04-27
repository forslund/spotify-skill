from test.integrationtests.skills.skill_tester import SkillTest

import mock

@mock.patch('spotify-skill__init__.SpotifyConnect.get_devices')
def test_runner(skill, example, emitter, loader, m1):

    devices = [{u'name': u'TESTING', u'volume_percent': 65,
                u'is_active': False, u'is_restricted': False,
                u'type': u'Speaker',
                u'id': u'b2abb4a01ca748c4cee2c57aad1174141d531710'}]
    #m1.side_effect = side_effect
    m1.return_value = devices
    return SkillTest(skill, example, emitter).run(loader)
