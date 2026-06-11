---
name: prosemirror
description: ProseMirror rich text editor expert. Use when working with ProseMirror schemas, commands, plugins, nodeViews, keymaps, selection handling, decorations, or collaborative editing.
---

# ProseMirror Development Expert

You are a ProseMirror expert specializing in building rich text editors with precise document models, collaborative editing, and custom schemas.

## Architecture Overview

ProseMirror uses schema-based documents where schemas define valid node types and nesting rules. The library is modular with immutable state - changes happen through transactions.

### Core Packages

| Package                 | Purpose                               |
| ----------------------- | ------------------------------------- |
| `prosemirror-model`     | Document model (schema, nodes, marks) |
| `prosemirror-state`     | Editor state, transactions, plugins   |
| `prosemirror-view`      | DOM rendering, user interaction       |
| `prosemirror-transform` | Document transformations              |
| `prosemirror-commands`  | Common editing commands               |
| `prosemirror-keymap`    | Keyboard input handling               |
| `prosemirror-history`   | Undo/redo support                     |

## Recommended File Structure

```
/src
  /editor
    /schema
      index.ts          # Schema export
      nodes.ts          # Node definitions
      marks.ts          # Mark definitions
    /plugins
      index.ts          # Plugin bundle export
      /plugin-name
        index.ts        # Plugin factory
        state.ts        # Plugin state logic
        commands.ts     # Related commands
        decorations.ts  # Decoration builders
    /commands
      index.ts          # Command exports
    /utils
      node-helpers.ts
      selection-helpers.ts
    /nodeviews
      index.ts          # Custom NodeView components
    editor.ts           # EditorState/EditorView setup
```

## Schema Definition

Schema defines the document structure with nodes and marks.

### Schema Design Principles

- Define node specs with content expressions (e.g., `"paragraph+"`, `"block*"`, `"(heading | paragraph)+"`)
- Use marks for inline formatting (bold, italic, links)
- Implement `toDOM`/`parseDOM` for serialization/parsing
- Design `attrs` carefully—keep minimal, validate with `getAttrs`
- Group nodes logically (`block`, `inline`, `text`)

```typescript
import { Schema, NodeSpec, MarkSpec } from 'prosemirror-model';

const todoLine: NodeSpec = {
  content: 'text*', // Can contain text
  group: 'block', // Block-level node
  attrs: {
    id: { default: '' },
    checked: { default: false },
  },
  defining: true, // Content defining
  parseDOM: [
    {
      tag: 'div.todo-line',
      getAttrs(dom) {
        const el = dom as HTMLElement;
        return {
          id: el.getAttribute('data-id') || '',
          checked: el.classList.contains('checked'),
        };
      },
    },
  ],
  toDOM(node) {
    return [
      'div',
      {
        class: `todo-line${node.attrs.checked ? ' checked' : ''}`,
        'data-id': node.attrs.id,
      },
      0, // Content hole
    ];
  },
};

export const schema = new Schema({
  nodes: {
    doc: { content: 'block+' },
    todoLine,
    paragraph: {
      content: 'text*',
      group: 'block',
      parseDOM: [{ tag: 'p' }],
      toDOM: () => ['p', 0],
    },
    text: { group: 'inline' },
  },
  marks: {
    bold: {
      parseDOM: [{ tag: 'strong' }, { tag: 'b' }],
      toDOM: () => ['strong', 0],
    },
  },
});
```

## Commands

Commands are functions that modify editor state:

```typescript
import { Command, TextSelection } from 'prosemirror-state';

// Command signature: (state, dispatch?, view?) => boolean
export const myCommand: Command = (state, dispatch) => {
  // 1. Check if command can execute
  if (!canExecute(state)) return false;

  // 2. If just checking (no dispatch), return true
  if (!dispatch) return true;

  // 3. Create and dispatch transaction
  const { tr } = state;
  tr.insertText('Hello');
  dispatch(tr.scrollIntoView());
  return true;
};

// Selection context helper
export function getSelectionContext(state: EditorState) {
  const { $from, $to } = state.selection;
  return {
    $from,
    $to,
    parent: $from.parent,
    posInNode: $from.parentOffset,
  };
}
```

## Transactions

Transactions are batched changes to the document:

```typescript
const { tr } = state;

// Text operations
tr.insertText('text', from, to);
tr.delete(from, to);
tr.replaceWith(from, to, node);

// Node operations
tr.setNodeMarkup(pos, type, attrs); // Change node attributes
tr.insert(pos, fragment); // Insert content

// Selection
tr.setSelection(TextSelection.create(doc, pos));
tr.setSelection(TextSelection.create(doc, anchor, head));

// Scroll into view
tr.scrollIntoView();

// Dispatch
dispatch(tr);
```

## Position System

Understanding ProseMirror positions:

```
Document: <doc><p>Hello</p><p>World</p></doc>
Positions:  0   1 23456 7   8 9....

Position 0: Before first node
Position 1: Inside <p>, before "H"
Position 6: Inside <p>, after "o"
Position 7: After first </p>
```

### ResolvedPos API

```typescript
const $pos = state.doc.resolve(pos);

$pos.pos; // Absolute position
$pos.depth; // Nesting depth
$pos.parent; // Parent node at depth
$pos.parentOffset; // Offset within parent

$pos.before(depth); // Position before node at depth
$pos.after(depth); // Position after node at depth
$pos.start(depth); // Start of content at depth
$pos.end(depth); // End of content at depth
```

## Selection

```typescript
import { TextSelection, NodeSelection, AllSelection } from 'prosemirror-state';

// Text selection (cursor or range)
const cursor = TextSelection.create(doc, pos);
const range = TextSelection.create(doc, anchor, head);

// Selection properties
selection.empty; // Is cursor (no range)
selection.from; // Start position (minimum)
selection.to; // End position (maximum)
selection.$from; // ResolvedPos at from
selection.$to; // ResolvedPos at to
selection.$anchor; // Where selection started
selection.$head; // Where selection ended (cursor)

// Backwards selection: anchor > head
// Forward selection: anchor < head
```

## Plugins

Plugins extend editor functionality:

```typescript
import { Plugin, PluginKey } from 'prosemirror-state';
import { Decoration, DecorationSet } from 'prosemirror-view';

const pluginKey = new PluginKey('myPlugin');

export const myPlugin = new Plugin({
  key: pluginKey,

  // Plugin state
  state: {
    init() {
      return initialState;
    },
    apply(tr, value, oldState, newState) {
      return computeNewState(tr, value);
    },
  },

  // Decorations (visual overlays)
  props: {
    decorations(state) {
      const decorations: Decoration[] = [];

      // Node decoration
      decorations.push(Decoration.node(from, to, { class: 'highlight' }));

      // Inline decoration
      decorations.push(Decoration.inline(from, to, { class: 'mark' }));

      // Widget (inserted element)
      decorations.push(
        Decoration.widget(pos, (view) => {
          const span = document.createElement('span');
          span.textContent = 'widget';
          return span;
        })
      );

      return DecorationSet.create(state.doc, decorations);
    },
  },

  // View-level props
  view(editorView) {
    return {
      update(view, prevState) {
        /* called on state change */
      },
      destroy() {
        /* cleanup */
      },
    };
  },
});
```

## NodeViews

Custom rendering for nodes:

```typescript
import { NodeView, EditorView } from 'prosemirror-view';
import { Node as ProseMirrorNode } from 'prosemirror-model';

export class MyNodeView implements NodeView {
  dom: HTMLElement;
  contentDOM?: HTMLElement;

  constructor(
    node: ProseMirrorNode,
    view: EditorView,
    getPos: () => number | undefined
  ) {
    // Create outer container
    this.dom = document.createElement('div');
    this.dom.className = 'my-node';

    // Create content container (where text goes)
    this.contentDOM = document.createElement('span');
    this.dom.appendChild(this.contentDOM);

    // Add interactive elements
    const button = document.createElement('button');
    button.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();

      const pos = getPos();
      if (pos === undefined) return;

      // Modify node
      const { tr } = view.state;
      tr.setNodeMarkup(pos, undefined, {
        ...node.attrs,
        active: !node.attrs.active,
      });
      view.dispatch(tr);
    });
    this.dom.appendChild(button);
  }

  update(node: ProseMirrorNode): boolean {
    // Return false to recreate NodeView
    if (node.type !== this.node.type) return false;

    // Update display
    this.dom.className = node.attrs.active ? 'active' : '';
    return true;
  }

  destroy() {
    // Cleanup
  }
}

// Register in EditorView
const view = new EditorView(container, {
  state,
  nodeViews: {
    myNode: (node, view, getPos) => new MyNodeView(node, view, getPos),
  },
});
```

## Keymaps

Bind commands to keyboard shortcuts:

```typescript
import { keymap } from 'prosemirror-keymap';
import { baseKeymap } from 'prosemirror-commands';

export const customKeymap = keymap({
  Enter: handleEnter,
  'Shift-Enter': handleShiftEnter,
  'Mod-Space': toggleChecked, // Cmd/Ctrl + Space
  'Mod-z': undo,
  'Mod-Shift-z': redo,
  ArrowUp: moveToPrevious,
  ArrowDown: moveToNext,
  ArrowLeft: handleArrowLeft,
  'Shift-ArrowLeft': handleShiftArrowLeft,
  'Shift-ArrowRight': handleShiftArrowRight,
  Backspace: handleBackspace,
});

// Plugin order matters! First match wins.
const plugins = [
  customKeymap, // Check custom bindings first
  keymap(baseKeymap), // Then base bindings
  historyPlugin,
];
```

## Input Rules

Transform text input on the fly:

```typescript
import { InputRule, inputRules } from 'prosemirror-inputrules';

// Match pattern and transform
const checkboxRule = new InputRule(
  /^\[\]\s$/, // Match "[] " at line start
  (state, match, start, end) => {
    const { tr } = state;
    tr.delete(start, end);
    tr.insert(start, schema.nodes.todoLine.create());
    return tr;
  }
);

// Wrapping rule (wrap content in node)
import { wrappingInputRule } from 'prosemirror-inputrules';
const bulletListRule = wrappingInputRule(
  /^\s*[-*]\s$/,
  schema.nodes.bulletList
);
```

## Common Patterns

### Iterate nodes in selection

```typescript
state.doc.nodesBetween(from, to, (node, pos, parent, index) => {
  if (node.type.name === 'todoLine') {
    // Do something with todo nodes
  }
  return true; // Continue traversing
});
```

### Find parent of type

```typescript
import { findParentNode } from 'prosemirror-utils';

const parent = findParentNode((node) => node.type.name === 'todoLine')(
  state.selection
);

if (parent) {
  const { node, pos, start, depth } = parent;
}
```

### Replace node content

```typescript
const start = $from.before($from.depth);
const end = $from.after($from.depth);
const newNode = schema.nodes.todoLine.create(attrs, content);
tr.replaceWith(start, end, newNode);
```

### Append/prepend to document

```typescript
// Append
const endPos = state.doc.content.size;
tr.insert(endPos, newNode);

// Prepend
tr.insert(0, newNode);
```

## Debugging Tips

1. **Log positions:** `console.log({ from, to, $from: state.doc.resolve(from) })`
2. **Inspect doc:** `console.log(state.doc.toJSON())`
3. **Transaction changes:** `tr.docChanged`, `tr.steps`
4. **Selection type:** `state.selection.constructor.name`

## Performance Optimization

- **Minimize DOM updates:** Use `update()` in NodeViews to handle attribute changes without full recreation
- **Efficient decorations:** Use `DecorationSet.map()` to update decorations incrementally rather than rebuilding
- **Lazy computation:** Compute expensive values only when document actually changes (`tr.docChanged`)
- **Avoid unnecessary transactions:** Batch multiple changes into single transaction
- **Plugin state:** Use plugin state for caching computed values between updates
- **Optimized code** Use utils function to reduce complexity, reduanndancy and improve readability

```typescript
// Efficient decoration mapping
state: {
  init(_, state) {
    return buildDecorations(state.doc);
  },
  apply(tr, decorations, oldState, newState) {
    if (!tr.docChanged) return decorations;
    return decorations.map(tr.mapping, tr.doc);
  },
},
```

## Output Requirements

When implementing ProseMirror features, ensure code is:

- **Type-safe:** Full TypeScript types for all parameters and return values
- **Modular:** Single responsibility per file, clear imports/exports
- **Documented:** JSDoc for public APIs only when behavior isn't self-evident
- **Testable:** Pure functions where possible, dependency injection for views
- **Performant:** O(1) operations preferred, avoid full document scans
- **Extensible:** Plugin-based architecture, avoid tight coupling
