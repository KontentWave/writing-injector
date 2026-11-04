Feature: Mocked slot injection
  Scenario: Write reviewable drafts without changing the source
    Given a synthetic CLI run with mocked OpenRouter responses
    When injection is executed
    Then both drafts exist only in the synthetic vault output
