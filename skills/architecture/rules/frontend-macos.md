# Frontend macOS Architecture Rule

## Applicability

Use this rule when the project includes macOS application components.

## Technology Requirements

### Language & Platform

- **MUST** use Swift 6.0+
- **MUST** enable strict concurrency checking
- **MUST** target macOS 15.0+ minimum deployment
- **MUST** use Xcode 16+

### Framework

- **MUST** use SwiftUI for all new views
- **MAY** use AppKit for specific requirements (advanced text editing, etc.)
- **MUST** use Observation framework (@Observable)

## Architecture Pattern

### MVVM for macOS

- **MUST** follow MVVM pattern
- **MUST** use @Observable for ViewModels
- **MUST** mark ViewModels with @MainActor
- **MUST** handle window management explicitly
- **MUST** implement proper menu bar integration
- **SHOULD** support keyboard shortcuts
- **MUST** keep Views under 200 lines

## Window Management

### Multi-Window Support

- **MUST** support multiple windows if appropriate
- **SHOULD** use WindowGroup for document-based apps
- **MAY** use Window for utility windows
- **MUST** implement Settings scene for preferences

## Menu Bar and Commands

### Requirements

- **MUST** implement standard menu items (File, Edit, View, etc.)
- **MUST** provide keyboard shortcuts for common actions
- **SHOULD** follow macOS conventions
- **MUST** disable menu items when not applicable
- **SHOULD** use CommandGroup for custom menu items

## File System Integration

### Sandboxing

- **MUST** enable App Sandbox
- **MUST** request appropriate entitlements
- **MUST** use security-scoped bookmarks for persistent access
- **MUST** handle file access permissions properly

### File Operations

- **MUST** use NSOpenPanel/NSSavePanel for file dialogs
- **MUST** support standard file types with UniformTypeIdentifiers
- **MUST** implement proper error handling for file operations
- **SHOULD** support drag and drop for files

## UI Patterns

### Sidebars

- **SHOULD** use NavigationSplitView for multi-column layouts
- **MUST** support sidebar collapsing
- **SHOULD** persist sidebar state

### Toolbars

- **MUST** use native toolbar APIs
- **SHOULD** allow toolbar customization
- **MUST** provide hover states
- **SHOULD** use SF Symbols for toolbar icons

### Windows

- **MUST** support standard window operations (minimize, zoom, close)
- **SHOULD** save and restore window size and position
- **MAY** implement custom window styles when appropriate

## Preferences/Settings

- **MUST** use Settings scene
- **SHOULD** organize into tabs for complex preferences
- **MUST** persist settings properly (UserDefaults or AppStorage)
- **MUST** follow macOS settings conventions

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
- **Models:** Entity names
- **Services:** Purpose-based names
- **Extensions:** Type + purpose format

## State Management

### Local State

- **MUST** use @State for view-local state
- **MUST** use @Binding for child-to-parent communication
- **SHOULD** keep state as low in the hierarchy as possible

### Shared State

- **MUST** use @Observable for shared ViewModels
- **SHOULD** use Environment for dependency injection
- **MAY** use @AppStorage for simple user preferences
- **SHOULD** use proper state management for complex app state

## Data Persistence

### Options

- **MUST** use SwiftData for local persistence (macOS 14+)
- **MAY** use CoreData only if SwiftData is insufficient
- **MUST** use Keychain for sensitive data
- **SHOULD** use UserDefaults only for simple preferences

## Networking

### Requirements

- **MUST** use async/await for all network calls
- **MUST** use URLSession with modern APIs
- **SHOULD** implement retry logic
- **MUST** handle errors gracefully
- **SHOULD** implement proper timeout handling

## Testing

### Requirements

- **MUST** write unit tests for ViewModels
- **SHOULD** use XCTest framework
- **SHOULD** implement UI tests for critical paths
- **MUST** test async operations properly
- **SHOULD** mock external dependencies

## Performance

### Requirements

- **MUST** profile with Instruments
- **SHOULD** optimize list rendering with LazyVStack/LazyHStack
- **MUST** implement pagination for large data sets
- **SHOULD** cache data appropriately
- **MUST** handle memory warnings properly

## Accessibility

### Requirements

- **MUST** provide VoiceOver labels for interactive elements
- **MUST** support keyboard navigation
- **SHOULD** respect user accessibility preferences
- **MUST** ensure sufficient color contrast
- **SHOULD** support Dynamic Type where applicable

## Related Rules

- [Frontend iOS](./frontend-ios.md) - Similar patterns apply
- [Design Patterns](./design-patterns.md)
- [Build and Deployment](./build-deployment.md)
- [Project Analysis](./project-analysis.md) - How to analyze current structure
