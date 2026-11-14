#!/usr/bin/env python3
"""Temporarily instrument Godot Web thread waits and TCP listen callsites."""
from __future__ import annotations

import argparse
from pathlib import Path

WAIT_SITES = {
    "editor/doc/editor_help.cpp": [
        ("\tloader_thread.wait_to_finish();", "EditorHelp::_finish_regen_script_doc_thread"),
    ],
    "editor/file_system/editor_file_system.cpp": [
        ("\t\t\t\tactive_thread.wait_to_finish();", "EditorFileSystem::exit_tree"),
        ("\t\t\t\t\t\t\tthread_sources.wait_to_finish();", "EditorFileSystem::sources_thread"),
        ("\t\t\t\t\tthread.wait_to_finish();", "EditorFileSystem::scan_thread"),
    ],
    "editor/inspector/editor_resource_preview.cpp": [
        ("\t\t\tthread.wait_to_finish();", "EditorResourcePreview::stop"),
    ],
    "editor/asset_library/asset_library_editor_plugin.cpp": [
        ("\t\t\t\tE.value.thread->wait_to_finish();", "AssetLibraryEditorPlugin::image_thread"),
    ],
    "platform/web/audio_driver_web.cpp": [
        ("\tthread.wait_to_finish();", "AudioDriverWorklet::finish_driver"),
    ],
    "editor/project_manager/project_list.cpp": [
        ("\t\tscan_data->thread->wait_to_finish();", "ProjectList::_finish_scan"),
    ],
    "core/debugger/remote_debugger_peer.cpp": [
        ("\t\tthread.wait_to_finish();", "RemoteDebuggerPeerTCP::close"),
    ],
    "modules/gdscript/language_server/gdscript_language_server.cpp": [
        ("\t\tthread.wait_to_finish();", "GDScriptLanguageServer::stop"),
    ],
}

TCP_SITES = {
    "modules/gdscript/language_server/gdscript_language_protocol.cpp": [
        ("\treturn server->listen(p_port, p_bind_ip);", "GDScriptLanguageProtocol::start"),
    ],
    "editor/debugger/editor_file_server.cpp": [
        ("\tError err = server->listen(port);", "EditorFileServer::start"),
    ],
    "editor/debugger/debug_adapter/debug_adapter_protocol.cpp": [
        ("\treturn server->listen(p_port, p_bind_ip);", "DebugAdapterProtocol::start"),
    ],
    "platform/web/export/editor_http_server.cpp": [
        ("\tError err = server->listen(p_port, p_address);", "EditorHTTPServer::listen"),
    ],
    "editor/debugger/editor_debugger_server.cpp": [
        ("\t\tconst Error err = server->listen(bind_port, bind_host);", "EditorDebuggerServerTCP::start"),
    ],
}


def replace_once(content: str, anchor: str, marker: str, kind: str) -> str:
    count = content.count(anchor)
    if count != 1:
        raise ValueError(f"Expected one {kind} anchor, found {count}: {anchor!r}")
    indentation = anchor[: len(anchor) - len(anchor.lstrip("\t "))]
    call = f'print_line("WEB_DIAG_{kind}_SITE:{marker}");'
    insertion = f"#ifdef WEB_ENABLED\n{indentation}{call}\n#endif\n{anchor}"
    return content.replace(anchor, insertion, 1)


def instrument_source(content: str, sites: list[tuple[str, str]], kind: str) -> str:
    for anchor, marker in sites:
        content = replace_once(content, anchor, marker, kind)
    return content


def instrument_godot_source(root: Path) -> list[str]:
    changed = []
    for path, sites in WAIT_SITES.items():
        full_path = root / path
        if not full_path.is_file():
            raise FileNotFoundError(full_path)
        updated = instrument_source(full_path.read_text(encoding="utf-8"), sites, "WAIT")
        full_path.write_text(updated, encoding="utf-8")
        changed.append(path)
    for path, sites in TCP_SITES.items():
        full_path = root / path
        if not full_path.is_file():
            raise FileNotFoundError(full_path)
        updated = instrument_source(full_path.read_text(encoding="utf-8"), sites, "TCP")
        full_path.write_text(updated, encoding="utf-8")
        changed.append(path)
    return sorted(changed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot-source", required=True, type=Path)
    args = parser.parse_args()
    changed = instrument_godot_source(args.godot_source.resolve())
    print("Instrumented Godot diagnostic callsites:")
    for path in changed:
        print(f" - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
