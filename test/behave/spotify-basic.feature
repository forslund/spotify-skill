Feature: Mycroft Weather Skill current local humidity

    Scenario: Check for connection
        Given an english speaking user
         When the user says "what spotify devices are available"
         Then "mycroft-spotify" should respond with devices or error
