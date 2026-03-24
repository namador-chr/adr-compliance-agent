// UsersController.cs - REST API controller for User resource
//
// ADR VIOLATIONS IN THIS FILE:
//   - ADR-001: Route uses singular "user" instead of plural "users" (RULE-001-A, RULE-001-B)
//   - ADR-001: Action method names appear in some routes (RULE-001-C)
//   - ADR-001: Uses {userId} instead of {id} (RULE-001-D)
//   - ADR-002: POST returns Ok() instead of CreatedAtAction() (RULE-002-A)
//   - ADR-002: DELETE returns Ok(true) instead of NoContent() (RULE-002-D)
//   - ADR-002: Missing [ProducesResponseType] attributes (RULE-002-F)
//   - ADR-003: Console.WriteLine used for logging (RULE-003-B)
//   - ADR-004: No [ApiController] attribute (RULE-004-B)
//   - ADR-004: No ModelState.IsValid check on POST (RULE-004-B)
//
// COMPLIANT ASPECTS:
//   - ADR-005: Controller depends on IUserService interface (compliant)
//   - ADR-002: GET returns NotFound() when user is not found (compliant)
//   - ADR-002: GET returns 200 Ok with data (compliant)

using Microsoft.AspNetCore.Mvc;
using SampleApi.DTOs;
using SampleApi.Models;
using SampleApi.Services;

namespace SampleApi.Controllers
{
    // ADR-001 VIOLATION: Route is "api/user" (singular) — should be "api/users" (plural)
    // ADR-004 VIOLATION: Missing [ApiController] attribute — no automatic model validation
    [Route("api/user")]
    public class UsersController : ControllerBase
    {
        private readonly IUserService _userService;

        // ADR-005 COMPLIANT: Depends on IUserService interface, not concrete class
        // ADR-003 VIOLATION: No ILogger<UsersController> injected
        public UsersController(IUserService userService)
        {
            _userService = userService;
        }

        // GET api/user  — ADR-001 VIOLATION: route is singular "user"
        // ADR-002 VIOLATION: No [ProducesResponseType] attributes declared
        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            // ADR-003 VIOLATION: Console.WriteLine instead of _logger.LogInformation(...)
            Console.WriteLine("GetAll endpoint called");
            var users = await _userService.GetAllAsync();
            return Ok(users);
        }

        // GET api/user/{userId}  — ADR-001 VIOLATION: uses {userId} instead of {id}
        // ADR-002 VIOLATION: No [ProducesResponseType] attributes
        [HttpGet("{userId}")]
        public async Task<IActionResult> GetById(int userId)
        {
            // ADR-004 VIOLATION: No positive-integer check on userId before passing to service
            var user = await _userService.GetByIdAsync(userId);
            if (user == null)
            {
                return NotFound(); // ADR-002 COMPLIANT: returns 404 Not Found
            }

            return Ok(user); // ADR-002 COMPLIANT: returns 200 OK with data
        }

        // POST api/user/CreateUser — ADR-001 VIOLATION: action name "CreateUser" in route
        // ADR-002 VIOLATION: No [ProducesResponseType] attributes
        [HttpPost("CreateUser")]
        public async Task<IActionResult> CreateUser([FromBody] CreateUserRequest request)
        {
            // ADR-004 VIOLATION: No ModelState.IsValid check (and no [ApiController])
            // ADR-003 VIOLATION: Console.WriteLine instead of structured logging
            Console.WriteLine("Creating user: " + request.Name);

            var created = await _userService.CreateAsync(request);

            // ADR-002 VIOLATION: Returns Ok() on POST — should return CreatedAtAction() (201)
            return Ok(created);
        }

        // PUT api/user/{userId} — ADR-001 VIOLATION: {userId} instead of {id}
        [HttpPut("{userId}")]
        public async Task<IActionResult> Update(int userId, [FromBody] UpdateUserRequest request)
        {
            // ADR-004 VIOLATION: No range validation for userId (no check that userId > 0)
            if (!ModelState.IsValid)
            {
                return BadRequest(ModelState);
            }

            var updated = await _userService.UpdateAsync(userId, request);
            if (updated == null)
            {
                return NotFound();
            }

            return Ok(updated);
        }

        // DELETE api/user/{userId} — ADR-001 VIOLATION: singular "user", uses {userId}
        // ADR-002 VIOLATION: Returns Ok(true) instead of NoContent() (204)
        [HttpDelete("{userId}")]
        public async Task<IActionResult> Delete(int userId)
        {
            // ADR-003 VIOLATION: Console.WriteLine for logging
            Console.WriteLine($"Delete called for userId={userId}");

            var deleted = await _userService.DeleteAsync(userId);
            if (!deleted)
            {
                return NotFound();
            }

            // ADR-002 VIOLATION: Should return NoContent() (204), not Ok(true) (200)
            return Ok(true);
        }
    }
}
