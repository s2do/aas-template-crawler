# AAS Template Crawler & Semantic Inventory

This tool is a specialized crawler designed to scan repositories of **Asset Administration Shell (AAS)** templates (JSON/XML). It performs deep semantic analysis to map property relationships, track domain dependencies, and audit AAS `Operation` definitions.

## Features

* **Deep Semantic Analysis:** Maps IRIs across `semanticId`, `supplementalSemanticIds`, `ConceptDescription`, and `isCaseOf` fields.
* **Compatibility Intelligence:** Tracks the usage patterns of external dictionaries (like ECLASS) using the **P:S:C:I Ratio** (Primary:Supplemental:ConceptDescriptionID:IsCaseOf).
* **Operational Audit:** Scans JSON structures for `Operation` definitions and provides line-number-accurate reports for quick debugging.
* **Human-Readable Exports:** Automatically expands `CamelCase` identifiers into clean, human-readable labels.
* **Dual-Format Support:** Processes both JSON and XML templates, providing separate domain statistics for each.

## Setup & Usage

### Prerequisites

* Python 3.x
* No external dependencies required (uses built-in `os`, `re`, `csv`, `json`, `argparse`, `urllib`, and `collections`).

### Running the Crawler

Run the script from your terminal by pointing it to the directory containing your AAS templates:

```bash
python url-crawler.py /path/to/your/templates

```

## Generated Artifacts

| Filename | Description |
| --- | --- |
| `idta_stats_json.csv` | Domain frequency for all JSON-based IRIs. |
| `idta_stats_xml.csv` | Domain frequency for all XML-based IRIs. |
| `idta_element_types.csv` | Distribution of `modelType` across the repository. |
| `idta_glossary.csv` | Comprehensive semantic inventory (detailed below). |
| `idta_files_with_operations.csv` | Audit log of where `Operation` elements are defined. |

## Data Dictionary (`idta_glossary.csv`)

| Field | Description |
| --- | --- |
| **Term (idShort)** | The machine-readable identifier. |
| **Expanded Name** | Human-readable version (e.g., `MaxSpeed` → `Max Speed`). |
| **Element Types** | AAS `modelType` (e.g., `Property`, `Qualifier`). |
| **IRI** | The unique identifier or standard reference. |
| **Compatibility(P:S:C:I Ratio)** | Usage distribution: **P**rimary, **S**upplemental, **C**onceptDescription, **I**sCaseOf. |
| **Definition** | English-language description of the term. |
| **Source Files** | Comma-separated list of files where the IRI appears. |
| **TotalCount** | Total frequency across the repository. |

## Version History & Notes

* **P:S:C:I Integrity:** The glossary includes a checksum logic. If `TotalCount` does not equal the sum of the components in the ratio, an integrity warning is logged to the console.
* **CamelCase Expansion:** Automatically handles standard AAS naming conventions and common acronyms (e.g., `MACAddress` → `MAC Address`).