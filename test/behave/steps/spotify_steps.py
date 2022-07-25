from behave import then

from test.integrationtests.voight_kampff import (then_wait, mycroft_responses)


@then('"mycroft-spotify" should respond with devices or error')
def verify_device_response(context):
    acceptable_dialogs = ('AvailableDevices',
                          'NoDevicesAvailable',
                          'NoSettingsReceived',
                          'NotConfigured',
                          'NotAuthorized')

    def check_dialog(message):
        utt_dialog = message.data.get('meta', {}).get('dialog')
        return utt_dialog in acceptable_dialogs, ""

    passed, debug = then_wait('speak', check_dialog, context)
    if not passed:
        assert_msg = debug
        assert_msg += mycroft_responses(context)

    assert passed, assert_msg or 'Mycroft didn\'t respond'
