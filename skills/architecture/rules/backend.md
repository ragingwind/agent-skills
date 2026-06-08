# Backend Architecture Rule

## Applicability

Use this rule when the project includes server-side components.

## Technology Requirements

### Runtime & Language

- **Node.js:** 22+ LTS with native TypeScript support
- **Python:** 3.12+ with type hints
- **Rust:** Latest stable with async runtime
- **Go:** 1.23+
- **MUST** use latest stable version of chosen runtime

### Framework Selection

- **Node.js:** Hono, Fastify 5+, or Next.js API routes
- **Python:** FastAPI 0.115+
- **Rust:** Axum or Actix-web
- **Go:** Gin or Echo
- **MUST** use latest stable version

## API Design

### RESTful API

- **MUST** follow REST principles
- **MUST** use appropriate HTTP methods (GET, POST, PUT, PATCH, DELETE)
- **MUST** use proper status codes
- **MUST** implement consistent response format
- **SHOULD** use JSON for request/response bodies
- **MUST** version APIs (e.g., /api/v1/)

### GraphQL (if applicable)

- **MUST** use latest version of Apollo Server or similar
- **MUST** implement proper error handling
- **SHOULD** use DataLoader for batching
- **MUST** implement query complexity limits
- **SHOULD** implement pagination

### API Documentation

- **MUST** document with OpenAPI/Swagger (REST) or GraphQL schema
- **MUST** include example requests and responses
- **SHOULD** keep documentation in sync with implementation
- **SHOULD** generate API documentation automatically

## Authentication & Authorization

### Modern Approaches

- **MUST** use OAuth 2.0 / OpenID Connect for user auth
- **SHOULD** use JWT with short expiration (15-60 minutes)
- **MUST** implement refresh token rotation
- **MUST** use bcrypt or argon2 for password hashing
- **MUST NOT** use MD5 or SHA1 for passwords

### Security Requirements

- **MUST** implement rate limiting
- **MUST** protect against CSRF
- **MUST** implement proper CORS policies
- **MUST** validate and sanitize all inputs
- **SHOULD** implement API key rotation
- **MUST** use HTTPS only in production

## Database

### Options

- **PostgreSQL 16+** (recommended for relational)
- **MongoDB 8+** (for document store)
- **Redis 7+** (for caching)
- **MUST** choose based on data structure and query patterns

### ORM/Query Builder

- **TypeScript:** Drizzle ORM or Prisma 6+
- **Python:** SQLAlchemy 2.0+ with async support
- **MUST** use migrations for schema changes
- **MUST** use connection pooling
- **MUST** implement proper transaction handling

### Database Best Practices

- **MUST** use prepared statements to prevent SQL injection
- **MUST** implement database indexes appropriately
- **SHOULD** use database constraints for data integrity
- **MUST** implement backup and recovery procedures
- **SHOULD** monitor database performance

## Error Handling

### Requirements

- **MUST** implement global error handler
- **MUST** log errors with context (timestamp, user, request ID)
- **MUST** return appropriate HTTP status codes
- **SHOULD** use error tracking service (Sentry, etc.)
- **MUST** distinguish between operational and programmer errors
- **MUST NOT** expose stack traces or internal details to clients

### Error Response Format

- **MUST** use consistent error response structure
- **SHOULD** include error codes for client handling
- **MUST** provide user-friendly error messages
- **SHOULD** include request ID for debugging

## Validation

### Requirements

- **MUST** validate all input at API boundary
- **MUST** use schema validation (Zod, Joi, Pydantic, etc.)
- **MUST** sanitize user input to prevent XSS
- **MUST** validate data types, formats, and ranges
- **SHOULD** return detailed validation errors

## Logging

### Requirements

- **MUST** use structured logging (JSON format)
- **MUST** include request IDs for tracing
- **SHOULD** use appropriate logging levels (DEBUG, INFO, WARN, ERROR)
- **MUST** avoid logging sensitive data (passwords, tokens, PII)
- **Recommended Libraries:** Pino (Node.js), structlog (Python)

### What to Log

- **MUST** log all errors with stack traces
- **SHOULD** log authentication attempts
- **SHOULD** log significant business events
- **MUST** log API request/response (in development)
- **SHOULD** implement log rotation

## Performance

### Requirements

- **MUST** implement caching where appropriate (Redis, in-memory)
- **SHOULD** use database query optimization
- **MUST** implement pagination for large datasets
- **SHOULD** use async/await for I/O operations
- **SHOULD** implement request timeouts
- **MUST** monitor API response times

## Testing

### Requirements

- **MUST** write unit tests for business logic
- **SHOULD** write integration tests for API endpoints
- **SHOULD** test error handling scenarios
- **MUST** mock external dependencies
- **SHOULD** aim for >80% code coverage on critical paths
- **MUST** test authentication and authorization

## File Structure

### Project Organization

- **MUST** analyze and document the current project's directory structure
- **MUST** maintain consistency with existing organization patterns
- **MUST** respect existing naming conventions
- **SHOULD** refer to current project implementation for structure reference

### Organization Principles

- **MUST** separate concerns (routes, services, models, middleware)
- **SHOULD** organize by feature for large applications
- **SHOULD** organize by type for small to medium applications
- **MUST** keep related files together
- **MUST** separate business logic from framework code

### Common Patterns

- **Routes/Controllers:** Handle HTTP requests and responses
- **Services:** Contain business logic
- **Models:** Define data structures
- **Middleware:** Handle cross-cutting concerns
- **Database:** Schemas, migrations, connections
- **Utils/Helpers:** Shared utilities

## Monitoring & Observability

### Requirements

- **SHOULD** implement health check endpoints
- **SHOULD** implement metrics collection (Prometheus, etc.)
- **SHOULD** monitor error rates and response times
- **MUST** implement alerting for critical failures
- **SHOULD** use distributed tracing for microservices

## Related Rules

- [AI Integration](./ai-integration.md)
- [Design Patterns](./design-patterns.md)
- [Build and Deployment](./build-deployment.md)
- [Technology Versions](./technology-versions.md)
- [Project Analysis](./project-analysis.md)
