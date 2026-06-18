# Design Patterns and Principles Rule

## Overview

This document defines design patterns, architectural principles, and code quality standards that ensure maintainable, scalable, and clean code across all project components.

## SOLID Principles

### Single Responsibility Principle (SRP)

- **MUST** ensure each class/component/function has one reason to change
- **MUST** separate data fetching from UI rendering
- **MUST** separate business logic from presentation logic
- **MUST** keep functions focused on a single task
- **SHOULD** refactor when a module has multiple responsibilities

#### Application

- **Components:** Only handle presentation and user interaction
- **Services:** Only handle business logic or external communication
- **Models:** Only represent data structures
- **ViewModels:** Only manage view state and coordinate between view and model

### Open/Closed Principle (OCP)

- **MUST** design modules open for extension, closed for modification
- **MUST** use composition and dependency injection
- **SHOULD** use strategy pattern for varying behavior
- **SHOULD** use plugin architectures when appropriate
- **AVOID:** Modifying existing code to add new features

#### Application

- **Use interfaces/protocols** to define contracts
- **Use configuration** instead of hardcoded values
- **Use dependency injection** to swap implementations
- **Use composition** to add new behaviors

### Liskov Substitution Principle (LSP)

- **MUST** ensure derived types are substitutable for base types
- **MUST** honor contracts defined by base types
- **MUST NOT** strengthen preconditions in derived types
- **MUST NOT** weaken postconditions in derived types
- **SHOULD** prefer composition over inheritance to avoid LSP violations

### Interface Segregation Principle (ISP)

- **MUST** create focused, specific interfaces
- **MUST** split large interfaces into smaller, cohesive ones
- **AVOID:** Large, monolithic interfaces
- **AVOID:** Forcing clients to depend on methods they don't use
- **SHOULD** design interfaces from the client's perspective

#### Application

- **Many specific interfaces** > One general interface
- **Client-specific interfaces** > All-encompassing interfaces
- **Role-based interfaces** for different use cases

### Dependency Inversion Principle (DIP)

- **MUST** depend on abstractions, not concretions
- **MUST** use dependency injection
- **MUST** define interfaces owned by high-level modules
- **SHOULD** inject dependencies through constructors
- **AVOID:** Direct instantiation of dependencies

#### Application

- **High-level modules** define interfaces
- **Low-level modules** implement interfaces
- **Dependencies** injected from outside
- **Testability** improved through mocking interfaces

## API Design Principles

### RESTful API Design

- **MUST** use appropriate HTTP methods (GET, POST, PUT, PATCH, DELETE)
- **MUST** use proper HTTP status codes
- **MUST** use nouns for resource names, not verbs
- **MUST** use plural nouns for collections
- **MUST** implement consistent URL structure
- **MUST** version APIs (e.g., /api/v1/)
- **SHOULD** use query parameters for filtering, sorting, pagination
- **SHOULD** implement HATEOAS for discoverability

### GraphQL API Design

- **MUST** design schema with clear type definitions
- **MUST** implement proper error handling
- **SHOULD** use DataLoader for N+1 query prevention
- **MUST** implement query complexity limits
- **SHOULD** implement pagination (cursor-based preferred)
- **MUST** document schema with descriptions

### API Consistency

- **MUST** use consistent naming conventions
- **MUST** use consistent response formats
- **MUST** use consistent error formats
- **MUST** use consistent date/time formats (ISO 8601)
- **SHOULD** use consistent pagination patterns

### API Versioning

- **MUST** version public APIs
- **SHOULD** use URL versioning for major versions
- **MAY** use header versioning for minor versions
- **MUST** maintain backward compatibility within major versions
- **SHOULD** deprecate old versions with advance notice

## Interface-Based Module Design

### Interface Definition

- **MUST** define interfaces for all public APIs
- **MUST** keep interfaces small and focused (ISP)
- **SHOULD** define interfaces in terms of behavior, not implementation
- **MUST** document interface contracts clearly
- **SHOULD** use type systems to enforce interfaces (TypeScript, Swift protocols)

### Module Boundaries

- **MUST** define clear module boundaries
- **MUST** communicate between modules through interfaces only
- **MUST** hide implementation details within modules
- **SHOULD** minimize coupling between modules
- **MUST** maximize cohesion within modules

### Dependency Management

- **MUST** depend on interfaces, not implementations
- **MUST** inject dependencies explicitly
- **SHOULD** use dependency injection containers for complex apps
- **MUST** avoid circular dependencies
- **SHOULD** use dependency inversion at module boundaries

### Interface Contracts

- **MUST** document preconditions and postconditions
- **MUST** document side effects
- **MUST** specify error conditions
- **SHOULD** use design by contract principles
- **MUST** validate inputs at boundaries

## Maintainability Principles

### Code Readability

- **MUST** write self-documenting code
- **MUST** use meaningful, descriptive names
- **SHOULD** keep functions under 50 lines
- **SHOULD** keep files under 500 lines
- **MUST** use consistent formatting
- **SHOULD** add comments only when code cannot be self-explanatory

### Code Simplicity

- **MUST** favor simplicity over cleverness
- **SHOULD** use the simplest solution that works
- **MUST** avoid premature optimization
- **SHOULD** refactor complex code into simpler pieces
- **MUST** follow YAGNI (You Aren't Gonna Need It)

### DRY (Don't Repeat Yourself)

- **MUST** eliminate code duplication
- **SHOULD** extract common logic into reusable functions
- **SHOULD** use composition to share behavior
- **MUST** balance DRY with readability
- **AVOID:** Premature abstraction

### Testability

- **MUST** write testable code
- **MUST** use dependency injection for external dependencies
- **SHOULD** keep functions pure when possible
- **MUST** separate logic from I/O
- **SHOULD** aim for >80% test coverage on business logic

### Documentation

- **MUST** document public APIs
- **SHOULD** document architectural decisions (ADRs)
- **MUST** keep documentation in sync with code
- **SHOULD** use inline documentation for complex logic
- **MUST** document WHY, not just WHAT

## Clean Code Principles

### Naming Conventions

- **MUST** use intention-revealing names
- **MUST** use pronounceable names
- **MUST** use searchable names
- **MUST** avoid mental mapping
- **MUST** use consistent naming patterns
- **AVOID:** Single-letter variables (except loop counters)
- **AVOID:** Encodings in names (Hungarian notation)

### Function Design

- **MUST** keep functions small (one thing)
- **MUST** use descriptive function names
- **SHOULD** limit function parameters (ideally ≤3)
- **MUST** avoid side effects in pure functions
- **SHOULD** use objects for multiple parameters
- **MUST** separate commands from queries

### Error Handling

- **MUST** use exceptions/errors, not error codes
- **MUST** provide context with errors
- **MUST** define error handling at boundaries
- **SHOULD** use custom error types
- **MUST** clean up resources in error cases
- **AVOID:** Returning null (use Optional/Maybe patterns)

### Code Smells to Avoid

#### Bloaters

- **Long Method** - Functions over 50 lines
- **Large Class** - Classes with too many responsibilities
- **Primitive Obsession** - Using primitives instead of small objects
- **Long Parameter List** - More than 3-4 parameters
- **Data Clumps** - Same group of parameters appearing together

#### Object-Orientation Abusers

- **Switch Statements** - Consider polymorphism
- **Temporary Field** - Fields only used in certain circumstances
- **Refused Bequest** - Subclass doesn't use inherited methods
- **Alternative Classes with Different Interfaces** - Similar classes with different interfaces

#### Change Preventers

- **Divergent Change** - One class changed for many different reasons
- **Shotgun Surgery** - One change requires many small changes elsewhere
- **Parallel Inheritance Hierarchies** - Creating subclass requires creating another

#### Dispensables

- **Comments** - Excessive comments hiding bad code
- **Duplicate Code** - Same code structure in multiple places
- **Dead Code** - Unused code
- **Speculative Generality** - Unused abstractions

#### Couplers

- **Feature Envy** - Method uses another class more than its own
- **Inappropriate Intimacy** - Classes too dependent on each other's internals
- **Message Chains** - Long chains of method calls (Law of Demeter violation)
- **Middle Man** - Class delegates most work to another class

### Refactoring Guidelines

- **MUST** refactor when code smells are detected
- **MUST** have tests before refactoring
- **SHOULD** refactor in small, incremental steps
- **MUST** keep tests passing during refactoring
- **SHOULD** commit after each successful refactoring step

## Component UI Design

### Component Principles

- **MUST** follow single responsibility principle
- **MUST** keep components under 200 lines
- **SHOULD** create small, focused components
- **MUST** separate presentational from container components
- **SHOULD** make components reusable
- **MUST** use composition over inheritance

### Component Hierarchy

- **MUST** establish clear parent-child relationships
- **SHOULD** keep component trees shallow
- **MUST** lift state to appropriate level
- **SHOULD** pass data down, events up
- **MUST** avoid prop drilling (use context/injection when needed)

### Component Types

#### Presentational Components

- **MUST** focus only on UI rendering
- **MUST** receive data via props
- **MUST NOT** contain business logic
- **SHOULD** be stateless when possible
- **MUST** be highly reusable

#### Container Components

- **MUST** handle data fetching and state management
- **MUST** pass data to presentational components
- **SHOULD** contain minimal UI markup
- **MAY** connect to state management
- **SHOULD** coordinate multiple presentational components

#### Layout Components

- **MUST** define page/section structure
- **SHOULD** be agnostic of content
- **MUST** handle responsive behavior
- **SHOULD** use composition for flexibility

### Component API Design

- **MUST** design clear, minimal prop interfaces
- **MUST** provide sensible defaults
- **SHOULD** use TypeScript/PropTypes for type safety
- **MUST** document public component APIs
- **SHOULD** use composition slots/children for flexibility
- **MUST** validate props at runtime in development

### State Management in Components

- **MUST** keep state as local as possible
- **SHOULD** lift state only when necessary
- **MUST** use appropriate state management (local, context, global)
- **SHOULD** derive state instead of duplicating
- **MUST** avoid unnecessary re-renders

### Component Composition Patterns

- **SHOULD** use children/slot props for flexibility
- **SHOULD** use render props for behavior sharing
- **SHOULD** use higher-order components/decorators sparingly
- **MUST** use hooks/composables for logic reuse (React/Vue)
- **SHOULD** use compound components for related UI elements

### Component Naming

- **MUST** use PascalCase for component names
- **MUST** use descriptive, intention-revealing names
- **SHOULD** prefix with feature/domain for clarity
- **SHOULD** suffix with type when helpful (e.g., Button, Modal)
- **MUST** maintain consistent naming patterns

### Accessibility in Components

- **MUST** provide semantic HTML
- **MUST** support keyboard navigation
- **MUST** provide ARIA labels where needed
- **MUST** ensure sufficient color contrast
- **MUST** test with screen readers

### Performance Considerations

- **SHOULD** memoize expensive computations
- **SHOULD** implement virtual scrolling for large lists
- **MUST** lazy load heavy components
- **SHOULD** optimize re-render behavior
- **MUST** avoid inline function definitions in render

## Common Design Patterns

### Repository Pattern

- **Purpose:** Abstract data access logic
- **MUST** define interface for data operations
- **MUST** hide data source details
- **SHOULD** return domain models, not DTOs
- **Use Case:** Database, API, cache abstraction

### Factory Pattern

- **Purpose:** Encapsulate object creation
- **MUST** return interface types
- **SHOULD** centralize creation logic
- **Use Case:** Complex object initialization, strategy selection

### Strategy Pattern

- **Purpose:** Encapsulate interchangeable algorithms
- **MUST** define common interface
- **MUST** allow runtime strategy selection
- **Use Case:** Payment methods, sorting algorithms, validation rules

### Observer Pattern

- **Purpose:** Notify dependents of state changes
- **SHOULD** use modern reactive libraries
- **MUST** handle unsubscription
- **Use Case:** Event systems, state management, pub-sub

### Dependency Injection Pattern

- **Purpose:** Invert control of dependencies
- **MUST** inject through constructor or setter
- **MUST** depend on interfaces
- **SHOULD** use DI containers for complex apps
- **Use Case:** Testing, modularity, configuration

### Adapter Pattern

- **Purpose:** Convert interface to another interface
- **MUST** maintain single responsibility
- **SHOULD** be transparent to clients
- **Use Case:** Third-party library integration, legacy code

### Facade Pattern

- **Purpose:** Simplify complex subsystem interfaces
- **MUST** provide simple, unified interface
- **SHOULD** hide subsystem complexity
- **Use Case:** Complex APIs, library wrappers

## Composition Over Inheritance

### Requirements

- **MUST** favor composition over class inheritance
- **SHOULD** use interfaces/protocols for contracts
- **SHOULD** use mixins/traits for behavior sharing
- **AVOID:** Deep inheritance hierarchies (>2-3 levels)
- **MUST** use inheritance only for "is-a" relationships

### Composition Techniques

- **Delegation:** Forward calls to composed object
- **Aggregation:** Contain objects that can exist independently
- **Composition:** Contain objects that cannot exist independently
- **Mixins/Traits:** Share behavior across unrelated types

## Async Patterns

### Requirements

- **MUST** use async/await over callbacks
- **MUST** handle errors in async code
- **SHOULD** use Promise.all for parallel operations
- **MUST** implement proper cancellation
- **SHOULD** avoid async in constructors

### Error Handling in Async

- **MUST** use try/catch with async/await
- **MUST** handle promise rejections
- **SHOULD** use Promise.allSettled when some failures acceptable
- **MUST** clean up resources on errors
- **SHOULD** implement timeout mechanisms

### Parallel vs Sequential

- **SHOULD** run independent operations in parallel
- **MUST** run dependent operations sequentially
- **SHOULD** use Promise.all for parallel execution
- **MUST** consider error handling strategy (fail-fast vs continue)

## Code Organization

### By Feature (Recommended for Large Apps)

- **MUST** group related functionality together
- **MUST** keep feature modules self-contained
- **SHOULD** minimize cross-feature dependencies
- **MUST** define clear module boundaries

### By Type (Acceptable for Small Apps)

- **MAY** group by technical type (models, views, controllers)
- **MUST** maintain clear separation of concerns
- **SHOULD** migrate to feature-based as app grows

### File Organization

- **MUST** keep related files together
- **SHOULD** co-locate tests with implementation
- **MUST** use consistent file naming
- **SHOULD** keep files focused and small (<500 lines)

## Related Rules

- [Frontend Web](./frontend-web.md) - Web component patterns
- [Frontend iOS](./frontend-ios.md) - iOS/Swift patterns
- [Frontend macOS](./frontend-macos.md) - macOS patterns
- [Backend](./backend.md) - Server-side patterns
- [Writing Guidelines](./writing-guidelines.md) - Documentation standards
