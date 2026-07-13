from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token


POSITIONING_LINE = "Student developer exploring AI, algorithms & macOS apps."
CHINESE_IDENTITY_LINE = "你好，我在把好奇心做成可以运行的东西。"
PROFILE_URL = "https://github.com/Izumi-iii"
EMAIL_URL = "mailto:depressing113@foxmail.com"
SNAKE_DARK_URL = (
    "https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/"
    "output/contribution-snake-dark.svg"
)
SNAKE_LIGHT_URL = (
    "https://raw.githubusercontent.com/Izumi-iii/Izumi-iii/"
    "output/contribution-snake.svg"
)
FEATURED_SECTION = "03 // FEATURED BUILDS"
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
REQUIRED_LOCAL_IMAGES = {
    "assets/brand/izumi-builder.svg": "IZUMI // BUILDER neon pixel logo",
    "assets/hero/miku-idle.gif": "Pixel-art Hatsune Miku gently idling",
    "assets/brand/current-quest.svg": (
        "Current quests rotate through SwiftUI, computer vision, algorithms, "
        "and building experiments"
    ),
    "assets/generated/profile-stats.svg": (
        "Izumi's current GitHub activity statistics"
    ),
    "assets/generated/languages.svg": (
        "Languages used across Izumi's public repositories"
    ),
    "assets/generated/projects.svg": (
        "Live stars and update dates for Izumi's featured repositories"
    ),
    "assets/generated/last-sync.svg": "Last successful automated profile update",
}

MARKDOWN = MarkdownIt("commonmark", {"html": True})


@dataclass(frozen=True)
class Heading:
    start: int
    end: int
    level: int
    tag: str
    text: str
    direct_link: tuple[str, str] | None


class ReadmeHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict[str, str | None]] = []
        self.sources: list[dict[str, str | None]] = []
        self.links: list[str] = []
        self.paragraphs: list[str] = []
        self.pictures: list[list[tuple[str, dict[str, str | None]]]] = []
        self.duplicate_attributes: list[tuple[str, str]] = []
        self._paragraph_parts: list[str] | None = None
        self._paragraph_depth = 0
        self._picture: list[tuple[str, dict[str, str | None]]] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attribute_names = [name for name, _ in attrs]
        self.duplicate_attributes.extend(
            (tag, name)
            for name, count in Counter(attribute_names).items()
            if count > 1
        )
        attributes = dict(attrs)
        if tag == "p":
            if self._paragraph_parts is None:
                self._paragraph_parts = []
            self._paragraph_depth += 1
        elif tag == "picture":
            self._picture = []
        elif tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"] or "")

        if tag == "img":
            self.images.append(attributes)
        elif tag == "source":
            self.sources.append(attributes)
        if self._picture is not None and tag in {"img", "source"}:
            self._picture.append((tag, attributes))

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._paragraph_parts is not None:
            self._paragraph_depth -= 1
            if self._paragraph_depth == 0:
                self.paragraphs.append(_normalize_text("".join(self._paragraph_parts)))
                self._paragraph_parts = None
        elif tag == "picture" and self._picture is not None:
            self.pictures.append(self._picture)
            self._picture = None

    def handle_data(self, data: str) -> None:
        if self._paragraph_parts is not None:
            self._paragraph_parts.append(data)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _render_inline(children: list[Token]) -> str:
    parts: list[str] = []
    for child in children:
        if child.type == "text":
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
    return _normalize_text("".join(parts))


def _inline_links(children: list[Token]) -> tuple[str, ...]:
    return tuple(
        href
        for child in children
        if child.type == "link_open"
        if (href := child.attrGet("href")) is not None
    )


def _direct_inline_link(children: list[Token]) -> tuple[str, str] | None:
    if (
        len(children) < 2
        or children[0].type != "link_open"
        or children[-1].type != "link_close"
        or sum(child.type == "link_open" for child in children) != 1
        or sum(child.type == "link_close" for child in children) != 1
    ):
        return None
    href = children[0].attrGet("href")
    if href is None:
        return None
    return href, _render_inline(children[1:-1])


def _headings(tokens: list[Token]) -> list[Heading]:
    headings: list[Heading] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 2 >= len(tokens):
            continue
        inline = tokens[index + 1]
        close = tokens[index + 2]
        if inline.type != "inline" or close.type != "heading_close":
            continue
        children = inline.children or []
        headings.append(
            Heading(
                start=index,
                end=index + 2,
                level=token.level,
                tag=token.tag,
                text=_render_inline(children),
                direct_link=_direct_inline_link(children),
            )
        )
    return headings


def _paragraph_after(tokens: list[Token], heading: Heading) -> str | None:
    index = heading.end + 1
    if index + 2 >= len(tokens):
        return None
    opening = tokens[index]
    inline = tokens[index + 1]
    closing = tokens[index + 2]
    if (
        opening.type != "paragraph_open"
        or opening.level != heading.level
        or inline.type != "inline"
        or closing.type != "paragraph_close"
    ):
        return None
    return _render_inline(inline.children or [])


def _validate_project_fallbacks(tokens: list[Token]) -> list[str]:
    errors: list[str] = []
    headings = _headings(tokens)
    sections = [
        heading
        for heading in headings
        if heading.level == 0
        and heading.tag == "h2"
        and heading.text == FEATURED_SECTION
    ]
    if len(sections) != 1:
        errors.append(f"missing or duplicate featured builds section: {FEATURED_SECTION}")
        project_headings: list[Heading] = []
    else:
        section = sections[0]
        section_end = next(
            (
                heading.start
                for heading in headings
                if heading.start > section.start
                and heading.level == section.level
                and heading.tag == "h2"
            ),
            len(tokens),
        )
        project_headings = [
            heading
            for heading in headings
            if section.end < heading.start < section_end
            and heading.level == section.level
            and heading.tag == "h3"
        ]

    actual_links = [
        heading.direct_link[0] if heading.direct_link is not None else ""
        for heading in project_headings
    ]
    expected_links = [url for _, url, _ in PROJECTS]
    for name, url, description in PROJECTS:
        matching = [
            heading
            for heading in project_headings
            if heading.direct_link == (url, name)
        ]
        if len(matching) != 1:
            errors.append(
                f"missing or duplicate {name} project fallback Markdown heading/link: {url}"
            )
            continue
        if _paragraph_after(tokens, matching[0]) != description:
            errors.append(f"missing exact {name} project description: {description}")

    if all(actual_links.count(url) == 1 for url in expected_links):
        if actual_links != expected_links:
            errors.append("featured project fallbacks are out of order")
    return errors


def _feed_rendered_html(tokens: list[Token]) -> ReadmeHTMLParser:
    parser = ReadmeHTMLParser()
    for token in tokens:
        if token.type == "html_block":
            parser.feed(token.content)
        elif token.type == "inline":
            for child in token.children or []:
                if child.type == "html_inline":
                    parser.feed(child.content)
    parser.close()
    return parser


def _markdown_paragraphs(tokens: list[Token]) -> list[str]:
    return [
        _render_inline(tokens[index + 1].children or [])
        for index, token in enumerate(tokens[:-1])
        if token.type == "paragraph_open"
        and tokens[index + 1].type == "inline"
    ]


def _markdown_links(tokens: list[Token]) -> list[str]:
    return [
        href
        for token in tokens
        if token.type == "inline"
        for href in _inline_links(token.children or [])
    ]


def _markdown_images(tokens: list[Token]) -> list[tuple[str, str]]:
    images: list[tuple[str, str]] = []
    for token in tokens:
        if token.type != "inline":
            continue
        for child in token.children or []:
            if child.type != "image":
                continue
            source = child.attrGet("src") or ""
            if child.children is None:
                alt = _normalize_text(child.content)
            else:
                alt = _render_inline(child.children)
            images.append((source, alt))
    return images


def _is_remote(reference: str) -> bool:
    return reference.startswith(("http://", "https://", "data:"))


def _validate_image_reference(reference: str, root: Path, errors: list[str]) -> None:
    if _is_remote(reference):
        return
    resolved_root = root.resolve()
    try:
        resolved_reference = (resolved_root / reference).resolve()
        resolved_reference.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        errors.append(f"local image escapes repository root: {reference}")
        return
    if not resolved_reference.is_file():
        errors.append(f"missing local image: {reference}")


def _validate_local_image_manifest(
    html: ReadmeHTMLParser,
    markdown_images: list[tuple[str, str]],
    errors: list[str],
) -> None:
    rendered = [
        (image.get("src") or "", (image.get("alt") or "").strip())
        for image in html.images
    ]
    rendered.extend(markdown_images)
    local = [(source, alt) for source, alt in rendered if not _is_remote(source)]
    counts = Counter(local)
    for source, alt in REQUIRED_LOCAL_IMAGES.items():
        if counts[(source, alt)] != 1:
            errors.append(
                "local image manifest requires exactly one "
                f"{source} with alt text: {alt}"
            )
    unexpected = sorted(
        (source, alt)
        for source, alt in local
        if (source, alt) not in {
            (required_source, required_alt)
            for required_source, required_alt in REQUIRED_LOCAL_IMAGES.items()
        }
    )
    for source, alt in unexpected:
        errors.append(
            f"unexpected local image in manifest: {source} (alt: {alt or '<empty>'})"
        )


def _srcset_references(srcset: str) -> list[str]:
    return [
        candidate.strip().split()[0]
        for candidate in srcset.split(",")
        if candidate.strip()
    ]


def _has_stable_snake_picture(parser: ReadmeHTMLParser) -> bool:
    for picture in parser.pictures:
        if len(picture) != 3:
            continue
        dark_tag, dark = picture[0]
        light_tag, light = picture[1]
        image_tag, image = picture[2]
        if (
            dark_tag == "source"
            and dark.get("media") == "(prefers-color-scheme: dark)"
            and dark.get("srcset") == SNAKE_DARK_URL
            and light_tag == "source"
            and light.get("media") == "(prefers-color-scheme: light)"
            and light.get("srcset") == SNAKE_LIGHT_URL
            and image_tag == "img"
            and image.get("src") == SNAKE_LIGHT_URL
        ):
            return True
    return False


def validate_readme(path: Path, root: Path) -> list[str]:
    if not path.exists():
        return ["README.md does not exist"]

    tokens = MARKDOWN.parse(path.read_text(encoding="utf-8"))
    html = _feed_rendered_html(tokens)
    errors = _validate_project_fallbacks(tokens)
    errors.extend(
        f"duplicate HTML attribute on <{tag}>: {attribute}"
        for tag, attribute in html.duplicate_attributes
    )

    paragraphs = html.paragraphs + _markdown_paragraphs(tokens)
    if paragraphs.count(CHINESE_IDENTITY_LINE) != 1:
        errors.append("Chinese identity line must appear exactly once")
    if paragraphs.count(POSITIONING_LINE) != 1:
        errors.append(f"missing rendered positioning line: {POSITIONING_LINE}")

    link_targets = html.links + _markdown_links(tokens)
    if link_targets.count(PROFILE_URL) != 2:
        errors.append(f"missing GitHub profile link: {PROFILE_URL}")
    if link_targets.count(EMAIL_URL) != 2:
        errors.append(f"missing email link: {EMAIL_URL}")

    if not _has_stable_snake_picture(html):
        errors.append("missing exact stable contribution snake picture")

    markdown_images = _markdown_images(tokens)
    _validate_local_image_manifest(html, markdown_images, errors)
    image_alts = [(image.get("alt") or "").strip() for image in html.images]
    image_alts.extend(alt for _, alt in markdown_images)
    if not any("IZUMI // BUILDER" in alt for alt in image_alts):
        errors.append("missing accessible identity title fallback: IZUMI // BUILDER")

    for image in html.images:
        reference = image.get("src")
        if not reference:
            errors.append("image has no src attribute")
        else:
            _validate_image_reference(reference, root, errors)
        if not (image.get("alt") or "").strip():
            errors.append(f"image has no alt text: {reference or '<missing src>'}")

    for source in html.sources:
        for reference in _srcset_references(source.get("srcset") or ""):
            _validate_image_reference(reference, root, errors)

    for reference, alt in markdown_images:
        if not reference:
            errors.append("Markdown image has no src attribute")
        else:
            _validate_image_reference(reference, root, errors)
        if not alt:
            errors.append(
                f"Markdown image has no alt text: {reference or '<missing src>'}"
            )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=Path("README.md"))
    args = parser.parse_args()
    errors = validate_readme(args.path, Path("."))
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
