#!/usr/bin/env python3
"""Playwright screenshot renderer and isolated `agent-assets` branch publisher.

Renders live component HTML or UI mockups using the repository's real
`site_ui/styles.css` and `site_ui/helpers.js` in both Light and Dark mode,
and optionally publishes PNG artifacts to an isolated orphan `agent-assets`
branch so GitHub Issues and Pull Requests can embed real screenshots without
polluting `main`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from scripts import agent_backlog
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import agent_backlog  # type: ignore[no-redef]


ASSETS_BRANCH = "agent-assets"


def read_file_from_ref(rel_path: str, ref: Optional[str] = None, repo_root: str = ".") -> str:
    """Read a repository file either from the working tree (`ref=None`) or a git ref."""
    norm = rel_path.strip().replace("\\", "/")
    if not ref:
        full_path = os.path.join(repo_root, norm)
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    proc = subprocess.run(
        ["git", "show", f"{ref}:{norm}"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return proc.stdout


def launch_playwright_browser(playwright: Any) -> Any:
    """Launch headless Chromium using bundled Chromium or installed Edge/Chrome channels."""
    errors: List[str] = []
    for kwargs in (
        {"headless": True},
        {"headless": True, "channel": "msedge"},
        {"headless": True, "channel": "chrome"},
    ):
        try:
            return playwright.chromium.launch(**kwargs)
        except Exception as exc:
            errors.append(f"{kwargs}: {exc}")
    raise RuntimeError("Could not launch Playwright Chromium/Edge/Chrome:\n" + "\n".join(errors))


def build_preview_html(
    body_html: str,
    css_text: str,
    helpers_js: str = "",
    inline_script: str = "",
    dark_mode: bool = False,
    stage_padding: int = 24,
    extra_css: str = "",
) -> str:
    """Wrap an HTML component/mockup inside a standalone page styled with `site_ui/styles.css`."""
    body_cls = "dark-mode" if dark_mode else ""
    bg = "#0f172a" if dark_mode else "#f1f5f9"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
{css_text}
html, body {{
    margin: 0;
    padding: 0;
    background: {bg};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}}
.screenshot-stage {{
    display: inline-block;
    padding: {stage_padding}px;
    background: {bg};
    min-width: 680px;
    box-sizing: border-box;
}}
.screenshot-stage .modal-box {{
    margin: 0 auto;
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.22);
}}
{extra_css}
</style>
</head>
<body class="{body_cls}">
<div id="screenshot-stage" class="screenshot-stage">
{body_html}
</div>
<script>
{helpers_js}
{inline_script}
</script>
</body>
</html>
"""


def capture_html_screenshots(
    body_html: str,
    output_dir: str,
    name_prefix: str,
    css_text: str,
    helpers_js: str = "",
    inline_script: str = "",
    viewport: Tuple[int, int] = (920, 900),
    capture_dark_mode: bool = True,
    extra_css: str = "",
) -> List[Dict[str, str]]:
    """Render `body_html` in Light (and optionally Dark) mode and save clipped PNGs."""
    from playwright.sync_api import sync_playwright

    os.makedirs(output_dir, exist_ok=True)
    modes: List[Tuple[str, bool]] = [("Light Mode", False)]
    if capture_dark_mode:
        modes.append(("Dark Mode", True))

    results: List[Dict[str, str]] = []
    with sync_playwright() as p:
        browser = launch_playwright_browser(p)
        try:
            for label, is_dark in modes:
                page = browser.new_page(
                    viewport={"width": viewport[0], "height": viewport[1]},
                    device_scale_factor=2,
                )
                page_errors: List[str] = []
                page.on("pageerror", lambda err: page_errors.append(str(err)))
                try:
                    suffix = "dark" if is_dark else "light"
                    out_path = os.path.join(output_dir, f"{name_prefix}-{suffix}.png")
                    html = build_preview_html(
                        body_html=body_html,
                        css_text=css_text,
                        helpers_js=helpers_js,
                        inline_script=inline_script,
                        dark_mode=is_dark,
                        extra_css=extra_css,
                    )
                    page.set_content(html, wait_until="load")
                    if page_errors:
                        raise RuntimeError(f"Page JS error while rendering {out_path}: {page_errors}")
                    stage = page.locator("#screenshot-stage")
                    stage.screenshot(path=out_path)
                    results.append(
                        {
                            "mode": suffix,
                            "label": label,
                            "path": out_path.replace("\\", "/"),
                        }
                    )
                finally:
                    page.close()
        finally:
            browser.close()
    return results


def publish_assets_to_branch(
    files_map: Dict[str, str],
    branch: str = ASSETS_BRANCH,
    commit_message: str = "chore: update issue/PR visual preview screenshots",
    repo: Optional[str] = None,
    repo_root: str = ".",
) -> Dict[str, str]:
    """Commit and push screenshot files to an isolated orphan `agent-assets` branch.

    Returns a mapping from logical asset key -> `https://raw.githubusercontent.com/...` URL.
    """
    if branch in ("main", "master"):
        raise ValueError(f"Refusing to publish screenshot assets to protected branch '{branch}'.")

    target_repo = repo or agent_backlog.detect_repo_slug()
    wt_dir = os.path.abspath(os.path.join(repo_root, "scratch", "worktrees", branch))

    subprocess.run(
        ["git", "fetch", "origin", branch],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if os.path.exists(wt_dir):
        subprocess.run(
            ["git", "worktree", "remove", "--force", wt_dir],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    subprocess.run(["git", "worktree", "prune"], cwd=repo_root, text=True, capture_output=True, check=False)
    os.makedirs(os.path.dirname(wt_dir), exist_ok=True)

    remote_exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"origin/{branch}"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    ).returncode == 0
    local_exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", branch],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    ).returncode == 0

    try:
        if remote_exists:
            subprocess.run(
                ["git", "worktree", "add", "-B", branch, wt_dir, f"origin/{branch}"],
                cwd=repo_root,
                check=True,
            )
        elif local_exists:
            subprocess.run(
                ["git", "worktree", "add", wt_dir, branch],
                cwd=repo_root,
                check=True,
            )
        else:
            subprocess.run(
                ["git", "worktree", "add", "--orphan", "-b", branch, wt_dir],
                cwd=repo_root,
                check=True,
            )

        urls: Dict[str, str] = {}
        for dest_rel, src_path in files_map.items():
            clean_rel = dest_rel.strip().lstrip("/").replace("\\", "/")
            dest_abs = os.path.join(wt_dir, clean_rel)
            os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
            shutil.copy2(src_path, dest_abs)
            urls[clean_rel] = f"https://raw.githubusercontent.com/{target_repo}/{branch}/{clean_rel}"

        subprocess.run(["git", "add", "."], cwd=wt_dir, check=True)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=wt_dir,
            text=True,
            capture_output=True,
            check=True,
        )
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_message], cwd=wt_dir, check=True)
        subprocess.run(["git", "push", "-u", "origin", f"{branch}:{branch}"], cwd=wt_dir, check=True)
        return urls
    finally:
        if os.path.exists(wt_dir):
            subprocess.run(
                ["git", "worktree", "remove", "--force", wt_dir],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
            subprocess.run(["git", "worktree", "prune"], cwd=repo_root, text=True, capture_output=True, check=False)


def render_val_modal_screenshots(
    output_dir: str,
    ref: Optional[str] = None,
    name_prefix: str = "val-modal",
    player_name: str = "RJ Davis",
    team_info: str = "North Carolina • #4 G",
    stats: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Capture Light & Dark mode screenshots of `renderValBreakdownHtml` at a given git ref."""
    sample_details = stats or {
        "pts": 26,
        "fg": {"m": 9, "a": 17},
        "threePt": {"m": 4, "a": 8},
        "ft": {"m": 4, "a": 5},
        "reb": 4,
        "ast": 6,
        "stl": 2,
        "blk": 0,
        "tov": 2,
        "total": 34,
    }
    css_text = read_file_from_ref("site_ui/styles.css", ref=ref)
    helpers_js = read_file_from_ref("site_ui/helpers.js", ref=ref)
    body_html = (
        '<div class="modal-box val-formula-modal-box val-breakdown-modal-box" '
        'style="position:relative; max-width:560px; width:100%;">'
        '<div id="val-modal-body" class="val-formula-content"></div>'
        "</div>"
    )
    inline_script = (
        f"const details = {json.dumps(sample_details)};\n"
        f"const html = renderValBreakdownHtml(details, {json.dumps(player_name)}, {json.dumps(team_info)});\n"
        "document.getElementById('val-modal-body').innerHTML = html;\n"
    )
    return capture_html_screenshots(
        body_html=body_html,
        output_dir=output_dir,
        name_prefix=name_prefix,
        css_text=css_text,
        helpers_js=helpers_js,
        inline_script=inline_script,
        viewport=(760, 960),
        capture_dark_mode=True,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture Light/Dark Playwright UI screenshots for Issues & PRs")
    sub = parser.add_subparsers(dest="command", required=True)

    val_p = sub.add_parser("val-modal", help="Render Player VAL Breakdown modal from a git ref or working tree")
    val_p.add_argument("--ref", default=None, help="Git ref (e.g. origin/main, agent/issue-2); defaults to working tree")
    val_p.add_argument("--out-dir", default="scratch/screenshots")
    val_p.add_argument("--prefix", default="val-modal")

    custom_p = sub.add_parser("custom", help="Render an HTML snippet file using site_ui/styles.css")
    custom_p.add_argument("--html-file", required=True)
    custom_p.add_argument("--ref", default=None)
    custom_p.add_argument("--out-dir", default="scratch/screenshots")
    custom_p.add_argument("--prefix", default="preview")

    pub_p = sub.add_parser("publish", help="Upload local PNG files to the isolated agent-assets branch")
    pub_p.add_argument("--branch", default=ASSETS_BRANCH)
    pub_p.add_argument("--message", default="chore: update issue/PR visual preview screenshots")
    pub_p.add_argument("mappings", nargs="+", help="dest/rel/path.png=local/path.png pairs")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "val-modal":
        shots = render_val_modal_screenshots(
            output_dir=args.out_dir,
            ref=args.ref,
            name_prefix=args.prefix,
        )
        print(json.dumps(shots, indent=2))
        return 0

    if args.command == "custom":
        with open(args.html_file, "r", encoding="utf-8") as f:
            body_html = f.read()
        css_text = read_file_from_ref("site_ui/styles.css", ref=args.ref)
        shots = capture_html_screenshots(
            body_html=body_html,
            output_dir=args.out_dir,
            name_prefix=args.prefix,
            css_text=css_text,
        )
        print(json.dumps(shots, indent=2))
        return 0

    if args.command == "publish":
        files_map: Dict[str, str] = {}
        for item in args.mappings:
            if "=" not in item:
                raise ValueError(f"Expected dest_rel=local_path, got '{item}'")
            dest_rel, local_path = item.split("=", 1)
            files_map[dest_rel.strip()] = local_path.strip()
        urls = publish_assets_to_branch(
            files_map=files_map,
            branch=args.branch,
            commit_message=args.message,
        )
        print(json.dumps(urls, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
