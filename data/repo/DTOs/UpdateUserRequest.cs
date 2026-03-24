// UpdateUserRequest.cs - DTO for updating a user
using System.ComponentModel.DataAnnotations;

namespace SampleApi.DTOs
{
    /// <summary>
    /// Request model for updating an existing user.
    /// </summary>
    public class UpdateUserRequest
    {
        [Required(ErrorMessage = "Name is required.")]
        [MaxLength(100, ErrorMessage = "Name cannot exceed 100 characters.")]
        public string Name { get; set; }

        [Required(ErrorMessage = "Email is required.")]
        [EmailAddress(ErrorMessage = "Email must be a valid email address.")]
        [MaxLength(200, ErrorMessage = "Email cannot exceed 200 characters.")]
        public string Email { get; set; }

        [Required(ErrorMessage = "Role is required.")]
        [MaxLength(50, ErrorMessage = "Role cannot exceed 50 characters.")]
        public string Role { get; set; }
    }
}
