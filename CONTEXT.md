# XML Autocloser

Glossary for the click-to-inject editing mode and the existing tag auto-closing behavior.

## Language

**Auto-close**:
The behavior where typing `>` for an opening XML/HTML tag immediately inserts its corresponding closing tag.

**Click-Placement Mode**:
A temporary editing state enabled/disabled by a hotkey, where the user previews tag text “dangling” near the mouse and injects it into the clicked document.

**Dangling Green Elements**:
The greenish preview characters/partial tag text that follow the mouse while the user types during the first click-to-inject step of Click-Placement Mode.

**Click,Click Cycle**:
The two-step sequence in Click-Placement Mode: first click injects **Dangling Green Elements**; second click injects the red closing preview (a slash-prefixed retype of the same green content) and ends the current cycle step.

**Dangling Red Elements**:
The reddish preview content shown during the second click state; it is an automatic retype of the first-step green content, prefixed by the **Red Slash Prefix** (`/`). Typing is not allowed in this red state.

**Red Slash Prefix**:
A red, floating `/` that appears immediately before the first red character of the second-step preview (i.e., at the boundary where the closing tag text is being formed).

## Flagged ambiguities

- **“Place”**:
Click targets the insertion caret position produced by the click. If there is an active selection, injected text replaces the selection.

## Rules

**Click-Placement Mode overrides Auto-close**:
While Click-Placement Mode is active, Auto-close on `>` is disabled.

**Insertion & selection handling**:
Click-injected text is inserted at the click caret position. If there is an active selection, injected text replaces the selection.

**Two-step injection for Click,Click Cycle**:
First click: user typing builds **Dangling Green Elements**, which remain previewed near the mouse.
Second click: the red preview (**Dangling Red Elements**) is constructed automatically as the previously typed green content prefixed with `/`; typing is not allowed during the red state. Second click injects the red content into the document.

**Cycle ending**:
After the second click injects the red content, the cycle ends. If Click-Placement Mode remains enabled, the mode awaits the next first click.

## Example dialogue

Dev: “When you say Shift+comma three times enables the click mode, do you want the normal `>` auto-close to keep running too?”
Domain expert: “No. When click-placement is active, `>` should not auto-insert closing tags; only the dangling previews should be used.”

Dev: “After the first click, does the second-step red preview start with a `/` right before the tag name?”
Domain expert: “Yes, the red slash prefix must float in front of the red dangling mass.”

