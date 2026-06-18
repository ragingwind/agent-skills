# Frontend iOS Architecture Rule

## Applicability

Use this rule when the project includes iOS application components.

## Technology Requirements

### Language & Platform

- **MUST** use Swift 6.0+
- **MUST** enable strict concurrency checking
- **MUST** target iOS 18.0+ minimum deployment
- **MUST** use Xcode 16+

### Framework

- **MUST** use SwiftUI as primary UI framework
- **MAY** use UIKit only for specific requirements not available in SwiftUI
- **MUST** use Observation framework (@Observable) over ObservableObject

## Architecture Pattern

### MVVM Implementation

- **MUST** separate View, ViewModel, and Model layers
- **MUST** use @Observable for ViewModels
- **MUST** keep Views under 200 lines
- **MUST** use @MainActor for ViewModels
- **MUST** implement proper separation of concerns
- **SHOULD** keep ViewModels testable and independent of SwiftUI

## State Management

### Local State

- **MUST** use @State for view-local state
- **MUST** use @Binding for child-to-parent communication
- **SHOULD** keep state as low in the view hierarchy as possible

### Shared State

- **MUST** use @Observable for shared ViewModels
- **SHOULD** use Environment for dependency injection
- **MAY** use @AppStorage for simple user preferences
- **SHOULD** implement proper state management patterns for complex state

### Data Persistence

- **MUST** use SwiftData for local persistence (iOS 17+)
- **MAY** use CoreData only if SwiftData is insufficient
- **MUST** use Keychain for sensitive data
- **SHOULD** use UserDefaults only for simple preferences

## Navigation

### Modern Navigation

- **MUST** use NavigationStack for navigation hierarchies
- **MUST** implement type-safe navigation with Hashable routes
- **SHOULD** use NavigationPath for complex navigation
- **MUST** support deep linking where applicable
- **SHOULD** handle navigation state restoration

## Networking

### Modern Async/Await

- **MUST** use async/await for all network calls
- **MUST** use URLSession with modern APIs
- **SHOULD** implement retry logic with exponential backoff
- **MUST** handle errors gracefully
- **SHOULD** implement proper timeout handling
- **MUST** use actors for thread-safe network services

## UI Components

### Design System

- **SHOULD** create reusable component library
- **MUST** follow Apple Human Interface Guidelines
- **SHOULD** use SF Symbols for icons
- **MUST** implement proper accessibility
- **SHOULD** create custom ViewModifiers for consistent styling

### Animations

- **SHOULD** use native SwiftUI animations
- **MUST** provide meaningful feedback for user actions
- **SHOULD** respect reduced motion preferences
- **MUST** ensure animations are performant

## File Structure

### Project Organization

- **MUST** analyze and document the current project's directory structure
- **MUST** maintain consistency with existing organization patterns
- **MUST** respect existing naming conventions for files and folders
- **SHOULD** refer to current project implementation for structure reference

### Organization Principles

- **MUST** separate concerns (Models, ViewModels, Views, Services, Resources)
- **SHOULD** organize by feature for large applications
- **SHOULD** organize by type for small to medium applications
- **MUST** keep related files together
- **MUST** use Xcode folder references (blue folders), not groups
- **MUST** ensure Xcode navigator matches filesystem structure

### File Naming Conventions

- **MUST** follow consistent naming patterns across the project
- **SHOULD** use descriptive, clear names
- **App Entry Point:** Match target name (e.g., YourAppNameApp.swift)
- **Views:** Descriptive names indicating purpose
- **ViewModels:** Corresponding to view names
- **Models:** Entity names conforming to Swift naming conventions
- **Services:** Purpose-based names with "Service" suffix
- **Extensions:** Type + purpose format

## Testing

### Requirements

- **MUST** write unit tests for ViewModels
- **SHOULD** use XCTest framework
- **SHOULD** implement UI tests for critical paths
- **MUST** test async operations properly
- **SHOULD** mock external dependencies in tests
- **SHOULD** aim for >80% code coverage on business logic

## Performance

### Requirements

- **MUST** profile with Instruments
- **SHOULD** optimize list rendering with LazyVStack/LazyHStack
- **MUST** implement pagination for large data sets
- **SHOULD** cache images appropriately
- **MUST** avoid unnecessary view re-renders
- **SHOULD** use task cancellation for async operations
- **MUST** handle memory warnings properly

## Accessibility

### Requirements

- **MUST** provide accessibility labels for all interactive elements
- **MUST** support VoiceOver
- **MUST** support Dynamic Type
- **SHOULD** test with accessibility features enabled
- **MUST** ensure sufficient color contrast
- **SHOULD** provide accessibility hints where needed

## Background Tasks

### Requirements

- **MUST** handle app lifecycle events properly
- **SHOULD** implement background refresh when appropriate
- **MUST** save user data before app termination
- **SHOULD** use BackgroundTasks framework for background operations

## Push Notifications

### Requirements (if applicable)

- **MUST** request proper permissions
- **MUST** handle notification payloads correctly
- **SHOULD** implement notification actions
- **MUST** handle notifications in all app states (foreground, background, terminated)

## Security

### Requirements

- **MUST** validate all user input
- **MUST** use HTTPS for all network communications
- **MUST** implement certificate pinning for sensitive apps
- **MUST** never store sensitive data in UserDefaults
- **MUST** use Keychain for credentials and tokens

## Localization

### Requirements

- **SHOULD** support multiple languages
- **MUST** use NSLocalizedString or String Catalog
- **SHOULD** test with different languages and regions
- **MUST** handle right-to-left languages if supporting them

## Related Rules

- [Frontend macOS](./frontend-macos.md) - Similar patterns apply
- [Design Patterns](./design-patterns.md)
- [Build and Deployment](./build-deployment.md)
- [Technology Versions](./technology-versions.md)
- [Project Analysis](./project-analysis.md) - How to analyze current structure
