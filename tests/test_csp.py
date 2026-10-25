import re


def _script_src(response):
    policy = response.headers.get("Content-Security-Policy", "")
    match = re.search(r"script-src ([^;]+)", policy)
    assert match, policy
    return match.group(1)


def test_script_src_has_no_unsafe_directives(client):
    for path in ("/", "/login"):
        src = _script_src(client.get(path))
        assert "'unsafe-inline'" not in src
        assert "'unsafe-eval'" not in src


def test_login_inline_script_carries_matching_nonce(client):
    response = client.get("/login")
    nonce = re.search(r"'nonce-([^']+)'", _script_src(response)).group(1)
    html = response.get_data(as_text=True)
    assert re.search(rf'<script nonce="{re.escape(nonce)}"[^>]*>', html)
    assert not re.search(r"\sonclick=", html)


def test_login_scripts_opt_out_of_cloudflare_rocket_loader(client):
    """Rocket Loader re-injects scripts without the CSP nonce; they must opt out."""
    response = client.get("/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    scripts = re.findall(r"<script[^>]*>", html)
    assert scripts
    for tag in scripts:
        assert 'data-cfasync="false"' in tag, tag
