# CI

`github-workflow-ci.yml` is the GitHub Actions workflow for this repo. The Arena
sandbox's GitHub App cannot push `.github/workflows/*` (missing `workflows`
permission), so it lives here until a human moves it:

    mkdir -p .github/workflows && git mv ci/github-workflow-ci.yml .github/workflows/ci.yml

Run the same gates locally:

    bash -n install.sh && shellcheck -S warning install.sh
    ./install.sh --verify-only --skip-owl; test $? -eq 2
    scripts/gen-status.py --check
    python3 -m unittest discover -s sidecars/semcache/tests
