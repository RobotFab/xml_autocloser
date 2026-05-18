# XML AutoCloser

A system-wide Python script that automatically inserts closing XML/HTML tags
as you type. Works in every app: browsers, Outlook, VS Code, TextEdit, etc.

## What it does

Type `<div>` → instantly becomes `<div>|</div>` with the cursor between the tags.

```
You type:   <div>
You get:    <div>|</div>    (cursor lands at |, ready to type content)
```

Press comma twice to move the cursor past the current closing tag.
The two trigger commas are deleted automatically.

Example:

```
<example>The <hardware>keyboard,,</hardware> is useful.,,</example>
```

After the first two commas, the cursor jumps past `</hardware>`. After the
second two commas, it jumps past `</example>`.

## Installation

**Requires Python 3.8+**

```bash
cd ~/xml-autocloser
pip3 install -r requirements.txt
```

## Running the script

```bash
python3 ~/xml-autocloser/xml_autocloser.py
```

Keep this terminal open (or run it in the background with `&`).

### macOS — Accessibility Permission (required)

macOS blocks global keyboard monitoring without explicit permission:

1. Run the script once — macOS will prompt you or show an error
2. Open **System Settings → Privacy & Security → Accessibility**
3. Click `+` and add your **Terminal** app (or `python3` if prompted)
4. Restart the script

### Auto-start on macOS login

Add this to your shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
# Run xml_autocloser in the background at login
if ! pgrep -f xml_autocloser.py > /dev/null; then
    python3 ~/xml-autocloser/xml_autocloser.py &
fi
```

### Windows — auto-start

1. Run: `pythonw ~/xml-autocloser/xml_autocloser.py` (no console window)
2. Create a shortcut to that command and place it in `shell:startup`

### Linux (X11)

Add to `~/.bashrc`:
```bash
python3 ~/xml-autocloser/xml_autocloser.py &
```

**Wayland note:** pynput has limited Wayland support; X11 is fully supported.

## What auto-closes

- Any XML/HTML tag: `<div>`, `<section>`, `<MyComponent>`, `<ns:element>`
- Tags with attributes: `<div class="foo" id="bar">`

## What does NOT auto-close

- **HTML void elements** (they have no content): `<br>`, `<img>`, `<input>`,
  `<hr>`, `<meta>`, `<link>`, `<col>`, `<embed>`, `<area>`, `<base>`,
  `<param>`, `<source>`, `<track>`, `<wbr>`
- **Self-closing tags**: `<MyTag />` (anything ending with `/>`)
- **Closing tags**: `</div>` won't trigger anything

## Known limitations

- **Paste operations** are not tracked (pasted text won't be in the script's
  buffer, so pasting `<div>` won't auto-close it)
- **Cursor movement** (arrow keys, mouse clicks) can desync the buffer from
  the actual cursor position. Arrow-key movement clears pending jump targets
  when detected
- **VS Code** has its own auto-close extensions that may conflict; the script
  still works but you may get double insertions — disable VS Code's built-in
  auto-close if needed

## Stopping the script

Press `Ctrl+C` in the terminal where it's running, or kill the process:

```bash
pkill -f xml_autocloser.py
```
