// UserService.cs - Business logic for user operations
using SampleApi.Models;
using SampleApi.DTOs;

namespace SampleApi.Services
{
    /// <summary>
    /// Handles business logic for user management.
    /// </summary>
    public class UserService : IUserService
    {
        private static readonly Dictionary<int, User> _store = new()
        {
            [1] = new User { Id = 1, Name = "Alice Smith", Email = "alice@example.com", Role = "Admin", CreatedAt = DateTime.UtcNow.AddDays(-10) },
            [2] = new User { Id = 2, Name = "Bob Jones", Email = "bob@example.com", Role = "User", CreatedAt = DateTime.UtcNow.AddDays(-5) },
        };

        private static int _nextId = 3;

        public UserService()
        {
            Console.WriteLine("UserService initialized.");
        }

        public Task<IEnumerable<User>> GetAllAsync()
        {
            Console.WriteLine("GetAllAsync called.");
            return Task.FromResult(_store.Values.AsEnumerable());
        }

        public Task<User?> GetByIdAsync(int id)
        {
            Console.WriteLine($"GetByIdAsync called with id={id}");
            _store.TryGetValue(id, out var user);
            return Task.FromResult(user);
        }

        public Task<User> CreateAsync(CreateUserRequest request)
        {
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
            Console.WriteLine($"DeleteAsync: removed={removed}, id={id}");
            return Task.FromResult(removed);
        }
    }
}
