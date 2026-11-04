Feature: Rank Slovak candidates
  Scenario: Prefer clean Slovak over Czechisms
    Given a clean synthetic candidate and a Czechism variant
    When both candidates are linted
    Then the clean candidate has the higher score
