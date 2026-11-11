# wms-capabilities-sorter

Sorts the layers of any WMS 1.3.0 GetCapabilities document by title and
writes the result to a file, which a web server can then serve to clients
such as QGIS.

## Background

Since QGIS 4.2, the Browser panel lists WMS layers in the order of the
GetCapabilities document instead of alphabetically
(see [qgis/QGIS#67566](https://github.com/qgis/QGIS/issues/67566) and
[qgis/QGIS#62918](https://github.com/qgis/QGIS/issues/62918)).
For services with hundreds of layers, such as the [swisstopo WMS](https://www.geo.admin.ch/wms-available-services-an-data), this makes
finding a layer tedious. This script downloads the capabilities document,
sorts the layers by title and saves a copy that QGIS can use instead of the
original.

## What it does

- Downloads a WMS 1.3.0 GetCapabilities document
- Sorts all `<Layer>` elements by `<Title>`, at every level of the layer tree
  - case-insensitive
  - umlauts and accents sort with their base letter (`Ä` with `A`)
  - all other elements inside a `<Layer>` keep their original order
- Keeps the namespace prefixes of the original document
- Writes the result atomically: a failed download or an invalid response
  (e.g. a service exception) never overwrites the last good file
- Leaves all `OnlineResource` URLs unchanged, so GetMap, GetFeatureInfo and
  GetLegendGraphic requests still go to the original server

## Requirements

- Python 3.8 or later (standard library only, no extra packages)
- A web server serving the output directory, e.g. Apache or nginx with
  `/var/www/html`

## Installation

```bash
git clone https://github.com/SARCycle/wms-capabilities-sorter.git
cd wms-capabilities-sorter
sudo cp wms_capabilities_sorter.py /usr/local/bin/
sudo chmod 755 /usr/local/bin/wms_capabilities_sorter.py
```

## Usage

```
wms_capabilities_sorter.py --url URL --output PATH [--timeout SECONDS]
```

| Option      | Required | Description                                    |
|-------------|----------|------------------------------------------------|
| `--url`     | yes      | Full GetCapabilities URL of the WMS            |
| `--output`  | yes      | Path of the sorted output file                 |
| `--timeout` | no       | Download timeout in seconds (default: 120)     |
| `--version` | no       | Show the version and exit                      |

Example with the swisstopo WMS:

```bash
sudo /usr/local/bin/wms_capabilities_sorter.py \
  --url "https://wms.geo.admin.ch/?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities" \
  --output /var/www/html/swisstopo_wms_getcapabilities.xml
```

No output means success. Errors are written to stderr, and the exit code
is 1.

## Scheduling with cron

See [`crontab.example`](crontab.example). To install, run
`sudo crontab -e` and add the line from that file, adapted to your URL and
output path.

## QGIS setup

1. In the Browser panel, right-click **WMS/WMTS** → **New Connection…**
2. Set the URL to the served file, e.g.
   `http://your-server/swisstopo_wms_getcapabilities.xml`.
   QGIS appends `?SERVICE=WMS&REQUEST=GetCapabilities`; a static web
   server ignores this and serves the file.
3. Leave **Ignore GetMap/GetTile/GetLegendGraphic URI reported in
   capabilities** and **Ignore GetFeatureInfo URI reported in
   capabilities** unchecked. Otherwise QGIS sends map requests to your web
   server instead of to the original WMS.

## Running the tests

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests use embedded sample documents and `file://` URLs; no network
access is needed.

## Limitations

- Only WMS 1.3.0 is supported. WMS 1.1.1 documents
  (`WMT_MS_Capabilities`) are rejected with an error.
- XML comments, processing instructions and namespace declarations that are
  not used anywhere in the document are not preserved.
- Layers are sorted within their parent only; the tree structure itself is
  not changed.

## License

Copyright (C) 2026 SARCycle

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option)
any later version. See [`LICENSE`](LICENSE) for the full text.
