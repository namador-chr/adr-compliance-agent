// Program.cs - ASP.NET Core entry point and service registration
// This file is largely ADR-compliant.

var builder = WebApplication.CreateBuilder(args);

// Register services
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// ADR-005 COMPLIANT: Registers IUserService mapped to UserService (interface → concrete)
builder.Services.AddScoped<SampleApi.Services.IUserService, SampleApi.Services.UserService>();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();
app.UseAuthorization();
app.MapControllers();

app.Run();
