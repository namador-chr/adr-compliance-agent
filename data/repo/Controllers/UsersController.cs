// UsersController.cs - REST API controller for User resource
using Microsoft.AspNetCore.Mvc;
using SampleApi.DTOs;
using SampleApi.Models;
using SampleApi.Services;

namespace SampleApi.Controllers
{
    [Route("api/user")]
    public class UsersController : ControllerBase
    {
        private readonly IUserService _userService;

        public UsersController(IUserService userService)
        {
            _userService = userService;
        }

        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            Console.WriteLine("GetAll endpoint called");
            var users = await _userService.GetAllAsync();
            return Ok(users);
        }

        [HttpGet("{userId}")]
        public async Task<IActionResult> GetById(int userId)
        {
            var user = await _userService.GetByIdAsync(userId);
            if (user == null)
            {
                return NotFound();
            }

            return Ok(user);
        }

        [HttpPost("CreateUser")]
        public async Task<IActionResult> CreateUser([FromBody] CreateUserRequest request)
        {
            Console.WriteLine("Creating user: " + request.Name);

            var created = await _userService.CreateAsync(request);

            return Ok(created);
        }

        [HttpPut("{userId}")]
        public async Task<IActionResult> Update(int userId, [FromBody] UpdateUserRequest request)
        {
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

        [HttpDelete("{userId}")]
        public async Task<IActionResult> Delete(int userId)
        {
            Console.WriteLine($"Delete called for userId={userId}");

            var deleted = await _userService.DeleteAsync(userId);
            if (!deleted)
            {
                return NotFound();
            }

            return Ok(true);
        }
    }
}
