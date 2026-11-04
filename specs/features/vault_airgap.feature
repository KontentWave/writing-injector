Feature: Private vault storage isolation
  Scenario: Reject any private storage on drive D
    Given a vault path on drive D
    When the vault boundary is checked
    Then storage is rejected
