import json
from datetime import datetime, timezone

from app.execution import accounting
from app.status import build_site


def test_cloud_build_preserves_published_account_and_local_export_replaces_it(tmp_path, monkeypatch):
    account_path = tmp_path / 'account.json'
    monkeypatch.setattr(accounting, 'ACCOUNT', account_path)
    monkeypatch.setattr(build_site, 'DOCS', tmp_path)
    assert not build_site._paper_account()['available']
    stamp = datetime.now(timezone.utc).isoformat()
    account_path.write_text(json.dumps({
        'seq': 1, 'runtime': {
            'last_mark_seq': 1, 'last_mark_ts': stamp,
            'last_snapshot': {'equity': 100123, 'return_percent': 0.123},
            'daily_equity': {'2026-09-29': {'ts': stamp, 'equity': 100123}},
        },
    }))
    local = build_site._paper_account()
    assert local['available'] and local['portfolio']['equity'] == 100123
    account_path.unlink()
    cloud = build_site._paper_account()
    assert cloud['as_of'] == stamp
    assert cloud['equity_curve'] == local['equity_curve']
    assert cloud['mark_age_seconds'] >= local['mark_age_seconds']
    # A present but damaged account must never silently reuse an older good mark.
    account_path.write_text('invalid')
    assert not build_site._paper_account()['available']
