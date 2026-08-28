# Third-Party Notices

Visory includes source code imported from the following upstream project.

## Daily Stock Analysis

- Project: Daily Stock Analysis
- Source: https://github.com/ZhuLinsen/daily_stock_analysis
- Imported revision: `fb4735a1055caefa2396982af3b09121feb9ff30`
- License: MIT
- License copy: `third_party/licenses/daily_stock_analysis-MIT.txt`
- Imported paths and exclusions: `upstream-baseline/daily_stock_analysis.yaml`
- Upstream documentation: `docs/upstream/daily_stock_analysis/`
- Imported CI test support: `.github/requirements-ci.txt`, `.github/ci-test-durations.json`, `.github/scripts/ai_review.py`, `.github/scripts/build_release_notes.py`
- Non-active workflow evidence: `docs/upstream/daily_stock_analysis/workflows/`

The archived workflow files are outside `.github/workflows/` and are retained only for fixed-baseline tests and migration audit. Visory does not enable the upstream daily-analysis, release, publish, or deployment automation.

The upstream project also includes modified code derived from AlphaSift:

- Project: AlphaSift
- Source: https://github.com/ZhuLinsen/alphasift
- Referenced revision: `9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf`
- License: Apache License 2.0
- Included paths: `src/services/screening/**/*.py` and
  `src/services/screening/strategies/*.yaml`
- License copy retained with the imported code:
  `src/services/screening/LICENSE`

The original upstream notice is preserved at
`docs/upstream/daily_stock_analysis/THIRD_PARTY_NOTICES.md`.
