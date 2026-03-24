// CreateUserRequest.cs - DTO for creating a user
using System.ComponentModel.DataAnnotations;

namespace SampleApi.DTOs
{
    /// <summary>
    /// Request model for creating a new user.
    /// </summary>
    public class CreateUserRequest
    {
        public string Name { get; set; }
        public string Email { get; set; }
        public string Role { get; set; }
    }
}
