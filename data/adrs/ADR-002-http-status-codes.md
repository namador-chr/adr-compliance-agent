# ADR-002: HTTP Status Codes

## Status
Accepted

## Date
2024-01-15

## Context
Correct and consistent HTTP status codes are critical for REST API consumers to handle responses accurately. Using incorrect or vague status codes (e.g., always returning 200 OK) makes error handling difficult and violates REST semantics.

## Decision
All API endpoints MUST return semantically correct HTTP status codes according to the following rules.

### Rules (used for automated compliance checking)

1. **RULE-002-A**: Successful resource creation (POST) MUST return `201 Created`, not `200 OK`.
   - ✅ Compliant: `return CreatedAtAction(...)` or `return StatusCode(201, ...)`
   - ❌ Non-compliant: `return Ok(newResource)` on a POST endpoint

2. **RULE-002-B**: When a requested resource is not found, the endpoint MUST return `404 Not Found`.
   - ✅ Compliant: `return NotFound()` when the resource does not exist
   - ❌ Non-compliant: `return Ok(null)`, `return Ok("")`, returning 200 with empty body

3. **RULE-002-C**: Validation failures (bad input from client) MUST return `400 Bad Request`.
   - ✅ Compliant: `return BadRequest(...)` or `return ValidationProblem(...)`
   - ❌ Non-compliant: `return StatusCode(500, ...)` for validation errors, `return Ok(...)`

4. **RULE-002-D**: Successful DELETE operations with no content to return MUST return `204 No Content`.
   - ✅ Compliant: `return NoContent()` on DELETE
   - ❌ Non-compliant: `return Ok()`, `return Ok(true)` on DELETE

5. **RULE-002-E**: Unhandled server-side errors MUST result in `500 Internal Server Error` (via global exception middleware), NOT leaking stack traces as 200 responses.
   - ✅ Compliant: Global exception handler middleware returning `ProblemDetails` with status 500
   - ❌ Non-compliant: Catching exceptions and returning `return Ok(ex.Message)`

6. **RULE-002-F**: Endpoints MUST declare expected response types using `[ProducesResponseType]` attributes.
   - ✅ Compliant: `[ProducesResponseType(typeof(UserDto), StatusCodes.Status200OK)]`
   - ❌ Non-compliant: No `[ProducesResponseType]` attributes on controller actions

## Consequences
- **Positive**: Clients can rely on status codes for automated error handling; better API documentation.
- **Negative**: Requires discipline across the team and code review enforcement.

## Compliance Signals (for automated analysis)
- Search for POST endpoints returning `return Ok(...)` — should be `CreatedAtAction` or 201.
- Search for GET/DELETE endpoints — verify `NotFound()` is used when null is returned from service.
- Search for DELETE endpoints — verify they return `NoContent()`.
- Search for try/catch blocks that swallow exceptions and return `Ok(...)`.
- Search for presence of `[ProducesResponseType]` on each public action method.
