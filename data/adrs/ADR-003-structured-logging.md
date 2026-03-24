# ADR-003: Structured Logging

## Status
Accepted

## Date
2024-01-15

## Context
Applications typically use `Console.WriteLine` or ad-hoc debug logging during development, which is not suitable for production systems. Structured, leveled logging via a proper logging framework enables log aggregation, alerting, and tracing in production environments (e.g., ELK, Azure Monitor, Datadog).

## Decision
All application logging MUST use the ASP.NET Core `ILogger<T>` interface (or a compatible structured logger). `Console.WriteLine`, `Debug.WriteLine`, and direct file writes are forbidden for logging purposes.

### Rules (used for automated compliance checking)

1. **RULE-003-A**: All classes that produce logs MUST inject `ILogger<T>` via constructor injection.
   - ✅ Compliant: `private readonly ILogger<UsersController> _logger;` injected in constructor
   - ❌ Non-compliant: No `ILogger` field, or using a static logger instance

2. **RULE-003-B**: `Console.WriteLine` MUST NOT be used for logging anywhere in the application.
   - ✅ Compliant: `_logger.LogInformation("Processing request for user {UserId}", id);`
   - ❌ Non-compliant: `Console.WriteLine("Processing request for user " + id);`

3. **RULE-003-C**: `Debug.WriteLine` or `Trace.WriteLine` MUST NOT be used for logging.
   - ✅ Compliant: `_logger.LogDebug("Debug info: {Data}", data);`
   - ❌ Non-compliant: `Debug.WriteLine("debug: " + data);`

4. **RULE-003-D**: Log messages MUST use structured message templates (named placeholders), NOT string concatenation or interpolation.
   - ✅ Compliant: `_logger.LogError("Failed to find user with ID {UserId}", id);`
   - ❌ Non-compliant: `_logger.LogError($"Failed to find user with ID {id}");`
   - ❌ Non-compliant: `_logger.LogError("Failed to find user with ID " + id);`

5. **RULE-003-E**: Log level MUST be appropriate to the severity:
   - `LogInformation` for normal operational events
   - `LogWarning` for unexpected but recoverable situations
   - `LogError` for failures and exceptions (with the exception object passed)
   - ❌ Non-compliant: Using `LogInformation` for exceptions, or using no logging at all in catch blocks

## Consequences
- **Positive**: Centralized, queryable, structured logs; easier debugging in production; log correlation IDs.
- **Negative**: Minor refactoring required for legacy code using `Console.WriteLine`.

## Compliance Signals (for automated analysis)
- Search for `Console.WriteLine` — any occurrence in non-test code is a violation.
- Search for `Debug.WriteLine` or `Trace.WriteLine` — violations.
- Search for `ILogger` in constructor parameters and field declarations — must be present in controllers and services.
- Search for `_logger.Log*($"`)` or string concatenation in log calls — structured template violations.
- Verify that catch blocks call `_logger.LogError(ex, ...)` passing the exception as the first argument.
