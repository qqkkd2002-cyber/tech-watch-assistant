import subprocess
import html
import re
from typing import List, Dict

def run_applescript(script_content: str) -> str:
    """Executes a block of AppleScript and returns stdout."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script_content],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # If Notes app is not accessible or another issue occurs, raise or return empty
        print(f"AppleScript Error: {e.stderr}")
        raise e

def ensure_folder_exists(folder_name: str) -> bool:
    """Creates a folder in Apple Notes if it does not exist."""
    script = f'''
    tell application "Notes"
        if not (exists folder "{folder_name}") then
            make new folder with properties {{name:"{folder_name}"}}
            return "created"
        else
            return "exists"
        end if
    end tell
    '''
    try:
        res = run_applescript(script)
        return res == "created"
    except Exception:
        return False

def get_note_titles(folder_name: str) -> List[str]:
    """Retrieves titles of all notes in a specific folder to check for duplicates."""
    script = f'''
    tell application "Notes"
        set out to ""
        if exists folder "{folder_name}" then
            set noteList to every note in folder "{folder_name}"
            repeat with aNote in noteList
                set out to out & (name of aNote) & "\n"
            end repeat
        end if
        return out
    end tell
    '''
    try:
        output = run_applescript(script)
        if not output:
            return []
        return [line.strip() for line in output.split("\n") if line.strip()]
    except Exception:
        return []

def markdown_to_apple_notes_html(md_text: str) -> str:
    """Converts basic markdown elements to HTML appropriate for Apple Notes body.
    
    Apple Notes requires standard tags like <div>, <h1>, <h2>, <strong>, <ul>, <li>.
    """
    # Escape HTML special characters
    lines = md_text.split("\n")
    html_lines = []
    
    in_list = False
    
    for line in lines:
        line_strip = line.strip()
        
        # Handle lists
        if line_strip.startswith("- ") or line_strip.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = html.escape(line_strip[2:])
            # Basic bold parsing inside list item
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
            html_lines.append(f"<li>{content}</li>")
            continue
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
        
        # Handle headers
        if line_strip.startswith("### "):
            content = html.escape(line_strip[4:])
            html_lines.append(f"<h3>{content}</h3>")
        elif line_strip.startswith("## "):
            content = html.escape(line_strip[3:])
            html_lines.append(f"<h2>{content}</h2>")
        elif line_strip.startswith("# "):
            content = html.escape(line_strip[2:])
            html_lines.append(f"<h1>{content}</h1>")
        elif not line_strip:
            html_lines.append("<div><br></div>")
        else:
            content = html.escape(line)
            # Basic bold parsing
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
            # Basic link parsing
            content = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', content)
            html_lines.append(f"<div>{content}</div>")
            
    if in_list:
        html_lines.append("</ul>")
        
    return "".join(html_lines)

def create_note(folder_name: str, title: str, md_body: str) -> bool:
    """Creates a new note inside a specified folder."""
    ensure_folder_exists(folder_name)
    
    # Check if a note with this title already exists in this folder to prevent spam
    existing_titles = get_note_titles(folder_name)
    if title in existing_titles:
        print(f"Note '{title}' already exists in '{folder_name}'. Skipping creation.")
        return False
        
    html_body = markdown_to_apple_notes_html(md_body)
    
    # Escape quotes and backslashes for AppleScript string literal
    escaped_title = title.replace('\\', '\\\\').replace('"', '\\"')
    escaped_body = html_body.replace('\\', '\\\\').replace('"', '\\"')
    
    script = f'''
    tell application "Notes"
        set targetFolder to folder "{folder_name}"
        make new note in targetFolder with properties {{name:"{escaped_title}", body:"{escaped_body}"}}
        return "success"
    end tell
    '''
    try:
        res = run_applescript(script)
        return res == "success"
    except Exception as e:
        print(f"Failed to create note: {e}")
        return False

def get_notes(folder_name: str) -> List[Dict[str, str]]:
    """Retrieves titles and full bodies of notes in a folder."""
    script = f'''
    tell application "Notes"
        set out to ""
        if exists folder "{folder_name}" then
            set noteList to every note in folder "{folder_name}"
            repeat with aNote in noteList
                set out to out & (name of aNote) & "|||" & (body of aNote) & "\n===NOTE_SEP===\n"
            end repeat
        end if
        return out
    end tell
    '''
    try:
        output = run_applescript(script)
        if not output:
            return []
        
        notes = []
        raw_notes = output.split("\n===NOTE_SEP===\n")
        for rn in raw_notes:
            if not rn.strip():
                continue
            parts = rn.split("|||", 1)
            if len(parts) == 2:
                notes.append({
                    "title": parts[0].strip(),
                    "body": parts[1].strip()
                })
        return notes
    except Exception as e:
        print(f"Failed to get notes: {e}")
        return []

if __name__ == "__main__":
    # Test connection
    print("Testing Apple Notes folder creation...")
    folder = "Tech Watch - Docs"
    if ensure_folder_exists(folder):
        print(f"Folder '{folder}' checked/created successfully!")
        titles = get_note_titles(folder)
        print(f"Existing notes: {titles}")
    else:
        print("Folder check failed. Make sure Notes app is accessible.")
