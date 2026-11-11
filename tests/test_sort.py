# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SARCycle
"""Tests for wms_capabilities_sorter. Run from the repository root with:

    python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wms_capabilities_sorter as wcs  # noqa: E402

NS = {"wms": "http://www.opengis.net/wms"}

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0"
    xmlns="http://www.opengis.net/wms"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/wms http://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd">
  <Service>
    <Name>WMS</Name>
    <Title>Test service</Title>
    <OnlineResource xlink:type="simple" xlink:href="https://example.com/wms"/>
  </Service>
  <Capability>
    <Exception>
      <Format>XML</Format>
    </Exception>
    <Layer>
      <Title>Root</Title>
      <CRS>EPSG:2056</CRS>
      <Layer><Name>z</Name><Title>zebra</Title></Layer>
      <Layer><Name>ae</Name><Title>Äpfel</Title></Layer>
      <Layer><Name>b</Name><Title>Birnen</Title></Layer>
      <Layer><Name>num</Name><Title>112 Festnetz</Title></Layer>
      <Layer><Name>a</Name><Title>armee</Title></Layer>
      <Layer>
        <Title>Gruppe</Title>
        <Abstract>Group abstract</Abstract>
        <Layer><Name>g2</Name><Title>Zweite</Title></Layer>
        <Layer><Name>g1</Name><Title>Erste</Title></Layer>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
""".encode("utf-8")

SERVICE_EXCEPTION = b"""<?xml version="1.0" encoding="UTF-8"?>
<ServiceExceptionReport version="1.3.0" xmlns="http://www.opengis.net/ogc">
  <ServiceException>Something went wrong</ServiceException>
</ServiceExceptionReport>
"""

WMS_111 = b"""<?xml version="1.0" encoding="UTF-8"?>
<WMT_MS_Capabilities version="1.1.1">
  <Capability><Layer><Title>Root</Title></Layer></Capability>
</WMT_MS_Capabilities>
"""


def child_layer_titles(layer):
    return [child.find("wms:Title", NS).text for child in layer.findall("wms:Layer", NS)]


def local_names(element):
    return [child.tag.split("}", 1)[1] for child in element]


class SortCapabilitiesTest(unittest.TestCase):
    def setUp(self):
        self.result = wcs.sort_capabilities(SAMPLE)
        self.root = ET.fromstring(self.result)
        self.root_layer = self.root.find("wms:Capability/wms:Layer", NS)

    def test_top_level_layers_sorted_by_title(self):
        self.assertEqual(
            child_layer_titles(self.root_layer),
            ["112 Festnetz", "Äpfel", "armee", "Birnen", "Gruppe", "zebra"],
        )

    def test_numeric_titles_sort_first(self):
        self.assertEqual(child_layer_titles(self.root_layer)[0], "112 Festnetz")

    def test_umlaut_sorts_with_base_letter(self):
        titles = child_layer_titles(self.root_layer)
        self.assertLess(titles.index("Äpfel"), titles.index("Birnen"))

    def test_sorting_is_case_insensitive(self):
        titles = child_layer_titles(self.root_layer)
        self.assertLess(titles.index("armee"), titles.index("Birnen"))

    def test_nested_layers_sorted(self):
        group = [
            layer
            for layer in self.root_layer.findall("wms:Layer", NS)
            if layer.find("wms:Title", NS).text == "Gruppe"
        ][0]
        self.assertEqual(child_layer_titles(group), ["Erste", "Zweite"])

    def test_non_layer_elements_keep_order(self):
        self.assertEqual(
            local_names(self.root_layer), ["Title", "CRS"] + ["Layer"] * 6
        )
        group = self.root_layer.findall("wms:Layer", NS)[4]
        self.assertEqual(local_names(group), ["Title", "Abstract", "Layer", "Layer"])

    def test_namespaces_preserved(self):
        self.assertNotIn(b"ns0:", self.result)
        self.assertIn(b'xmlns="http://www.opengis.net/wms"', self.result)
        self.assertIn(b"xlink:href", self.result)
        self.assertIn(b"xsi:schemaLocation", self.result)

    def test_output_has_xml_declaration(self):
        self.assertTrue(self.result.startswith(b"<?xml"))


class InvalidInputTest(unittest.TestCase):
    def test_service_exception_raises(self):
        with self.assertRaises(wcs.CapabilitiesError):
            wcs.sort_capabilities(SERVICE_EXCEPTION)

    def test_wms_111_raises(self):
        with self.assertRaises(wcs.CapabilitiesError):
            wcs.sort_capabilities(WMS_111)

    def test_malformed_xml_raises(self):
        with self.assertRaises(wcs.CapabilitiesError):
            wcs.sort_capabilities(b"<html><body>not closed")


class MainTest(unittest.TestCase):
    """End-to-end tests using file:// URLs, so no network is needed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.output = self.tmp / "out.xml"

    def write_source(self, content):
        source = self.tmp / "source.xml"
        source.write_bytes(content)
        return source.as_uri()

    def run_main(self, url):
        with contextlib.redirect_stderr(io.StringIO()):
            return wcs.main(["--url", url, "--output", str(self.output)])

    def test_success_writes_sorted_output(self):
        self.assertEqual(self.run_main(self.write_source(SAMPLE)), 0)
        root = ET.fromstring(self.output.read_bytes())
        root_layer = root.find("wms:Capability/wms:Layer", NS)
        self.assertEqual(child_layer_titles(root_layer)[0], "112 Festnetz")

    def test_failure_keeps_existing_output(self):
        self.output.write_bytes(b"old content")
        self.assertEqual(self.run_main(self.write_source(SERVICE_EXCEPTION)), 1)
        self.assertEqual(self.output.read_bytes(), b"old content")
        self.assertEqual(sorted(os.listdir(self.tmp)), ["out.xml", "source.xml"])

    @unittest.skipIf(os.name != "posix", "file modes are POSIX-specific")
    def test_output_is_world_readable(self):
        self.assertEqual(self.run_main(self.write_source(SAMPLE)), 0)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
