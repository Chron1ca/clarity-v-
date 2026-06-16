"""Create Start Menu + Desktop shortcuts for Clarity.V.

Run once: `python install_shortcuts.py`.
The shortcuts launch run.pyw via the project's .venv Clarity.V.exe, so no
console window appears and Clarity.V opens like any other Windows app.
"""

from __future__ import annotations

import os
import sys
import shutil
import gc
from pathlib import Path

import pythoncom
from win32com.client import Dispatch  # type: ignore[import-not-found]
from win32com.propsys import propsys, pscon
from win32com.shell import shell, shellcon


def _align_32(offset: int) -> int:
    return (offset + 3) & ~3

def _align_bytes(b: bytes) -> bytes:
    pad = (4 - (len(b) % 4)) % 4
    return b + b"\x00" * pad

def _parse_string(data: bytes, offset: int) -> dict:
    import struct
    start = offset
    wLength, wValueLength, wType = struct.unpack_from("<HHH", data, offset)
    offset += 6
    
    key_chars = []
    while True:
        char = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if char == 0:
            break
        key_chars.append(chr(char))
    key = "".join(key_chars)
    
    offset = _align_32(offset)
    
    value = ""
    if wValueLength > 0:
        val_chars = []
        for _ in range(wValueLength):
            char = struct.unpack_from("<H", data, offset)[0]
            offset += 2
            if char == 0:
                continue
            val_chars.append(chr(char))
        value = "".join(val_chars)
        
    return {
        "type": "String",
        "key": key,
        "wType": wType,
        "value": value
    }

def _parse_string_table(data: bytes, offset: int) -> dict:
    import struct
    start = offset
    wLength, wValueLength, wType = struct.unpack_from("<HHH", data, offset)
    offset += 6
    
    key_chars = []
    while True:
        char = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if char == 0:
            break
        key_chars.append(chr(char))
    key = "".join(key_chars)
    
    offset = _align_32(offset)
    
    strings = []
    while offset < start + wLength:
        str_wLength = struct.unpack_from("<H", data, offset)[0]
        string_entry = _parse_string(data, offset)
        strings.append(string_entry)
        offset = _align_32(offset + str_wLength)
        
    return {
        "type": "StringTable",
        "key": key,
        "wType": wType,
        "children": strings
    }

def _parse_string_file_info(data: bytes, offset: int) -> dict:
    import struct
    start = offset
    wLength, wValueLength, wType = struct.unpack_from("<HHH", data, offset)
    offset += 6
    
    key_chars = []
    while True:
        char = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if char == 0:
            break
        key_chars.append(chr(char))
    key = "".join(key_chars)
    
    offset = _align_32(offset)
    
    children = []
    while offset < start + wLength:
        child_wLength = struct.unpack_from("<H", data, offset)[0]
        child = _parse_string_table(data, offset)
        children.append(child)
        offset = _align_32(offset + child_wLength)
        
    return {
        "type": "StringFileInfo",
        "key": key,
        "wType": wType,
        "children": children
    }

def _parse_var(data: bytes, offset: int) -> dict:
    import struct
    start = offset
    wLength, wValueLength, wType = struct.unpack_from("<HHH", data, offset)
    offset += 6
    
    key_chars = []
    while True:
        char = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if char == 0:
            break
        key_chars.append(chr(char))
    key = "".join(key_chars)
    
    offset = _align_32(offset)
    value_bytes = data[offset : offset + wValueLength]
    
    return {
        "type": "Var",
        "key": key,
        "wType": wType,
        "value": value_bytes
    }

def _parse_var_file_info(data: bytes, offset: int) -> dict:
    import struct
    start = offset
    wLength, wValueLength, wType = struct.unpack_from("<HHH", data, offset)
    offset += 6
    
    key_chars = []
    while True:
        char = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if char == 0:
            break
        key_chars.append(chr(char))
    key = "".join(key_chars)
    
    offset = _align_32(offset)
    
    children = []
    while offset < start + wLength:
        child_wLength = struct.unpack_from("<H", data, offset)[0]
        child = _parse_var(data, offset)
        children.append(child)
        offset = _align_32(offset + child_wLength)
        
    return {
        "type": "VarFileInfo",
        "key": key,
        "wType": wType,
        "children": children
    }

def _parse_version_info(data: bytes) -> dict:
    import struct
    offset = 0
    wLength, wValueLength, wType = struct.unpack_from("<HHH", data, offset)
    offset += 6
    
    key_chars = []
    while True:
        char = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if char == 0:
            break
        key_chars.append(chr(char))
    key = "".join(key_chars)
    
    offset = _align_32(offset)
    fixed_info_bytes = data[offset : offset + wValueLength]
    offset += wValueLength
    offset = _align_32(offset)
    
    children = []
    while offset < wLength:
        child_offset = offset
        child_wLength, child_wValueLength, child_wType = struct.unpack_from("<HHH", data, offset)
        
        peek_offset = offset + 6
        child_key_chars = []
        while True:
            char = struct.unpack_from("<H", data, peek_offset)[0]
            peek_offset += 2
            if char == 0:
                break
            child_key_chars.append(chr(char))
        child_key = "".join(child_key_chars)
        
        if child_key == "StringFileInfo":
            child = _parse_string_file_info(data, offset)
        elif child_key == "VarFileInfo":
            child = _parse_var_file_info(data, offset)
        else:
            break
            
        children.append(child)
        offset = _align_32(offset + child_wLength)
        
    return {
        "type": "VS_VERSION_INFO",
        "key": key,
        "wType": wType,
        "fixed_info": fixed_info_bytes,
        "children": children
    }

def _serialize_string(node: dict) -> bytes:
    import struct
    key_bytes = node["key"].encode("utf-16le") + b"\x00\x00"
    val_bytes = node["value"].encode("utf-16le") + b"\x00\x00"
    wValueLength = len(val_bytes) // 2
    wType = node["wType"]
    
    header = struct.pack("<HHH", 0, wValueLength, wType)
    data = header + key_bytes
    data = _align_bytes(data)
    data += val_bytes
    
    wLength = len(data)
    data = struct.pack("<H", wLength) + data[2:]
    return data

def _serialize_string_table(node: dict) -> bytes:
    import struct
    key_bytes = node["key"].encode("utf-16le") + b"\x00\x00"
    wType = node["wType"]
    
    header = struct.pack("<HHH", 0, 0, wType)
    data = header + key_bytes
    data = _align_bytes(data)
    
    for child in node["children"]:
        child_data = _serialize_string(child)
        data += child_data
        data = _align_bytes(data)
        
    wLength = len(data)
    data = struct.pack("<H", wLength) + data[2:]
    return data

def _serialize_string_file_info(node: dict) -> bytes:
    import struct
    key_bytes = node["key"].encode("utf-16le") + b"\x00\x00"
    wType = node["wType"]
    
    header = struct.pack("<HHH", 0, 0, wType)
    data = header + key_bytes
    data = _align_bytes(data)
    
    for child in node["children"]:
        child_data = _serialize_string_table(child)
        data += child_data
        data = _align_bytes(data)
        
    wLength = len(data)
    data = struct.pack("<H", wLength) + data[2:]
    return data

def _serialize_var(node: dict) -> bytes:
    import struct
    key_bytes = node["key"].encode("utf-16le") + b"\x00\x00"
    wType = node["wType"]
    wValueLength = len(node["value"])
    
    header = struct.pack("<HHH", 0, wValueLength, wType)
    data = header + key_bytes
    data = _align_bytes(data)
    data += node["value"]
    
    wLength = len(data)
    data = struct.pack("<H", wLength) + data[2:]
    return data

def _serialize_var_file_info(node: dict) -> bytes:
    import struct
    key_bytes = node["key"].encode("utf-16le") + b"\x00\x00"
    wType = node["wType"]
    
    header = struct.pack("<HHH", 0, 0, wType)
    data = header + key_bytes
    data = _align_bytes(data)
    
    for child in node["children"]:
        child_data = _serialize_var(child)
        data += child_data
        data = _align_bytes(data)
        
    wLength = len(data)
    data = struct.pack("<H", wLength) + data[2:]
    return data

def _serialize_version_info(node: dict) -> bytes:
    import struct
    key_bytes = node["key"].encode("utf-16le") + b"\x00\x00"
    wType = node["wType"]
    wValueLength = len(node["fixed_info"])
    
    header = struct.pack("<HHH", 0, wValueLength, wType)
    data = header + key_bytes
    data = _align_bytes(data)
    data += node["fixed_info"]
    data = _align_bytes(data)
    
    for child in node["children"]:
        if child["type"] == "StringFileInfo":
            child_data = _serialize_string_file_info(child)
        elif child["type"] == "VarFileInfo":
            child_data = _serialize_var_file_info(child)
        data += child_data
        data = _align_bytes(data)
        
    wLength = len(data)
    data = struct.pack("<H", wLength) + data[2:]
    return data

def _patch_exe(pythonw_path: Path, clarity_exe_path: Path) -> None:
    """Copy pythonw.exe to Clarity.V.exe and patch version info to 'Clarity.V'."""
    import pefile
    import win32api
    import win32con
    
    print(f"Copying {pythonw_path} to {clarity_exe_path}...")
    shutil.copy2(pythonw_path, clarity_exe_path)
    
    # Extract version resource from pythonw.exe
    pe = pefile.PE(pythonw_path)
    version_resource = None
    for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if entry.id == pefile.RESOURCE_TYPE["RT_VERSION"]:
            version_resource = entry
            break
            
    if not version_resource:
        print("Warning: No version resource found in pythonw.exe. Skipping metadata patch.")
        return
        
    ver_dir = version_resource.directory.entries[0]
    lang_dir = ver_dir.directory.entries[0]
    
    data = pe.get_data(lang_dir.data.struct.OffsetToData, lang_dir.data.struct.Size)
    lang_id = lang_dir.id
    
    # Parse and modify version info tree
    tree = _parse_version_info(data)
    for child in tree["children"]:
        if child["type"] == "StringFileInfo":
            for table in child["children"]:
                for string in table["children"]:
                    if string["key"] == "FileDescription":
                        string["value"] = "Clarity.V"
                    elif string["key"] == "ProductName":
                        string["value"] = "Clarity.V"
                    elif string["key"] == "CompanyName":
                        string["value"] = "Chron1ca"
                        
    new_data = _serialize_version_info(tree)
    
    # Write version resource using Win32 API
    print(f"Updating version metadata in {clarity_exe_path}...")
    handle = win32api.BeginUpdateResource(str(clarity_exe_path), False)
    # RT_VERSION = 16
    win32api.UpdateResource(handle, 16, 1, new_data, lang_id)
    win32api.EndUpdateResource(handle, False)
    print("Metadata updated successfully.")


def _make_shortcut(
    target_path: Path,
    arguments: str,
    working_dir: Path,
    shortcut_path: Path,
    description: str,
    icon_path: Path | None = None,
) -> None:
    """Write a .lnk file via the Windows Shell COM API."""
    shell_ws = Dispatch("WScript.Shell")
    sc = shell_ws.CreateShortCut(str(shortcut_path))
    sc.Targetpath = str(target_path)
    sc.Arguments = arguments
    sc.WorkingDirectory = str(working_dir)
    sc.Description = description
    if icon_path:
        sc.IconLocation = str(icon_path)
    else:
        sc.IconLocation = str(target_path)
    sc.save()


def _set_app_user_model_id(lnk_path: Path, app_id: str) -> None:
    """Set System.AppUserModel.ID property on the shortcut."""
    # Ensure WScript.Shell released the handle
    gc.collect()
    try:
        ps = propsys.SHGetPropertyStoreFromParsingName(
            str(lnk_path),
            None,
            shellcon.GPS_READWRITE,
            propsys.IID_IPropertyStore
        )
        prop_var = propsys.PROPVARIANTType(app_id, pythoncom.VT_LPWSTR)
        ps.SetValue(pscon.PKEY_AppUserModel_ID, prop_var)
        ps.Commit()
        ps = None
        gc.collect()
        print(f"Set AppUserModelID '{app_id}' on {lnk_path}")
    except Exception as e:
        print(f"Error setting AppUserModelID on {lnk_path}: {e}", file=sys.stderr)


def _setup_jumplist(
    clarity_exe: Path,
    entry: Path,
    working_dir: Path,
    logo: Path,
    app_id: str
) -> None:
    """Register Settings task in the taskbar Jump List."""
    print("Configuring Jump List tasks...")
    try:
        dl = pythoncom.CoCreateInstance(
            shell.CLSID_DestinationList,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_ICustomDestinationList
        )
        dl.SetAppID(app_id)
        
        # Clear previous Jump List
        try:
            dl.DeleteList(app_id)
        except Exception:
            pass
            
        min_slots, removed = dl.BeginList()
        
        coll = pythoncom.CoCreateInstance(
            shell.CLSID_EnumerableObjectCollection,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IObjectCollection
        )
        
        # Create ShellLink for Settings task
        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLinkW
        )
        link.SetPath(str(clarity_exe))
        link.SetArguments(f'"{entry}" --settings')
        link.SetWorkingDirectory(str(working_dir))
        if logo.exists():
            link.SetIconLocation(str(logo), 0)
            
        # Set System.Title on the task link (required to display correctly)
        ps = link.QueryInterface(propsys.IID_IPropertyStore)
        prop_var = propsys.PROPVARIANTType("Settings", pythoncom.VT_LPWSTR)
        ps.SetValue(pscon.PKEY_Title, prop_var)
        ps.Commit()
        
        coll.AddObject(link)
        
        # Commit to user tasks list
        arr = coll.QueryInterface(shell.IID_IObjectArray)
        dl.AddUserTasks(arr)
        dl.CommitList()
        print("Jump List Settings task registered successfully.")
    except Exception as e:
        print(f"Error configuring Jump List: {e}", file=sys.stderr)


def main() -> int:
    repo = Path(__file__).resolve().parent
    pythonw = repo / ".venv" / "Scripts" / "pythonw.exe"
    clarity_exe = repo / ".venv" / "Scripts" / "Clarity.V.exe"
    entry = repo / "run.pyw"
    logo = repo / "cv_logo.ico"
    app_id = "chron1ca.clarity_v.1.0"
    
    if not pythonw.exists():
        print(f"ERROR: pythonw not found at {pythonw}", file=sys.stderr)
        return 1
    if not entry.exists():
        print(f"ERROR: run.pyw not found at {entry}", file=sys.stderr)
        return 1

    # 1. Copy and patch pythonw.exe to Clarity.V.exe
    try:
        _patch_exe(pythonw, clarity_exe)
    except Exception as e:
        print(f"ERROR: Failed to copy/patch Clarity.V.exe: {e}", file=sys.stderr)
        return 1

    # 2. Generate shortcuts
    start_menu = (
        Path(os.environ["APPDATA"])
        / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    )
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"

    for parent in (start_menu, desktop):
        parent.mkdir(parents=True, exist_ok=True)
        link = parent / "Clarity.V.lnk"
        _make_shortcut(
            target_path=clarity_exe,
            arguments=f'"{entry}"',
            working_dir=repo,
            shortcut_path=link,
            description="Clarity.V — local voice dictation",
            icon_path=logo if logo.exists() else None,
        )
        print(f"wrote {link}")
        
        # 3. Set AppUserModelID on shortcut link
        _set_app_user_model_id(link, app_id)

    # 4. Configure Taskbar Jump List tasks
    _setup_jumplist(clarity_exe, entry, repo, logo, app_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

