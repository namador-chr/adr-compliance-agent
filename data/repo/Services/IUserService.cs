// IUserService.cs - Service interface for user operations
namespace SampleApi.Services
{
    public interface IUserService
    {
        Task<IEnumerable<Models.User>> GetAllAsync();
        Task<Models.User?> GetByIdAsync(int id);
        Task<Models.User> CreateAsync(DTOs.CreateUserRequest request);
        Task<Models.User?> UpdateAsync(int id, DTOs.UpdateUserRequest request);
        Task<bool> DeleteAsync(int id);
    }
}
