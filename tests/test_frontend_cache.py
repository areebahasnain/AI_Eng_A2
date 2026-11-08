"""Regression: local browser must not mix old JS with new markup."""
import hashlib
import re
from fastapi.testclient import TestClient
from backend.main import app, FRONTEND_DIR


def test_frontend_urls_are_content_versioned_and_uncached():
    with TestClient(app) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert 'no-store' in response.headers['cache-control']
        html = response.text
        for name in ('app.js', 'style.css'):
            digest = hashlib.sha256((FRONTEND_DIR / name).read_bytes()).hexdigest()[:16]
            assert '/static/' + name + '?v=' + digest in html
            static = client.get('/static/' + name + '?v=' + digest)
            assert static.status_code == 200
            assert 'no-store' in static.headers['cache-control']
        assert '__APP_HASH__' not in html
        assert '__STYLE_HASH__' not in html


def test_ui_required_ids_exist_in_index_markup():
    html = (FRONTEND_DIR / 'index.html').read_text(encoding='utf-8')
    script = (FRONTEND_DIR / 'app.js').read_text(encoding='utf-8')
    ids = re.findall(r"'([a-z-]+)'", script.split('const ids = [', 1)[1].split('];', 1)[0])
    for id_ in ids:
        assert re.search(r'id=[\"\']' + re.escape(id_) + r'[\"\']', html), id_
    assert 'assertCurrentMarkup();' in script
