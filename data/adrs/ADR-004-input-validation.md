# ADR-004: Input Validation

## Status
Accepted

## Date
2024-01-15

## Context
Accepting and processing unvalidated input is a leading cause of bugs, data corruption, and security vulnerabilities (e.g., injection attacks, invalid state). All inputs entering the system must be validated before use.

## Decision
All API endpoints that accept client input MUST validate that input before processing. Validation MUST use Data Annotations and/or FluentValidation, and MUST be enforced at the controller boundary.

### Rules (used for automated compliance checking)

1. **RULE-004-A**: All request model/DTO classes MUST have Data Annotation validation attributes on required or constrained properties.
   - ✅ Compliant: `[Required]`, `[MaxLength(100)]`, `[EmailAddress]`, `[Range(1, int.MaxValue)]` on DTO properties
   - ❌ Non-compliant: A DTO/request model class with no validation attributes

2. **RULE-004-B**: Controllers MUST check `ModelState.IsValid` OR use `[ApiController]` attribute (which enables automatic model validation).
   - ✅ Compliant: `[ApiController]` on the controller class (implicit model state validation)
   - ✅ Compliant: Explicit `if (!ModelState.IsValid) return BadRequest(ModelState);`
   - ❌ Non-compliant: No `[ApiController]` and no manual `ModelState.IsValid` check

3. **RULE-004-C**: Controller actions MUST NOT perform business logic against data before validation is confirmed.
   - ✅ Compliant: Validate first (via `[ApiController]` or explicit check), then pass to service
   - ❌ Non-compliant: Inserting/updating data before checking ModelState

4. **RULE-004-D**: String inputs that have maximum length constraints MUST declare `[MaxLength]` or `[StringLength]`.
   - ✅ Compliant: `[MaxLength(200)] public string Name { get; set; }`
   - ❌ Non-compliant: `public string Name { get; set; }` with no length constraint

5. **RULE-004-E**: ID values received from route parameters (e.g., `{id}`) in POST/PUT/DELETE operations MUST be validated to be positive integers when the key is an integer type.
   - ✅ Compliant: `if (id <= 0) return BadRequest("Id must be positive");`
   - ❌ Non-compliant: Directly passing a route `id` to a data layer without range checking

## Consequences
- **Positive**: Early rejection of bad data; clearer error messages for consumers; reduced risk of injection and data corruption.
- **Negative**: Additional code required for DTOs and validation attributes; potential for over-validation.

## Compliance Signals (for automated analysis)
- Search for DTO/request model classes — check if properties have `[Required]`, `[MaxLength]`, `[StringLength]`, `[Range]`, or similar attributes.
- Search for controller classes — check for `[ApiController]` attribute presence.
- Search for controller actions with `[HttpPost]` or `[HttpPut]` — verify that DTOs are used (not raw primitives) and that validation attributes exist.
- Search for direct service calls immediately after parameter binding with no validation guards.
- Search for string properties in request models with no length constraint attributes.
