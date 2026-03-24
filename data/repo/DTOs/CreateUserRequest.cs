// CreateUserRequest.cs - DTO for creating a user
// ADR-004 VIOLATION: Missing [Required] and [MaxLength] validation attributes on properties.
// ADR-004 VIOLATION: No Data Annotation validation — all properties are bare with no constraints.
using System.ComponentModel.DataAnnotations;

namespace SampleApi.DTOs
{
    /// <summary>
    /// Request model for creating a new user.
    /// NOTE: This is intentionally missing validation attributes to demonstrate ADR-004 violations.
    /// </summary>
    public class CreateUserRequest
    {
        // ADR-004 VIOLATION: Missing [Required] attribute
        // ADR-004 VIOLATION: Missing [MaxLength] or [StringLength] attribute
        public string Name { get; set; }

        // ADR-004 VIOLATION: Missing [Required] attribute
        // ADR-004 VIOLATION: Missing [EmailAddress] attribute
        // ADR-004 VIOLATION: Missing [MaxLength] attribute
        public string Email { get; set; }

        // ADR-004 VIOLATION: Missing [Required] attribute
        public string Role { get; set; }
    }
}
