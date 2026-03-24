# ADR-001: RESTful Resource Naming

## Status
Accepted

## Date
2024-01-15

## Context
Our API must follow consistent RESTful naming conventions to ensure predictability, discoverability, and alignment with industry standards. Inconsistent naming leads to confusion for API consumers and increases maintenance burden.

## Decision
All REST API endpoints MUST follow these naming rules:

### Rules (used for automated compliance checking)

1. **RULE-001-A**: Resource names in URL paths MUST be lowercase plural nouns.
   - ✅ Compliant: `/api/users`, `/api/orders`, `/api/products`
   - ❌ Non-compliant: `/api/User`, `/api/getUsers`, `/api/user`

2. **RULE-001-B**: Route templates MUST use `[Route("api/[controller]")]` or explicit plural noun paths.
   - ✅ Compliant: `[Route("api/users")]`, `[Route("api/[controller]")]` on a `UsersController`
   - ❌ Non-compliant: `[Route("api/user")]`, `[Route("api/GetUser")]`

3. **RULE-001-C**: Action method names (controller methods) MUST NOT appear in the URL path.
   - ✅ Compliant: `GET /api/users/5` (uses HTTP verb for semantics)
   - ❌ Non-compliant: `/api/users/GetUser/5`, `/api/users/DeleteUser/5`

4. **RULE-001-D**: Identifiers in path segments MUST use `{id}` as the parameter name for single-resource lookup.
   - ✅ Compliant: `[HttpGet("{id}")]`
   - ❌ Non-compliant: `[HttpGet("{userId}")]` for the primary key, `[HttpGet("{user_id}")]`

5. **RULE-001-E**: Query parameters MUST use camelCase naming.
   - ✅ Compliant: `?pageSize=10&pageNumber=1`
   - ❌ Non-compliant: `?PageSize=10`, `?page_size=10`

## Consequences
- **Positive**: Consistent, predictable API surface; better tooling support (Swagger, client generators).
- **Negative**: Requires renaming existing resources if they do not comply, which is a breaking change for consumers.

## Compliance Signals (for automated analysis)
- Look for `[Route(...)]` attributes on controllers — check for plural nouns in lowercase.
- Look for `[HttpGet]`, `[HttpPost]`, `[HttpPut]`, `[HttpDelete]` — verify no verb or singular resource name in path.
- Look for any URL path strings containing uppercase letters, action-verb prefixes (`Get`, `Create`, `Delete`, `Update`, `Fetch`), or singular nouns where plural is expected.
- Check that `{id}` is used (not `{userId}`, `{productId}`, etc.) for the primary resource identifier.
