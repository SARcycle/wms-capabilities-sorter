#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# wms_capabilities_sorter.py - sort the layers of a WMS 1.3.0
# GetCapabilities document by title
# Copyright (C) 2026 SARCycle
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
Download a WMS 1.3.0 GetCapabilities document, sort all <Layer> elements
by <Title> (recursively, at every level of the layer tree), and write the
result atomically to a file.

Compatible with Python 3.8+ (standard library only).
"""

import argparse
import io
import os
import sys
import tempfile
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

__version__ = "1.0.0"

WMS_NS = "http://www.opengis.net/wms"
CAPABILITIES_TAG = "{%s}WMS_Capabilities" % WMS_NS
CAPABILITY_TAG = "{%s}Capability" % WMS_NS
LAYER_TAG = "{%s}Layer" % WMS_NS
TITLE_TAG = "{%s}Title" % WMS_NS
USER_AGENT = "wms-capabilities-sorter/%s" % __version__


class CapabilitiesError(Exception):
    """The document is not a usable WMS 1.3.0 GetCapabilities response."""


def log(message):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("%s %s" % (stamp, message), file=sys.stderr)


def download(url, timeout):
    """Return the raw response body of ``url``."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        # HTTP responses have a status; file:// responses may report None
        status = getattr(response, "status", None)
        if status is not None and status != 200:
            raise CapabilitiesError("HTTP status %s" % status)
        return response.read()


def register_namespaces(data):
    """Register every namespace prefix declared in the document, so that
    ElementTree writes them back unchanged instead of ns0:, ns1:, ..."""
    for _event, (prefix, uri) in ET.iterparse(
        io.BytesIO(data), events=("start-ns",)
    ):
        ET.register_namespace(prefix, uri)


def sort_key(layer):
    """Case-insensitive key; umlauts and accents sort with their base
    letter (Ä with A, é with e). Layers without a title sort first."""
    title_elem = layer.find(TITLE_TAG)
    title = (title_elem.text or "") if title_elem is not None else ""
    decomposed = unicodedata.normalize("NFKD", title.strip())
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    return (base.casefold(), title)


def sort_layers(element):
    """Sort child <Layer> elements by title, recursively.

    Child layers are put back into the same positions (slots) that layers
    occupied before, so all other elements keep their schema-required
    order. Whitespace tails stay with the slot, which keeps the
    indentation tidy."""
    children = list(element)
    slots = [i for i, child in enumerate(children) if child.tag == LAYER_TAG]

    for i in slots:
        sort_layers(children[i])

    if len(slots) > 1:
        layers = [children[i] for i in slots]
        tails = [layer.tail for layer in layers]
        sorted_layers = sorted(layers, key=sort_key)
        for slot_index, layer, tail in zip(slots, sorted_layers, tails):
            layer.tail = tail
            element[slot_index] = layer


def sort_capabilities(data):
    """Take a GetCapabilities document as bytes and return the sorted
    document as UTF-8 encoded bytes, including an XML declaration."""
    try:
        register_namespaces(data)
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise CapabilitiesError("Response is not well-formed XML: %s" % exc) from exc

    if root.tag != CAPABILITIES_TAG:
        raise CapabilitiesError(
            "Unexpected root element %r; expected a WMS 1.3.0 "
            "WMS_Capabilities document (service exception or WMS 1.1.1?)"
            % root.tag
        )

    capability = root.find(CAPABILITY_TAG)
    if capability is None:
        raise CapabilitiesError("No <Capability> element found")
    if capability.find(".//" + LAYER_TAG) is None:
        raise CapabilitiesError("No <Layer> elements found")

    sort_layers(capability)

    buffer = io.BytesIO()
    ET.ElementTree(root).write(buffer, encoding="UTF-8", xml_declaration=True)
    return buffer.getvalue()


def write_atomically(content, path):
    """Write ``content`` to a temporary file in the target directory and
    rename it over ``path``, so readers never see a partial file."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(
        prefix=".wms_capabilities_sorter_", suffix=".xml", dir=directory
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        # mkstemp creates the file with mode 0600; a web server must read it
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="wms_capabilities_sorter.py",
        description=(
            "Download a WMS 1.3.0 GetCapabilities document, sort all layers "
            "by title and write the result atomically to a file."
        ),
    )
    parser.add_argument(
        "--url", required=True, help="full GetCapabilities URL of the WMS"
    )
    parser.add_argument(
        "--output", required=True, help="path of the sorted output file"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="download timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        data = download(args.url, args.timeout)
        content = sort_capabilities(data)
        write_atomically(content, args.output)
    except Exception as exc:  # noqa: BLE001 - log any failure, keep old file
        log("ERROR: %s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
