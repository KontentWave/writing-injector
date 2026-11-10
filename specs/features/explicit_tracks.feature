Feature: Explicit track resource selection
  Track and language selection never use prose or automatic path detection.

  Scenario: Preview an explicitly selected English serial track
    Given a synthetic English serial track layout
    When the explicit track is previewed
    Then English serial resource selection is reported without output writes

  Scenario: Reject a frame from another explicitly selected track
    Given a synthetic English serial track layout
    When the serial frame is previewed as blog
    Then the track mismatch fails without output writes
