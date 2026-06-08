# Contributing to Forkmark

Thanks for your interest in improving Forkmark! This project is early and
contributions — bug reports, docs fixes, and PRs — are very welcome.

## Ways to help

- **Report a bug** or **request a feature** via the issue templates.
- **Improve the docs** — clarity fixes are some of the most valuable PRs.
- **Add an importer** for another tool (LangSmith, Helicone, raw OpenAI logs).
- Look for issues labelled **`good first issue`**.

## Development setup

```bash
git clone https://github.com/forkmark/forkmark.git
cd forkmark

# Backend
pip install -r requirements.txt
python run.py            # serves UI + API at http://localhost:7700

# Frontend (only if you change the UI)
cd frontend && npm install && npm run build   # or `npm run dev` for hot reload
```

The SDK lives in `sdk/forkmark/`. To work on it locally:

```bash
pip install -e sdk          # installs the `forkmark` package + `forkmark` CLI
```

## Running tests

```bash
# Backend + SDK (Python)
pytest tests/ -q

# Frontend
cd frontend && npm test -- --run
```

CI runs the same suites on Python 3.10–3.12 plus a frontend build. Please make
sure `pytest tests/` is green before opening a PR.

If you change the README's SDK quickstart, also update `tests/test_readme_example.py`
(it intentionally pins the README to the real SDK surface so the example can't drift).

## Pull request guidelines

- Keep PRs focused — one logical change per PR.
- Add or update tests for behaviour changes.
- Update `CHANGELOG.md` under the `## [Unreleased]` heading.
- Match the existing code style (no formatter is enforced; keep it readable and
  consistent with the surrounding file).

## Code of conduct

Be respectful and constructive. We want Forkmark to be a friendly place for
people of all backgrounds and experience levels.

## License

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).
