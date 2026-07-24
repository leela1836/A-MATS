"""Static status-site generator for GitHub Pages.

Pages serves static files, so on every scan we dump the journal + model to
small JSON files (`docs/data.json`, `docs/nn.json`); the committed HTML pages
fetch them (and auto-refresh), giving a live, phone-friendly dashboard at a URL
without running any server.
"""
