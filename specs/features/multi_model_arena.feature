Feature: Offline-validated report-only model comparison
  Matrix comparisons preserve synthetic sources and never choose a merged winner.

  Scenario: All planned candidates appear in arena reviews and scorecards
    Given a synthetic CLI run with mocked OpenRouter responses
    When model comparison is executed
    Then only arena review and scorecards exist in the synthetic vault output
    And every model has its planned stable candidate identities

  Scenario: A remote failure produces explicitly failed review reports
    Given a synthetic CLI run with mocked OpenRouter responses
    When comparison with a failed model is executed
    Then only arena review and scorecards exist in the synthetic vault output
    And the scorecards explicitly record the failed model
