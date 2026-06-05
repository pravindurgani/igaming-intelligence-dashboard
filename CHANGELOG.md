# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Repository cleanup utility (`scripts/cleanup_repo.py`) for removing generated artefacts
- Comprehensive documentation structure under `docs/` with `audits/` and `reports/` subdirectories
- `pyproject.toml` for standardized tool configuration (ruff, black, isort, mypy, pytest)
- CI check for repository cleanliness to prevent committing generated files
- Complete test suite with 80+ passing tests covering all major functionality

### Changed
- Organized documentation: moved audit reports to `docs/audits/`, release notes to `docs/reports/`
- Analysis now uses full 30-day rolling window from `news_history.csv` instead of `latest_competitor_news.json`
- Improved `.gitignore` to cover all cache directories and temporary files
- Enhanced CI workflow with cleanup checks before linting and testing

### Fixed
- Analysis count mismatch: Now processes 199 articles (180 competitor + 19 internal) from 291 in 30-day window
- Context Explorer KeyError: Fixed column name from `'date'` to `'published_date'`
- Dropdown filtering: Keywords now show accurate article counts and hide zero-result options
- Article ID generation: Consistent URL normalization eliminates duplicates
- Atomic CSV writes: Crash-safe persistence prevents data corruption
- UTC timezone normalization: Consistent date filtering across all components

### Removed
- Cache directories from version control (`__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`)
- Clutter from repository root: moved 11 markdown docs to organized structure

## [1.0.0] - 2025-12-15

### Added
- Initial stable release
- iGaming competitive intelligence dashboard with Streamlit UI
- Automated news scraping and analysis pipeline
- Google Gemini-powered gap analysis and strategic insights
- 30-day rolling window analysis with smart article selection
- Company and location entity extraction using spaCy
- Comprehensive test suite with data integrity checks
- Pre-commit hooks for code quality
- GitHub Actions CI/CD pipeline

[Unreleased]: https://github.com/yourusername/repo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/yourusername/repo/releases/tag/v1.0.0
