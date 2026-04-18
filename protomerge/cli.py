from __future__ import annotations

"""
protomerge CLI — apply protocol extensions and output extended protocol XML.

Commands:
  apply     Fetch extensions, merge XML, output a ready-to-use protocol directory.
  validate  Check extensions.xml for merge conflicts without writing any files.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .merger import MergeError, merge_protocol_file, load_base_elements
from .models import Extension
from .sources import OFFICIAL_REPO, resolve, resolve_extension_files, fetch_base_protocol

app = typer.Typer(
    name="protomerge",
    help="Apply protocol extensions and output extended protocol XML.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

def parse_extensions_xml(config_path: Path) -> list[Extension]:
    """Parse extensions.xml and return a list of Extension objects."""
    try:
        tree = ET.parse(config_path)
    except (ET.ParseError, FileNotFoundError) as e:
        err_console.print(f"[red]Error:[/red] Cannot read {config_path}: {e}")
        raise typer.Exit(1)

    root = tree.getroot()
    if root.tag != "extensions":
        err_console.print(
            f"[red]Error:[/red] {config_path}: root element must be <extensions>"
        )
        raise typer.Exit(1)

    extensions: list[Extension] = []
    for el in root:
        if el.tag != "extension":
            continue
        ext_type = el.get("type")
        name = el.get("name")
        if not ext_type or not name:
            err_console.print(
                f"[red]Error:[/red] Each <extension> requires 'type' and 'name' attributes."
            )
            raise typer.Exit(1)
        extensions.append(Extension(
            type=ext_type,
            name=name,
            repo=el.get("repo"),
            ref=el.get("ref"),
            path=el.get("path"),
        ))
    return extensions


# ---------------------------------------------------------------------------
# XML output helpers
# ---------------------------------------------------------------------------

def _clean_element(el: ET.Element) -> ET.Element:
    """Return a copy of the element with internal tracking attributes removed."""
    clean = ET.Element(el.tag, {k: v for k, v in el.attrib.items() if not k.startswith("_eoext")})
    clean.text = el.text
    clean.tail = el.tail
    for child in el:
        clean.append(_clean_element(child))
    return clean


def _write_protocol_xml(output_file: Path, elements: list[ET.Element]) -> None:
    root = ET.Element("protocol")
    for el in elements:
        root.append(_clean_element(el))
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output_file, encoding="unicode", xml_declaration=False)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

@app.command()
def apply(
    config: Path = typer.Option(Path("extensions.xml"), "--config", "-c", help="Path to extensions.xml"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory (default: ./eo-protocol)"),
):
    """Fetch extensions, merge XML, and output extended protocol files."""

    console.rule("[bold]protomerge[/bold]")

    output_dir = output or Path("./eo-protocol")
    config_dir = config.parent.resolve()

    console.print(f"  [dim]Config[/dim]     {config}")
    console.print(f"  [dim]Output[/dim]     {output_dir}")
    console.print()

    if not config.exists():
        err_console.print(f"[red]Error:[/red] Config file not found: {config}")
        err_console.print("  Create an extensions.xml file or pass --config <path>.")
        raise typer.Exit(1)

    extensions = parse_extensions_xml(config)
    if not extensions:
        err_console.print("[yellow]Warning:[/yellow] No extensions defined in config. Nothing to do.")
        raise typer.Exit(0)

    ext_names = ", ".join(e.name for e in extensions)
    console.print(f"  [dim]Extensions[/dim] {ext_names}\n")

    # Resolve extension sources
    resolved_extensions = []
    with console.status("Fetching extension sources..."):
        for ext in extensions:
            try:
                resolved = resolve(ext, config_dir)
                resolved_extensions.append(resolved)
                repo_label = ext.repo or OFFICIAL_REPO
                ref_label = f" @ {ext.ref}" if ext.ref else ""
                console.print(f"  [green]✓[/green] {ext.name:<20} {repo_label if ext.type == 'git' else ext.path}{ref_label}")
            except ValueError as e:
                console.print(f"  [red]✗[/red] {ext.name}")
                err_console.print(f"\n[red]Error:[/red] {e}")
                raise typer.Exit(1)

    console.print()

    # Fetch base protocol
    with console.status("Fetching base eo-protocol..."):
        try:
            xml_root, base_files = fetch_base_protocol()
        except Exception as e:
            err_console.print(f"[red]Error:[/red] Failed to fetch base protocol: {e}")
            raise typer.Exit(1)

    console.print(f"  [green]✓[/green] Base protocol fetched ({len(base_files)} files)\n")

    # Build per-file element map
    file_elements: dict[Path, list[ET.Element]] = {}
    for f in base_files:
        rel = f.relative_to(xml_root)
        file_elements[rel] = load_base_elements([f])

    # Apply extensions
    console.print("  Applying extensions...")
    for resolved in resolved_extensions:
        ext_files = resolve_extension_files(resolved)
        ext_root = Path(resolved.local_path)
        try:
            for ext_file in ext_files:
                rel = ext_file.relative_to(ext_root)
                if rel not in file_elements:
                    file_elements[rel] = []
                result = merge_protocol_file(file_elements[rel], ext_file, resolved.name)
                console.print(f"  [green]✓[/green] {resolved.name:<20} {result.summary()}")
        except MergeError as e:
            console.print(f"  [red]✗[/red] {resolved.name:<20} merge error")
            err_console.print(f"\n[red]Error: Merge failed in extension '{resolved.name}'[/red]\n\n  {e}")
            raise typer.Exit(1)

    # Write output
    console.print()
    output_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, elements in file_elements.items():
        out_file = output_dir / rel_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        _write_protocol_xml(out_file, elements)

    console.print(f"  [bold green]Output:[/bold green] {output_dir}/")
    console.print()


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@app.command()
def validate(
    config: Path = typer.Option(Path("extensions.xml"), "--config", "-c", help="Path to extensions.xml"),
):
    """Fetch extensions and the base protocol, then dry-run merge to check for conflicts."""

    console.print("[bold]Validating extensions...[/bold]\n")

    if not config.exists():
        err_console.print(f"[red]Error:[/red] Config file not found: {config}")
        raise typer.Exit(1)

    config_dir = config.parent.resolve()
    extensions = parse_extensions_xml(config)

    # Resolve extension sources
    resolved_extensions = []
    for ext in extensions:
        try:
            resolved = resolve(ext, config_dir)
            resolved_extensions.append(resolved)
            console.print(f"  [green]✓[/green] {ext.name} — source resolved")
        except ValueError as e:
            console.print(f"  [red]✗[/red] {ext.name} — source error")
            err_console.print(f"\n[red]Error:[/red] {e}")
            raise typer.Exit(1)

    console.print()

    # Fetch base protocol
    with console.status("Fetching base eo-protocol..."):
        try:
            _, base_files = fetch_base_protocol()
        except Exception as e:
            err_console.print(f"[red]Error:[/red] Failed to fetch base protocol: {e}")
            raise typer.Exit(1)

    base_elements = load_base_elements(base_files)
    console.print(f"  [green]✓[/green] Base protocol loaded ({len(base_files)} files)\n")

    # Dry-run merge
    for resolved in resolved_extensions:
        ext_files = resolve_extension_files(resolved)
        ext_root = Path(resolved.local_path)
        try:
            for ext_file in ext_files:
                rel = ext_file.relative_to(ext_root)
                result = merge_protocol_file(base_elements, ext_file, resolved.name)
                label = f"{resolved.name}/{rel}"
                console.print(f"  [green]✓[/green] {label:<40} {result.summary()}")
        except MergeError as e:
            console.print(f"  [red]✗[/red] {resolved.name:<40} conflict")
            err_console.print(f"\n[red]Conflict:[/red] {e}")
            raise typer.Exit(1)

    console.print()
    console.print("[bold green]All extensions are valid — no conflicts detected.[/bold green]")


if __name__ == "__main__":
    app()
