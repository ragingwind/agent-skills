# AI Integration Rule

## Applicability

Use this rule when the project integrates AI services (OpenAI, Anthropic, Google AI, etc.).

## SDK Requirements

- **MUST** use official SDKs when available
- **MUST** use latest stable version
- **OpenAI:** openai ^4.75+
- **Anthropic:** @anthropic-ai/sdk ^0.32+
- **Google AI:** @google/generative-ai latest
- **Vercel AI SDK:** ai ^6.0+ (for unified AI interface)
- **SHOULD** pin SDK versions in production

## Framework Selection

### Vercel AI SDK

- **SHOULD** use Vercel AI SDK for multi-provider support
- **MUST** use ai ^4.0+ for latest features
- **Advantages:** Provider-agnostic, streaming support, React hooks, edge runtime compatible
- **Use Cases:** Applications requiring multiple AI providers, React applications, edge deployments

### Direct Provider SDKs

- **MAY** use direct provider SDKs for provider-specific features
- **Use Cases:** Single provider, advanced features not in Vercel AI SDK, non-web applications

### Decision Criteria

- **Multi-provider support needed** → Vercel AI SDK
- **React/Next.js application** → Vercel AI SDK
- **Edge runtime deployment** → Vercel AI SDK
- **Provider-specific features** → Direct SDK
- **iOS/macOS native apps** → Direct SDK

## API Communication

### Modern Async Pattern

- **MUST** use async/await for all AI API calls
- **MUST** handle asynchronous operations properly
- **SHOULD** implement timeout protection
- **MUST** handle streaming responses if applicable
- **SHOULD** use connection pooling for high-volume requests

### Streaming Responses

#### General Requirements

- **SHOULD** implement streaming for long-form content
- **MUST** handle stream errors gracefully
- **MUST** provide progress feedback to users
- **SHOULD** implement stream cancellation
- **MUST** handle partial responses on stream interruption

#### Vercel AI SDK Streaming

- **SHOULD** use `streamText` for text generation
- **SHOULD** use `streamObject` for structured outputs
- **MUST** implement proper stream cleanup
- **SHOULD** use React hooks (`useChat`, `useCompletion`) for client-side streaming

## Error Handling

### Requirements

- **MUST** handle rate limits with exponential backoff
- **MUST** handle network errors gracefully
- **MUST** implement timeout protection (30-60 seconds recommended)
- **SHOULD** implement request retry logic (3-5 retries)
- **MUST** distinguish between client and server errors
- **SHOULD** log all API errors with context

### Vercel AI SDK Error Handling

- **MUST** handle `APICallError` for API failures
- **MUST** handle `InvalidResponseDataError` for malformed responses
- **SHOULD** use error boundaries in React applications
- **MUST** implement fallback behavior on errors

### Rate Limiting

- **MUST** respect API rate limits
- **SHOULD** implement client-side rate limiting
- **MUST** handle 429 (Too Many Requests) errors
- **SHOULD** implement queue system for high-volume requests
- **MUST** provide user feedback when rate limited

### Retry Strategy

- **MUST** use exponential backoff for retries
- **SHOULD** add jitter to prevent thundering herd
- **MUST** set maximum retry attempts
- **SHOULD** retry only on transient errors (network, 5xx, rate limits)
- **MUST NOT** retry on client errors (4xx except 429)

## Prompt Engineering

### Standards

- **MUST** use system prompts effectively
- **SHOULD** implement prompt templates
- **MUST** validate prompt length against model limits
- **SHOULD** implement prompt caching where supported
- **MUST** version prompts for reproducibility
- **SHOULD** test prompts with various inputs

### Vercel AI SDK Prompts

- **SHOULD** use prompt template functions
- **MUST** use type-safe message formats
- **SHOULD** leverage multi-modal support when needed
- **MAY** use tool/function calling for structured interactions

### Prompt Management

- **SHOULD** externalize prompts from code
- **MUST** sanitize user input in prompts
- **SHOULD** implement prompt injection prevention
- **MUST** document prompt purpose and expected behavior
- **SHOULD** track prompt performance metrics

## Token Management

### Requirements

- **MUST** track token usage
- **MUST** implement token limits per request
- **SHOULD** estimate costs before requests
- **SHOULD** implement token counting
- **MUST** handle token limit errors gracefully
- **SHOULD** optimize prompts to reduce token usage

### Vercel AI SDK Token Tracking

- **SHOULD** access usage data from response objects
- **MUST** log token consumption for monitoring
- **SHOULD** implement middleware for token tracking
- **MAY** use `onFinish` callback for usage logging

### Cost Management

- **SHOULD** implement usage quotas per user/tenant
- **MUST** monitor and alert on cost thresholds
- **SHOULD** cache responses when appropriate
- **MUST** log token usage for billing/analysis
- **SHOULD** implement cost estimation endpoints

## Data Privacy

### Requirements

- **MUST** review AI provider's data retention policy
- **MUST NOT** send sensitive data without user consent
- **SHOULD** implement data sanitization before API calls
- **MUST** comply with relevant regulations (GDPR, CCPA, etc.)
- **MUST** document what data is sent to AI services
- **SHOULD** implement opt-out mechanisms

### Security

- **MUST** store API keys securely (environment variables, secrets manager)
- **MUST NOT** commit API keys to version control
- **MUST** rotate API keys regularly
- **SHOULD** use separate keys for dev/staging/production
- **MUST** implement key rotation procedures
- **SHOULD** use edge runtime environment variables for Vercel deployments

## Caching

### Requirements

- **SHOULD** cache AI responses for identical requests
- **MUST** implement cache invalidation strategy
- **SHOULD** use prompt caching features (Anthropic, etc.)
- **MUST** respect cache-control headers
- **SHOULD** implement cache warming for common queries

### Cache Strategy

- **SHOULD** cache by prompt hash
- **MUST** set appropriate TTL values
- **SHOULD** implement cache size limits
- **MUST** handle cache misses gracefully
- **SHOULD** monitor cache hit rates

### Vercel AI SDK Caching

- **MAY** use Vercel Data Cache for edge deployments
- **SHOULD** implement custom caching middleware
- **MUST** consider streaming responses in cache strategy

## Testing

### Requirements

- **MUST** mock AI API calls in tests
- **SHOULD** test error handling paths
- **SHOULD** test with sample responses
- **MUST** test timeout scenarios
- **SHOULD** test rate limit handling
- **MUST** test retry logic

### Test Strategy

- **SHOULD** use fixture responses for deterministic tests
- **MUST** test prompt validation
- **SHOULD** test token limit scenarios
- **MUST** test network failure scenarios
- **SHOULD** implement integration tests with real API (sparingly)

### Vercel AI SDK Testing

- **SHOULD** mock provider responses using test utilities
- **MUST** test streaming behavior
- **SHOULD** test React hooks with React Testing Library
- **MUST** test server actions in Next.js applications

## Monitoring & Observability

### Requirements

- **MUST** monitor API response times
- **MUST** track success/failure rates
- **SHOULD** monitor token usage trends
- **SHOULD** alert on error rate spikes
- **MUST** log request/response metadata (not full content)
- **SHOULD** track model version usage

### Metrics to Track

- **Request count and rate**
- **Response times (p50, p95, p99)**
- **Error rates by type**
- **Token usage (input/output)**
- **Cost per request**
- **Cache hit rates**
- **Stream completion rates**

### Vercel AI SDK Monitoring

- **SHOULD** use telemetry callbacks for observability
- **MAY** integrate with Vercel Analytics
- **SHOULD** track provider distribution in multi-provider setups
- **MUST** monitor edge function performance

## Model Selection

### Requirements

- **MUST** document which models are used for which tasks
- **SHOULD** use appropriate model for task complexity
- **MUST** specify model versions in production
- **SHOULD** test new model versions before deploying
- **MUST** handle model deprecation gracefully

### Model Configuration

- **MUST** configure appropriate max_tokens (maxTokens in Vercel AI SDK)
- **SHOULD** set temperature based on use case
- **SHOULD** configure top_p or top_k if needed
- **MUST** document model parameters
- **SHOULD** A/B test model configurations

### Vercel AI SDK Model Switching

- **SHOULD** use provider-agnostic model configuration
- **MAY** implement runtime model selection
- **SHOULD** abstract provider details from application logic
- **MUST** handle provider-specific limitations

## Tool/Function Calling

### Requirements (if applicable)

- **SHOULD** use structured outputs for data extraction
- **MUST** validate function call parameters
- **MUST** implement proper error handling for tool execution
- **SHOULD** document available tools/functions

### Vercel AI SDK Tools

- **SHOULD** use `tools` parameter for function definitions
- **MUST** implement tool execution handlers
- **SHOULD** use Zod schemas for tool parameter validation
- **MUST** handle tool call errors gracefully

## Edge Runtime Considerations

### Vercel AI SDK on Edge

- **SHOULD** use edge-compatible runtime for low latency
- **MUST** ensure all dependencies are edge-compatible
- **SHOULD** implement streaming for better UX
- **MUST** handle edge runtime limitations (timeouts, memory)
- **SHOULD** use lightweight models for edge deployment

## Related Rules

- [Backend](./backend.md)
- [Frontend Web](./frontend-web.md)
- [Design Patterns](./design-patterns.md)
- [Writing Guidelines](./writing-guidelines.md)
- [Technology Versions](./technology-versions.md)
- [Build and Deployment](./build-deployment.md)
