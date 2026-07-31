"""Local software inventory collector: the `cpegen inventory` subcommand.

Python port of the original R prototype (net.security `inventary.R`, later
`mitre` package, cpe branch, `inst/scripts/inventory.R`): extract a curated
list of installed software (name, version, vendor) from the local machine
and write a titles CSV directly consumable by `cpegen run`.

Sources:
- Windows: the Uninstall registry keys read natively with `winreg`
  (HKLM 64-bit, HKLM WOW6432Node and HKCU). Unlike the R original, we do
  NOT query Win32_Product: enumerating it is slow and triggers MSI
  consistency repairs as a side effect.
- Linux: `dpkg-query` (Debian/Ubuntu) or `rpm -qa` (RHEL/Fedora/SUSE).

Curation: drop empty names, deduplicate, and (by default) filter obvious
non-software inventory noise - KB updates, hotfixes, language packs -
which the 2023 analysis identified as a driver of the giant M3 bucket.
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Noise patterns: rows matching any of these are dropped unless --keep-noise.
NOISE_PATTERNS = [
    re.compile(r"\bkb\s?\d{6,}\b", re.IGNORECASE),          # Windows KB updates
    re.compile(r"^(security |cumulative )?update for\b", re.IGNORECASE),
    re.compile(r"\bhotfix\b", re.IGNORECASE),
    re.compile(r"\blanguage pack\b", re.IGNORECASE),
    re.compile(r"^microsoft \.net.*targeting pack\b", re.IGNORECASE),
    re.compile(r"^windows software development kit\b", re.IGNORECASE),
]


@dataclass
class InventoryItem:
    """One installed software entry, as raw as the source provides it."""

    name: str
    version: str = ""
    vendor: str = ""
    source: str = ""  # hklm64 | hklm32 | hkcu | dpkg | rpm

    @property
    def title(self) -> str:
        """Free-text title for the pipeline: name plus version when the
        name does not already carry it (SCCM-style)."""
        if self.version and self.version not in self.name:
            return f"{self.name} {self.version}"
        return self.name


def is_noise(item: InventoryItem) -> bool:
    return any(p.search(item.name) for p in NOISE_PATTERNS)


def curate(items: list[InventoryItem], keep_noise: bool = False) -> list[InventoryItem]:
    """Deduplicate, drop empties and (optionally) filter noise."""
    seen: set[tuple[str, str]] = set()
    out: list[InventoryItem] = []
    for item in items:
        name = item.name.strip()
        if not name:
            continue
        key = (name.lower(), item.version.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        if not keep_noise and is_noise(item):
            continue
        out.append(InventoryItem(name=name, version=item.version.strip(),
                                 vendor=item.vendor.strip(), source=item.source))
    out.sort(key=lambda x: x.name.lower())
    return out


# ------------------------------------------------------------------ windows

def collect_windows() -> list[InventoryItem]:
    """Read the three Uninstall registry locations natively."""
    import winreg  # stdlib, Windows only

    locations = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "hklm64"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "hklm32"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "hkcu"),
    ]
    items: list[InventoryItem] = []
    for hive, path, source in locations:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with root:
            n_subkeys = winreg.QueryInfoKey(root)[0]
            for i in range(n_subkeys):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as sub:
                        def val(name: str) -> str:
                            try:
                                v = winreg.QueryValueEx(sub, name)[0]
                                return str(v).strip()
                            except OSError:
                                return ""
                        # system components are not user-facing software
                        if val("SystemComponent") == "1":
                            continue
                        name = val("DisplayName")
                        if name:
                            items.append(InventoryItem(
                                name=name,
                                version=val("DisplayVersion"),
                                vendor=val("Publisher"),
                                source=source,
                            ))
                except OSError:
                    continue
    return items


# -------------------------------------------------------------------- linux

def parse_dpkg_output(text: str) -> list[InventoryItem]:
    """Parse `dpkg-query -W -f='${Package}\\t${Version}\\t${Maintainer}\\n'`."""
    items = []
    for line in text.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        name = parts[0].split(":")[0]  # strip :amd64 architecture suffix
        items.append(InventoryItem(
            name=name,
            version=parts[1].strip() if len(parts) > 1 else "",
            vendor=parts[2].strip() if len(parts) > 2 else "",
            source="dpkg",
        ))
    return items


def parse_rpm_output(text: str) -> list[InventoryItem]:
    """Parse `rpm -qa --qf '%{NAME}\\t%{VERSION}-%{RELEASE}\\t%{VENDOR}\\n'`."""
    items = []
    for line in text.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        items.append(InventoryItem(
            name=parts[0].strip(),
            version=parts[1].strip() if len(parts) > 1 else "",
            vendor=parts[2].strip() if len(parts) > 2 else "",
            source="rpm",
        ))
    return items


def collect_linux() -> list[InventoryItem]:
    if shutil.which("dpkg-query"):
        out = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Maintainer}\n"],
            capture_output=True, text=True, check=True)
        return parse_dpkg_output(out.stdout)
    if shutil.which("rpm"):
        out = subprocess.run(
            ["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{VENDOR}\n"],
            capture_output=True, text=True, check=True)
        return parse_rpm_output(out.stdout)
    raise RuntimeError("no supported package manager found (dpkg-query or rpm)")


# ------------------------------------------------------------------- driver

def collect(keep_noise: bool = False) -> list[InventoryItem]:
    """Collect and curate the local software inventory."""
    if sys.platform.startswith("win"):
        items = collect_windows()
    elif sys.platform.startswith("linux"):
        items = collect_linux()
    else:
        raise RuntimeError(
            f"unsupported platform {sys.platform!r}: only Windows and Linux "
            "(same coverage as the original inventory.R)")
    return curate(items, keep_noise=keep_noise)


def write_csv(items: list[InventoryItem], path: Path) -> None:
    """Write the inventory CSV: `title` first (what `cpegen run` reads),
    then the raw fields for traceability."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["title", "name", "version", "vendor", "source"])
        for item in items:
            writer.writerow([item.title, item.name, item.version,
                             item.vendor, item.source])
