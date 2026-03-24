# ADR-005: Separation of Concerns

## Status
Accepted

## Date
2024-01-15

## Context
Mixing data access logic, business logic, and HTTP concerns in the same class makes code difficult to test, maintain, and evolve. The API must follow a layered architecture that clearly separates responsibilities.

## Decision
The application MUST follow a three-layer architecture: **Controller → Service → Repository**. Each layer has clearly defined responsibilities, and no layer may bypass or duplicate another.

### Rules (used for automated compliance checking)

1. **RULE-005-A**: Controllers MUST NOT contain business logic or data access logic.
   - ✅ Compliant: Controller delegates to a service interface: `var user = await _userService.GetByIdAsync(id);`
   - ❌ Non-compliant: Controller directly instantiates or calls a DbContext, repository, or ORM

2. **RULE-005-B**: Controllers MUST depend on interfaces (abstractions), NOT concrete service implementations.
   - ✅ Compliant: Constructor parameter `IUserService userService`
   - ❌ Non-compliant: Constructor parameter `UserService userService` (concrete class)

3. **RULE-005-C**: Services MUST NOT reference `HttpContext`, `HttpRequest`, `HttpResponse`, or any ASP.NET HTTP abstractions.
   - ✅ Compliant: Service receives plain data objects (DTOs, primitives) and returns plain results
   - ❌ Non-compliant: `IHttpContextAccessor` injected into a service for non-security-related access; service returning `IActionResult`

4. **RULE-005-D**: Data access code (SQL queries, Entity Framework operations, file I/O) MUST reside in a Repository class, NOT in a Service or Controller.
   - ✅ Compliant: `_userRepository.GetByIdAsync(id)` called from the service layer
   - ❌ Non-compliant: `_dbContext.Users.FindAsync(id)` called directly from a Controller or Service

5. **RULE-005-E**: Each layer MUST depend only on the layer directly below it (no layer skipping).
   - ✅ Compliant: Controller → IUserService → IUserRepository
   - ❌ Non-compliant: Controller directly calling a repository interface; Service calling another service's repository

6. **RULE-005-F**: Constructor injection MUST be the only method of dependency injection (no service locator pattern).
   - ✅ Compliant: All dependencies declared in the constructor
   - ❌ Non-compliant: `HttpContext.RequestServices.GetService<IUserService>()` inside a class body

## Consequences
- **Positive**: Testable in isolation; clean boundaries; supports replacing implementations (e.g., swap repositories for testing).
- **Negative**: More classes and interfaces to maintain; increased initial setup cost.

## Compliance Signals (for automated analysis)
- Search for controller classes — check if they declare service interface fields (`IUserService`, `IOrderService`, etc.).
- Search for `new` keyword inside controller actions — constructing service/repository objects directly is a violation.
- Search for `DbContext` references in controllers or service classes (outside of repositories).
- Search for `HttpContext` or `IHttpContextAccessor` in service classes.
- Search for repository interface fields in controllers — controllers should not directly depend on repositories.
- Check interface usage: constructor parameters of controllers should be interfaces, not concrete classes.
