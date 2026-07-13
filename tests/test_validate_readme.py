from pathlib import Path
import re
import shutil

import pytest

from scripts.validate_readme import validate_readme


PROJECTS = (
    (
        "magicState",
        "https://github.com/Izumi-iii/magicState",
        "An application-development experiment focused on turning ideas into an interactive product.",
    ),
    (
        "downing_detect",
        "https://github.com/Izumi-iii/downing_detect",
        "A Python computer-vision project using YOLO to detect potential drowning risk in video streams.",
    ),
    (
        "Algorithm",
        "https://github.com/Izumi-iii/Algorithm",
        "A growing C++ log of algorithm practice, problem-solving patterns, and implementation notes.",
    ),
)


def readme_text() -> str:
    return Path("README.md").read_text(encoding="utf-8")


def validate_text(tmp_path: Path, text: str, root: Path = Path(".")) -> list[str]:
    readme = tmp_path / "README.md"
    readme.write_text(text, encoding="utf-8")
    return validate_readme(readme, root)


def project_block(name: str, url: str, description: str) -> str:
    return f"### [<code>{name}</code>]({url})\n\n{description}"


def project_fallback_markdown() -> str:
    blocks = "\n\n".join(project_block(*project) for project in PROJECTS)
    return f"## <code>03 // FEATURED BUILDS</code>\n\n{blocks}"


def required_html() -> str:
    return """\
<p><strong>Student developer exploring AI, algorithms &amp; macOS apps.</strong></p>
<p>你好，我在把好奇心做成可以运行的东西。</p>
<a href="https://github.com/Izumi-iii">GitHub</a>
<a href="mailto:depressing113@foxmail.com">Email</a>
<img src="https://example.com/logo.svg" alt="IZUMI // BUILDER neon pixel logo" />
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake-dark.svg" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake.svg" />
  <img src="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake.svg" alt="Contribution snake" />
</picture>"""


def required_content_errors() -> set[str]:
    return {
        "Chinese identity line must appear exactly once",
        "missing rendered positioning line: Student developer exploring AI, algorithms & macOS apps.",
        "missing GitHub profile link: https://github.com/Izumi-iii",
        "missing email link: mailto:depressing113@foxmail.com",
        "missing exact stable contribution snake picture",
        "missing accessible identity title fallback: IZUMI // BUILDER",
    }


def validate_required_html_code(tmp_path: Path, code: str) -> list[str]:
    text = f"{project_fallback_markdown()}\n\n{code}\n"
    return validate_text(tmp_path, text)


def test_real_readme_has_required_fallback_content_and_assets():
    assert validate_readme(Path("README.md"), Path(".")) == []


def test_real_readme_has_exact_local_visual_manifest_and_footer_contacts():
    text = readme_text()
    expected_paths = {
        "assets/brand/izumi-builder.svg",
        "assets/brand/current-quest.svg",
        "assets/hero/miku-idle.gif",
        "assets/generated/profile-stats.svg",
        "assets/generated/languages.svg",
        "assets/generated/projects.svg",
        "assets/generated/last-sync.svg",
    }
    assert {
        match.group(1)
        for match in re.finditer(r'<img\s+[^>]*src="([^"]+)"', text)
        if match.group(1).startswith("assets/")
    } == expected_paths
    assert all(text.count(f'src="{path}"') == 1 for path in expected_paths)
    assert text.count('href="https://github.com/Izumi-iii"') == 2
    assert text.count('href="mailto:depressing113@foxmail.com"') == 2


@pytest.mark.parametrize(
    ("original", "duplicate"),
    (
        (
            '<a href="https://github.com/Izumi-iii">GitHub</a>',
            '<a href="https://example.com" href="https://github.com/Izumi-iii">GitHub</a>',
        ),
        (
            'src="assets/brand/izumi-builder.svg"',
            'src="assets/missing.svg" src="assets/brand/izumi-builder.svg"',
        ),
        (
            'alt="IZUMI // BUILDER neon pixel logo"',
            'alt="wrong" alt="IZUMI // BUILDER neon pixel logo"',
        ),
        (
            'media="(prefers-color-scheme: dark)"',
            'media="print" media="(prefers-color-scheme: dark)"',
        ),
        (
            'srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake-dark.svg"',
            'srcset="https://example.com/fake.svg" srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake-dark.svg"',
        ),
        (
            'width="760"',
            'width="1" width="760"',
        ),
    ),
)
def test_validator_rejects_duplicate_html_attributes(
    tmp_path, original, duplicate
):
    errors = validate_text(tmp_path, readme_text().replace(original, duplicate, 1))

    assert any("duplicate HTML attribute" in error for error in errors)


def test_validator_rejects_parent_traversal_image_even_when_target_exists(tmp_path):
    root = tmp_path / "profile"
    root.mkdir()
    outside = tmp_path / "outside.svg"
    outside.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    readme = root / "README.md"
    readme.write_text(
        readme_text().replace(
            "assets/brand/izumi-builder.svg", "../outside.svg", 1
        ),
        encoding="utf-8",
    )

    errors = validate_readme(readme, root)

    assert "local image escapes repository root: ../outside.svg" in errors


def test_validator_rejects_symlink_image_that_resolves_outside_root(tmp_path):
    root = tmp_path / "profile"
    asset = root / "assets" / "brand" / "izumi-builder.svg"
    asset.parent.mkdir(parents=True)
    outside = tmp_path / "outside.svg"
    outside.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    asset.symlink_to(outside)
    readme = root / "README.md"
    readme.write_text(readme_text(), encoding="utf-8")

    errors = validate_readme(readme, root)

    assert (
        "local image escapes repository root: assets/brand/izumi-builder.svg"
        in errors
    )


def test_validator_reports_missing_project_link(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("IZUMI // BUILDER")
    errors = validate_readme(readme, tmp_path)
    assert any("magicState" in error for error in errors)


def test_validator_requires_accessible_identity_title_fallback(tmp_path):
    text = readme_text().replace(
        'alt="IZUMI // BUILDER neon pixel logo"',
        'alt="Neon pixel logo"',
    )

    errors = validate_text(tmp_path, text)

    assert "missing accessible identity title fallback: IZUMI // BUILDER" in errors


def test_validator_rejects_project_url_in_non_link_text(tmp_path):
    name, url, description = PROJECTS[0]
    replacement = f"### `{name}`\n\n{url}\n\n{description}"
    text = readme_text().replace(project_block(name, url, description), replacement)

    errors = validate_text(tmp_path, text)

    assert any("magicState project fallback" in error for error in errors)


def test_validator_rejects_wrong_project_link_label(tmp_path):
    name, url, description = PROJECTS[0]
    replacement = f"### [wrong-name]({url})\n\n{description}"
    text = readme_text().replace(project_block(name, url, description), replacement)

    errors = validate_text(tmp_path, text)

    assert any("magicState project fallback" in error for error in errors)


def test_validator_rejects_empty_project_link_label(tmp_path):
    name, url, description = PROJECTS[0]
    replacement = f"### []({url})\n\n{description}"
    text = readme_text().replace(project_block(name, url, description), replacement)

    errors = validate_text(tmp_path, text)

    assert any("magicState project fallback" in error for error in errors)


def test_validator_rejects_extra_project_link_label_text(tmp_path):
    name, url, description = PROJECTS[0]
    replacement = f"### [{name} extra]({url})\n\n{description}"
    text = readme_text().replace(project_block(name, url, description), replacement)

    errors = validate_text(tmp_path, text)

    assert any("magicState project fallback" in error for error in errors)


def test_validator_rejects_image_only_project_link_label(tmp_path):
    name, url, description = PROJECTS[0]
    replacement = (
        f"### [![{name} project card](assets/generated/projects.svg)]({url})"
        f"\n\n{description}"
    )
    text = readme_text().replace(project_block(name, url, description), replacement)

    errors = validate_text(tmp_path, text)

    assert any("magicState project fallback" in error for error in errors)


def test_validator_rejects_project_fallback_hidden_in_comment_and_image(tmp_path):
    name, url, description = PROJECTS[0]
    replacement = (
        f"<!--\n{project_block(name, url, description)}\n-->\n\n"
        f"![{name} project card]({url})"
    )
    text = readme_text().replace(project_block(name, url, description), replacement)

    errors = validate_text(tmp_path, text)

    assert any("magicState project fallback" in error for error in errors)


def test_validator_does_not_use_code_inline_as_featured_section_label(tmp_path):
    text = readme_text().replace(
        "## <code>03 // FEATURED BUILDS</code>",
        "## `03 // FEATURED BUILDS`",
    )

    errors = validate_text(tmp_path, text)

    assert "missing or duplicate featured builds section: 03 // FEATURED BUILDS" in errors


def test_validator_rejects_featured_projects_out_of_order(tmp_path):
    first = project_block(*PROJECTS[0])
    second = project_block(*PROJECTS[1])
    text = readme_text().replace(first, "PROJECT_ONE").replace(second, first).replace("PROJECT_ONE", second)

    errors = validate_text(tmp_path, text)

    assert "featured project fallbacks are out of order" in errors


def test_validator_rejects_changed_project_description(tmp_path):
    name, url, description = PROJECTS[1]
    text = readme_text().replace(description, "A computer-vision experiment.")

    errors = validate_text(tmp_path, text)

    assert any("downing_detect project description" in error for error in errors)


@pytest.mark.parametrize(
    ("part", "indent", "expected_error"),
    (
        ("heading", "    ", "magicState project fallback"),
        ("heading", "\t", "magicState project fallback"),
        ("description", "    ", "magicState project description"),
        ("description", "\t", "magicState project description"),
    ),
)
def test_validator_rejects_code_indented_project_fallback_parts(
    tmp_path, part, indent, expected_error
):
    name, url, description = PROJECTS[0]
    heading = f"### [<code>{name}</code>]({url})"
    if part == "heading":
        replacement = f"{indent}{heading}\n\n{description}"
    else:
        replacement = f"{heading}\n\n{indent}{description}"
    text = readme_text().replace(project_block(name, url, description), replacement)

    errors = validate_text(tmp_path, text)

    assert any(expected_error in error for error in errors)


def test_validator_requires_actual_github_profile_link(tmp_path):
    text = readme_text().replace(
        '<a href="https://github.com/Izumi-iii">GitHub</a>',
        '<span data-url="https://github.com/Izumi-iii">GitHub</span>',
    )

    errors = validate_text(tmp_path, text)

    assert "missing GitHub profile link: https://github.com/Izumi-iii" in errors


def test_validator_requires_actual_email_link(tmp_path):
    text = readme_text().replace(
        '<a href="mailto:depressing113@foxmail.com">Email</a>',
        '<span data-contact="mailto:depressing113@foxmail.com">Email</span>',
    )

    errors = validate_text(tmp_path, text)

    assert "missing email link: mailto:depressing113@foxmail.com" in errors


def test_validator_rejects_duplicate_chinese_identity_line(tmp_path):
    chinese_line = "你好，我在把好奇心做成可以运行的东西。"
    text = readme_text().replace(f"<p>{chinese_line}</p>", f"<p>{chinese_line}</p>\n<p>{chinese_line}</p>")

    errors = validate_text(tmp_path, text)

    assert "Chinese identity line must appear exactly once" in errors


def test_validator_rejects_positioning_line_hidden_in_comment(tmp_path):
    text = re.sub(
        r"<p><strong>Student developer exploring AI, algorithms &(?:amp;)? macOS apps\.</strong></p>",
        "<!-- Student developer exploring AI, algorithms & macOS apps. -->",
        readme_text(),
    )

    errors = validate_text(tmp_path, text)

    assert "missing rendered positioning line: Student developer exploring AI, algorithms & macOS apps." in errors


@pytest.mark.parametrize("fence", ("```", "~~~~"))
def test_validator_ignores_required_html_inside_matching_fenced_code(tmp_path, fence):
    code = f"{fence}html\n{required_html()}\n{fence}"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


def test_validator_ignores_required_html_inside_repeated_blockquote_fence(tmp_path):
    prefix = "> > "
    body = "\n".join(f"{prefix}{line}" for line in required_html().splitlines())
    code = f"{prefix}```html\n{body}\n{prefix}```"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


@pytest.mark.parametrize("marker", ("-", "+", "*", "1.", "2)"))
def test_validator_ignores_required_html_inside_list_fence(tmp_path, marker):
    content_indent = " " * (len(marker) + 1)
    body = "\n".join(
        f"{content_indent}{line}" for line in required_html().splitlines()
    )
    code = f"{marker} ```html\n{body}\n{content_indent}```"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


def test_validator_ignores_required_html_inside_nested_quote_list_fence(tmp_path):
    body = "\n".join(f">   {line}" for line in required_html().splitlines())
    code = f"> - ```html\n{body}\n>   ```"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


def test_validator_ignores_required_html_after_over_indented_false_closer(tmp_path):
    body = "\n".join(f"  {line}" for line in required_html().splitlines())
    code = f"- ```html\n      ```\n{body}\n  ```"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


def test_validator_ignores_nested_quote_list_indented_code(tmp_path):
    body = "\n".join(f">       {line}" for line in required_html().splitlines())
    code = f"> - item\n>\n{body}"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


@pytest.mark.parametrize("indent", ("    ", "\t"))
def test_validator_ignores_required_html_inside_root_indented_code(tmp_path, indent):
    code = "\n".join(f"{indent}{line}" for line in required_html().splitlines())

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


def test_validator_accepts_longer_matching_fence_closer(tmp_path):
    code = f"```html\n{required_html()}\n`````"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


def test_validator_preserves_content_after_longer_matching_fence_closer(tmp_path):
    text = "```text\nmasked code\n`````\n" + readme_text()

    errors = validate_text(tmp_path, text)

    assert errors == []


@pytest.mark.parametrize(
    "ordinary_markdown",
    (
        "> Ordinary blockquote text.",
        "> > Nested blockquote text.",
        "- Ordinary bullet item.",
        "+ Another bullet item.",
        "1. Ordinary ordered item.",
    ),
)
def test_validator_leaves_ordinary_blockquotes_and_lists_visible(
    tmp_path, ordinary_markdown
):
    errors = validate_text(tmp_path, f"{readme_text()}\n{ordinary_markdown}\n")

    assert errors == []


def test_validator_ignores_fake_images_and_links_inside_four_backtick_fence(tmp_path):
    fake_code = """\
````html
<img src="assets/generated/missing-in-code.svg" alt="Fake HTML image" />
![Fake Markdown image](assets/generated/also-missing-in-code.svg)
<a href="https://example.com/not-a-profile">Fake link</a>
````"""
    errors = validate_text(tmp_path, f"{readme_text()}\n{fake_code}\n")

    assert errors == []


def test_validator_ignores_required_html_inside_inline_code(tmp_path):
    compact_html = " ".join(required_html().splitlines())
    code = f"`{compact_html}`"

    errors = validate_required_html_code(tmp_path, code)

    assert required_content_errors() <= set(errors)


def test_readme_uses_valid_escaped_html_for_positioning_line():
    assert "Student developer exploring AI, algorithms &amp; macOS apps." in readme_text()


@pytest.mark.parametrize(
    ("old_attribute", "new_attribute"),
    (
        (
            'srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake-dark.svg"',
            'srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/main/contribution-snake-dark.svg"',
        ),
        (
            'srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake.svg"',
            'srcset="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snek.svg"',
        ),
        (
            'src="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/output/contribution-snake.svg"',
            'src="https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/main/contribution-snake.svg"',
        ),
    ),
)
def test_validator_requires_exact_stable_snake_picture_attributes(
    tmp_path, old_attribute, new_attribute
):
    text = readme_text().replace(old_attribute, new_attribute)

    errors = validate_text(tmp_path, text)

    assert "missing exact stable contribution snake picture" in errors


def test_missing_generated_assets_preserve_recognized_project_fallbacks(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    readme = root / "README.md"
    readme.write_text(readme_text(), encoding="utf-8")
    for directory in ("brand", "hero"):
        shutil.copytree(Path("assets") / directory, root / "assets" / directory)

    errors = validate_readme(readme, root)

    missing_images = {error for error in errors if error.startswith("missing local image:")}
    assert missing_images == {
        "missing local image: assets/generated/profile-stats.svg",
        "missing local image: assets/generated/languages.svg",
        "missing local image: assets/generated/projects.svg",
        "missing local image: assets/generated/last-sync.svg",
    }
    assert not any("project fallback" in error or "project description" in error for error in errors)


def test_validator_parses_single_quoted_image_src(tmp_path):
    text = readme_text().replace(
        'src="assets/generated/projects.svg"',
        "src='assets/generated/not-there.svg'",
    )

    errors = validate_text(tmp_path, text)

    assert "missing local image: assets/generated/not-there.svg" in errors


def test_validator_accepts_single_quoted_nonempty_alt_text(tmp_path):
    text = readme_text().replace(
        'alt="IZUMI // BUILDER neon pixel logo"',
        "alt='IZUMI // BUILDER neon pixel logo'",
    )

    errors = validate_text(tmp_path, text)

    assert not any("image has no alt text" in error for error in errors)


def test_validator_checks_inline_markdown_image_paths(tmp_path):
    text = readme_text() + "\n![Generated preview](assets/generated/not-there.svg)\n"

    errors = validate_text(tmp_path, text)

    assert "missing local image: assets/generated/not-there.svg" in errors


def test_validator_validates_shortcut_reference_markdown_image(tmp_path):
    alt = "Izumi's current GitHub activity statistics"
    text = (
        readme_text().replace(
            '  <img src="assets/generated/profile-stats.svg" width="680" '
            f'alt="{alt}" />\n',
            "",
        )
        + f"\n![{alt}]\n\n"
        + f"[{alt}]: assets/generated/profile-stats.svg\n"
    )

    errors = validate_text(tmp_path, text)

    assert errors == []


@pytest.mark.parametrize(
    "reference_image",
    (
        "![Izumi's current GitHub activity statistics][]\n\n"
        "[Izumi's current GitHub activity statistics]: assets/generated/profile-stats.svg",
        "![Izumi's current GitHub activity statistics][preview]\n\n"
        "[preview]: assets/generated/profile-stats.svg",
    ),
)
def test_validator_validates_collapsed_and_full_reference_markdown_images(
    tmp_path, reference_image
):
    text = readme_text().replace(
        '  <img src="assets/generated/profile-stats.svg" width="680" '
        'alt="Izumi\'s current GitHub activity statistics" />\n',
        "",
    )
    errors = validate_text(tmp_path, f"{text}\n{reference_image}\n")

    assert errors == []


def test_validator_rejects_empty_alt_reference_markdown_image(tmp_path):
    reference_image = (
        "![][preview]\n\n[preview]: assets/generated/profile-stats.svg"
    )

    errors = validate_text(tmp_path, f"{readme_text()}\n{reference_image}\n")

    assert "Markdown image has no alt text: assets/generated/profile-stats.svg" in errors


@pytest.mark.parametrize(
    "reference_image",
    (
        "![Missing Preview]\n\n[Missing Preview]: assets/generated/not-there.svg",
        "![Missing Preview][]\n\n[Missing Preview]: assets/generated/not-there.svg",
        "![Missing Preview][preview]\n\n[preview]: assets/generated/not-there.svg",
    ),
)
def test_validator_checks_reference_markdown_image_paths(tmp_path, reference_image):
    errors = validate_text(tmp_path, f"{readme_text()}\n{reference_image}\n")

    assert "missing local image: assets/generated/not-there.svg" in errors
