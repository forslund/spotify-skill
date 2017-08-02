import sys
import json
import os.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
auth = __import__('auth')




if len(sys.argv) != 2:
    print "usage: python spotify_skill USERNAME"

auth.prompt_for_user_token(sys.argv[1],
                           scope=auth.scope,
                           cache_dir=os.path.dirname(__file__))

skill_settings = os.path.join(os.path.dirname(__file__), 'settings.json')

# prepare settings dict
if os.path.exists(skill_settings):
    with open(skill_settings) as fp:
        settings = json.load(fp)
else:
    settings = {}

# update settings
settings['username'] = sys.argv[1]

# store settings
with open(skill_settings, 'w') as fp:
    json.dump(settings, fp)
