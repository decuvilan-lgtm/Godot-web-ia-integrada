#!/usr/bin/env python3
"""Port the Android public-GitHub Project Manager importer to the Web editor source.

This patch is intentionally anchor-checked: if upstream Godot changes the Project
Manager structure, the script fails instead of silently producing a partial patch.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / "engine" / "godot"
HEADER = ROOT / "editor/project_manager/project_manager.h"
SOURCE = ROOT / "editor/project_manager/project_manager.cpp"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path.relative_to(ROOT)}: expected exactly one patch anchor, "
            f"found {count}: {old[:100]!r}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if not HEADER.is_file() or not SOURCE.is_file():
    sys.exit("Godot source tree not found; initialize engine/godot first.")

replace_once(
    HEADER,
    "class HFlowContainer;\nclass LineEdit;",
    "class HFlowContainer;\nclass HTTPRequest;\nclass LineEdit;",
)
replace_once(
    HEADER,
    "ProjectDialog *project_dialog = nullptr;",
    """ProjectDialog *project_dialog = nullptr;
	ConfirmationDialog *github_import_dialog = nullptr;
	LineEdit *github_repo_url = nullptr;
	HTTPRequest *github_http_request = nullptr;
	String github_zip_path;
	String github_repo_name;""",
)
replace_once(
    HEADER,
    "	void _import_project();\n	void _new_project();",
    """	void _import_project();
	void _show_github_import_dialog();
	void _github_import_confirmed();
	void _github_download_completed(int p_result, int p_response_code, const PackedStringArray &p_headers, const PackedByteArray &p_body);
	void _new_project();""",
)
replace_once(
    SOURCE,
    '#include "scene/gui/separator.h"\n#include "scene/main/scene_tree.h"',
    '#include "scene/gui/separator.h"\n#include "scene/main/http_request.h"\n#include "scene/main/scene_tree.h"',
)
replace_once(
    SOURCE,
    """void ProjectManager::_import_project() {
	project_dialog->set_mode(ProjectDialog::MODE_IMPORT);
	project_dialog->ask_for_path_and_show();
}

void ProjectManager::_new_project() {""",
    '''void ProjectManager::_import_project() {
	project_dialog->set_mode(ProjectDialog::MODE_IMPORT);
	project_dialog->ask_for_path_and_show();
}

void ProjectManager::_show_github_import_dialog() {
	if (!github_import_dialog) {
		github_import_dialog = memnew(ConfirmationDialog);
		github_import_dialog->set_title(TTRC("Import from GitHub"));
		github_import_dialog->set_ok_button_text(TTRC("Download"));
		VBoxContainer *container = memnew(VBoxContainer);
		container->add_theme_constant_override("separation", 8 * EDSCALE);
		github_import_dialog->add_child(container);
		Label *help = memnew(Label);
		help->set_text(TTRC("Enter a public GitHub repository URL or owner/repository."));
		// Avoid an autowrapped zero-width Label requesting a dialog taller than the viewport.
		container->add_child(help);
		github_repo_url = memnew(LineEdit);
		github_repo_url->set_placeholder(TTRC("https://github.com/owner/repository"));
		github_repo_url->set_clear_button_enabled(true);
		container->add_child(github_repo_url);
		github_import_dialog->register_text_enter(github_repo_url);
		add_child(github_import_dialog);
		github_import_dialog->connect("confirmed", callable_mp(this, &ProjectManager::_github_import_confirmed));
	}
	github_import_dialog->popup_centered(Size2i(520 * EDSCALE, 0));
	github_repo_url->grab_focus();
}

void ProjectManager::_github_import_confirmed() {
	if (github_http_request) {
		_show_error(TTR("A GitHub download is already in progress."));
		return;
	}
	String repository = github_repo_url->get_text().strip_edges();
	repository = repository.trim_prefix("https://github.com/");
	repository = repository.trim_prefix("http://github.com/");
	repository = repository.trim_suffix("/");
	repository = repository.trim_suffix(".git");
	PackedStringArray parts = repository.split("/", false);
	if (parts.size() != 2 || parts[0].is_empty() || parts[1].is_empty() ||
		parts[0].contains_char(' ') || parts[1].contains_char(' ') ||
		parts[0].contains_char('?') || parts[1].contains_char('?') ||
		parts[0].contains_char('#') || parts[1].contains_char('#')) {
		_show_error(TTR("Invalid repository. Use https://github.com/owner/repository."));
		return;
	}
	github_repo_name = parts[1];
	github_zip_path = OS::get_singleton()->get_cache_path().path_join("godot_github_import.zip");
	DirAccess::remove_absolute(github_zip_path);
	github_http_request = memnew(HTTPRequest);
	github_http_request->set_download_file(github_zip_path);
	github_http_request->set_timeout(180.0);
	github_http_request->set_max_redirects(0);
	github_http_request->set_body_size_limit(64 * 1024 * 1024);
	add_child(github_http_request);
	github_http_request->connect("request_completed", callable_mp(this, &ProjectManager::_github_download_completed));
	// The Relay fetches GitHub's codeload redirect server-side. This avoids
	// browser CORS restrictions while keeping the engine's native ZIP installer.
	const String relay_url = "https://godot-web-ia-relay.onrender.com/v1/github/import/";
	Error err = github_http_request->request(relay_url + parts[0].uri_encode() + "/" + parts[1].uri_encode());
	if (err != OK) {
		github_http_request->queue_free();
		github_http_request = nullptr;
		_show_error(TTR("Could not start the GitHub download. Check your internet connection."));
	}
}

void ProjectManager::_github_download_completed(int p_result, int p_response_code, const PackedStringArray &p_headers, const PackedByteArray &p_body) {
	if (github_http_request) {
		github_http_request->queue_free();
		github_http_request = nullptr;
	}
	if (p_result != HTTPRequest::RESULT_SUCCESS || p_response_code != 200 || !FileAccess::exists(github_zip_path)) {
		DirAccess::remove_absolute(github_zip_path);
		_show_error(vformat(TTR("GitHub download failed (HTTP %d). Check the repository URL and make sure it is public."), p_response_code));
		return;
	}
	_install_project(github_zip_path, github_repo_name);
}

void ProjectManager::_new_project() {'''
)
replace_once(
    SOURCE,
    "			hb->add_child(import_btn);\n\n			scan_btn = memnew(Button);",
    """			hb->add_child(import_btn);

			Button *github_import_btn = memnew(Button);
			github_import_btn->set_text(TTRC("GitHub"));
			github_import_btn->set_tooltip_text(TTRC("Import a project from a public GitHub repository."));
			github_import_btn->connect(SceneStringName(pressed), callable_mp(this, &ProjectManager::_show_github_import_dialog));
			hb->add_child(github_import_btn);

			scan_btn = memnew(Button);""",
)
print("Public GitHub import added to the Godot Web Project Manager source.")
