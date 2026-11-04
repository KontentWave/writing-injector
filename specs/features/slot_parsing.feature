Feature: Parse a benign Slovak story frame
  Scenario: Extract one slot and its prose context
    Given a synthetic coffee frame
    When the frame is parsed
    Then its word bounds and two surrounding paragraphs are extracted
