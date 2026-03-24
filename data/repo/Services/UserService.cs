// UserService.cs - Business logic for user operations
// ADR-003 VIOLATION: Uses Console.WriteLine instead of ILogger<UserService>
// ADR-003 VIOLATION: No ILogger injected — the class does not use structured logging
// ADR-005 VIOLATION: Directly instantiates data access (in-memory dict simulates DB) — 
//                    real violation would be calling DbContext here instead of a repository
using SampleApi.Models;
using SampleApi.DTOs;

namespace SampleApi.Services
{
    /// <summary>
    /// Handles business logic for user management.
    ///
    /// ADR VIOLATIONS IN THIS FILE:
    ///   - ADR-003: Uses Console.WriteLine for logging (should use ILogger)
    ///   - ADR-003: Log messages use string interpolation instead of structured templates
    ///   - ADR-005: No repository abstraction — data access lives directly in the service
    /// </summary>
    public class UserService : IUserService
    {
        // Simulated in-memory store (represents direct data access in the service — ADR-005 violation)
        private static readonly Dictionary<int, User> _store = new()
        {
            [1] = new User { Id = 1, Name = "Alice Smith", Email = "alice@example.com", Role = "Admin", CreatedAt = DateTime.UtcNow.AddDays(-10) },
            [2] = new User { Id = 2, Name = "Bob Jones", Email = "bob@example.com", Role = "User", CreatedAt = DateTime.UtcNow.AddDays(-5) },
        };

        private static int _nextId = 3;

        // ADR-005 VIOLATION: No ILogger injected via constructor — no ILogger<UserService> field
        // ADR-003 VIOLATION: No structured logging at all; Console.WriteLine used instead
        public UserService()
        {
            // ADR-003 VIOLATION: Console.WriteLine used for logging
            Console.WriteLine("UserService initialized.");
        }

        public Task<IEnumerable<User>> GetAllAsync()
        {
            // ADR-003 VIOLATION: Console.WriteLine instead of _logger.LogInformation(...)
            Console.WriteLine("GetAllAsync called.");
            return Task.FromResult(_store.Values.AsEnumerable());
        }

        public Task<User?> GetByIdAsync(int id)
        {
            // ADR-003 VIOLATION: String interpolation in place of structured log template
            Console.WriteLine($"GetByIdAsync called with id={id}");
            _store.TryGetValue(id, out var user);
            return Task.FromResult(user);
        }

        public Task<User> CreateAsync(CreateUserRequest request)
        {
            // ADR-003 VIOLATION: Console.WriteLine instead of ILogger
            Console.WriteLine("CreateAsync: creating user " + request.Name);

            var user = new User
            {
                Id = _nextId++,
                Name = request.Name,
                Email = request.Email,
                Role = request.Role ?? "User",
                CreatedAt = DateTime.UtcNow
            };

            _store[user.Id] = user;
            return Task.FromResult(user);
        }

        public Task<User?> UpdateAsync(int id, UpdateUserRequest request)
        {
            if (!_store.TryGetValue(id, out var user))
            {
                // ADR-003 VIOLATION: Console.WriteLine should be _logger.LogWarning(...)
                Console.WriteLine("UpdateAsync: user not found, id=" + id);
                return Task.FromResult<User?>(null);
            }

            user.Name = request.Name;
            user.Email = request.Email;
            user.Role = request.Role;

            return Task.FromResult<User?>(user);
        }

        public Task<bool> DeleteAsync(int id)
        {
            var removed = _store.Remove(id);
            // ADR-003 VIOLATION: Console.WriteLine for logging
            Console.WriteLine($"DeleteAsync: removed={removed}, id={id}");
            return Task.FromResult(removed);
        }
    }
}
