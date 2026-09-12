# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.2] - 2026-09-13

### Added

- Support for single-page bank statements in `bnp_parser.py`: correctly isolates transactions between opening balance header and totals/closing balance footer on a single page.
- Unit tests in `test_bnp_parser.py` covering word boundary splitting and summary extraction for single-page statements containing both opening and closing `SOLDE` lines.

### Fixed

- Preserve extracted summary metadata in `extract_pdf_to_dataframe` by merging non-empty summary fields across pages instead of overwriting the summary dictionary.

## [0.1.1] - 2026-09-12

### Fixed

- Fix card transaction prefix check in `feature_extraction.py` by passing a tuple to `str.startswith`.

## [0.1.0] - 2026-09-12

### Added

- Initial release: local extraction pipeline, structured pdf parsing and transactions enrichment.
