"""The historical HTTP suites may run ONLY against an explicit local test SUT."""
import os
from urllib.parse import urlsplit
from unittest.mock import patch

import pytest


def pytest_configure(config):
    # These defaults prevent module-level legacy preview fallbacks during collection.
    base = os.environ.get("LOCAL_BACKEND_TEST_URL", "http://127.0.0.1:18089")
    if base != "http://127.0.0.1:18089":
        raise pytest.UsageError("Only the disposable localhost backend is allowed")
    os.environ["REACT_APP_BACKEND_URL"] = base
    os.environ["API_BASE_URL"] = base


def pytest_collection_modifyitems(config, items):
    if os.environ.get("SOLVIT_LOCAL_INTEGRATION") == "1":
        if os.environ.get("MONGO_URL") != "mongodb://127.0.0.1:27089/" or not os.environ.get("DB_NAME", "").startswith("codex_integrity_suite_"):
            raise pytest.UsageError("Full integration run requires a disposable localhost database")
        return
    for item in items:
        if item.path.name.startswith("test_iteration_") or item.path.name in ("test_solvit_platform.py", "test_reminder_service.py"):
            item.add_marker(pytest.mark.skip(reason="Requires explicitly configured disposable localhost SUT"))


@pytest.fixture(scope="session", autouse=True)
def prohibit_external_http():
    import socket
    import inspect
    import requests
    import httpx
    original_connect = socket.socket.connect
    original_requests = requests.sessions.Session.send
    original_httpx = httpx.HTTPTransport.handle_request
    original_send = httpx.Client.send

    def allowed(url):
        parsed = urlsplit(str(url))
        if parsed.scheme not in ("http", "https") or parsed.hostname != "127.0.0.1" or parsed.port != 18089:
            raise AssertionError("External/non-test HTTP request blocked by regression safety guard")

    def request_send(session, request, **kwargs):
        allowed(request.url)
        result = original_requests(session, request, **kwargs)
        # Production cookies stay Secure. Only loopback HTTP test clients adapt.
        for cookie in session.cookies:
            cookie.secure = False
        return result

    def transport_send(transport, request):
        allowed(request.url)
        return original_httpx(transport, request)

    def client_send(client, request, **kwargs):
        result = original_send(client, request, **kwargs)
        if urlsplit(str(request.url)).hostname == "127.0.0.1":
            for cookie in client.cookies.jar:
                cookie.secure = False
        return result

    def local_connect(sock, address):
        caller = inspect.currentframe().f_back
        internal_socketpair = caller.f_code.co_filename == socket.__file__ and caller.f_code.co_name == "_fallback_socketpair"
        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "localhost", "::1") or (address[1] not in (18089, 27089) and not internal_socketpair):
            raise OSError("Non-test socket connection blocked")
        return original_connect(sock, address)

    with patch.object(socket.socket, "connect", local_connect), patch.object(requests.sessions.Session, "send", request_send), patch.object(httpx.HTTPTransport, "handle_request", transport_send), patch.object(httpx.Client, "send", client_send):
        yield


@pytest.fixture(autouse=True)
def isolate_local_auth_limits():
    if os.environ.get("SOLVIT_LOCAL_INTEGRATION") != "1":
        yield
        return
    import requests
    endpoint = "http://127.0.0.1:18089/__test__/reset-auth-limits"
    response = requests.post(endpoint, timeout=5)
    assert response.status_code == 200 and response.json().get("test_only") is True
    try:
        yield
    finally:
        requests.post(endpoint, timeout=5)


@pytest.fixture(scope="module", autouse=True)
def isolate_local_fixture_modules():
    if os.environ.get("SOLVIT_LOCAL_INTEGRATION") == "1":
        import requests
        response = requests.post("http://127.0.0.1:18089/__test__/reset-fixtures", timeout=15)
        assert response.status_code == 200 and response.json().get("test_only") is True


@pytest.fixture
def complete_employee_form():
    """Exercise real subject signatures, with existing HR delegation otherwise."""
    import requests
    base = "http://127.0.0.1:18089/api"
    password = os.environ["DEMO_SEED_PASSWORD"]

    def complete(hr, employee, form_id, data):
        it = requests.Session()
        assert it.post(f"{base}/auth/login", json={"email": "itadmin@solvit.co.ke", "password": password}).status_code == 200
        provision = it.post(f"{base}/access/users/employee-account", json={"employee_id": employee["id"], "initial_password": password})
        assert provision.status_code == 200, provision.text
        subject = requests.Session()
        assert subject.post(f"{base}/auth/login", json={"email": employee["work_email"], "password": password}).status_code == 200
        completed_password = password + "-Changed"
        changed = subject.post(f"{base}/auth/password/change", json={"current_password": password, "new_password": completed_password})
        assert changed.status_code == 200, changed.text
        assert subject.post(f"{base}/auth/login", json={"email": employee["work_email"], "password": completed_password}).status_code == 200
        started = hr.post(f"{base}/forms/{form_id}/start", json={"employee_id": employee["id"], "data": data})
        assert started.status_code == 200, started.text
        submission = started.json()
        while submission.get("next_required_role"):
            signer = subject if submission["next_required_role"] == "employee" else hr
            signed = signer.post(f"{base}/forms/submissions/{submission['id']}/sign", json={"signature": "Synthetic authorized signature"})
            assert signed.status_code == 200, signed.text
            submission = signed.json()
        assert submission["status"] == "Completed"
        return signed

    return complete
