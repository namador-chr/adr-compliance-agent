# Architectural Decision Records (ADR) Compliance Report

## Executive Summary
This report details the architectural compliance of the codebase against three established Architectural Decision Records (ADRs). The analysis reveals that the `UsersController` and `UserService` are currently in a state of **significant non-compliance**. The codebase violates critical RESTful standards (ADR-001), fails to implement proper HTTP semantics and documentation (ADR-002), and relies on obsolete logging practices that bypass the mandated structured logging infrastructure (ADR-003). Immediate refactoring is recommended to bring the API and service layers in line with these standards.

---

## ADR-001: RESTful Resource Naming
**Status: NOT COMPLIANT**

The resource naming implementation deviates from standard REST conventions in multiple areas.

*   **RULE-001-A (Lowercase plural nouns): VIOLATES**
    *   The route `[Route("api/user")]` uses a singular noun.
*   **RULE-001-B (Route templates): VIOLATES**
    *   The explicit route definition overrides the desired plural convention.
*   **RULE-001-C (No action methods in URL): VIOLATES**
    *   `[HttpPost("CreateUser")]` includes the method name in the path.
*   **RULE-001-D (Identifiers as `{id}`): VIOLATES**
    *   The code uses `[HttpGet("{userId}")]` instead of the mandated `{id}`.
*   **RULE-001-E (Query parameters camelCase): NOT APPLICABLE**

---

## ADR-002: HTTP Status Codes
**Status: NOT COMPLIANT**

While basic validation and error handling are present, the API fails to correctly implement RESTful responses for successful operations and lacks API documentation.

*   **RULE-002-A (201 Created): VIOLATES**
    *   The POST method returns `Ok(created)` instead of `201 Created`.
*   **RULE-002-B (404 Not Found): COMPLIANT**
    *   Correctly returns `NotFound()` for missing resources.
*   **RULE-002-C (400 Bad Request): COMPLIANT**
    *   Correctly validates `ModelState` and returns `BadRequest`.
*   **RULE-002-D (204 No Content): VIOLATES**
    *   The DELETE method returns `Ok(true)` instead of `204 No Content`.
*   **RULE-002-F (Declare response types): VIOLATES**
    *   `[ProducesResponseType]` attributes are missing across all controller actions.

---

## ADR-003: Structured Logging
**Status: NOT COMPLIANT**

The codebase fails to utilize the required logging infrastructure, relying on outdated and unstructured console output.

*   **RULE-003-A (Inject `ILogger<T>`): VIOLATES**
    *   Neither the controller nor the service uses constructor injection for logging.
*   **RULE-003-B (No `Console.WriteLine`): VIOLATES**
    *   The code is heavily permeated with `Console.WriteLine` statements (e.g., `Console.WriteLine("UserService initialized.");`).
*   **RULE-003-C (No `Debug/Trace.WriteLine`): COMPLIANT**
*   **RULE-003-D (Structured message templates): VIOLATES**
    *   Logging (via `Console.WriteLine`) uses string interpolation, which prevents the creation of structured log events.
*   **RULE-003-E (Appropriate log levels): VIOLATES**
    *   No leveled logging exists; all messages are treated with the same priority via the console.

---

### Recommendations for Remediation
1.  **Refactor Routes:** Update controller attributes to use `[Route("api/users")]` and replace `{userId}` with `{id}`. Remove action names like `CreateUser` from route paths.
2.  **Align HTTP Semantics:** Refactor `CreateUser` to return `CreatedAtAction` (201) and the `Delete` method to return `NoContent` (204). Add `[ProducesResponseType]` to all controller methods.
3.  **Modernize Logging:** Remove all instances of `Console.WriteLine`. Implement `ILogger<T>` via constructor injection in both `UsersController` and `UserService` and use structured logging templates (e.g., `_logger.LogInformation("Deleted user with id {UserId}", userId);`).