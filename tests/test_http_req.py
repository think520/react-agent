from unittest.mock import patch, MagicMock
import httpx
from tools.http_req import http_request, MAX_RESPONSE_SIZE
from tools.base import ToolResult


def _mock_response(status_code=200, text="OK", http_version="1.1", reason_phrase="OK",
                   content_type="text/plain", content=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.http_version = http_version
    resp.reason_phrase = reason_phrase
    resp.content = content if content is not None else text.encode("utf-8")
    resp_headers = {"content-type": content_type}
    if headers:
        resp_headers.update(headers)
    resp.headers = resp_headers
    resp.is_redirect = False
    return resp


class TestHttpRequest:
    @patch("tools.http_req.httpx.Client")
    def test_get_request(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(200, '{"hello":"world"}')
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com/api", allow_private_network=True)

        assert isinstance(result, ToolResult)
        assert result.ok
        assert "HTTP/1.1 200 OK" in result.content
        assert '{"hello":"world"}' in result.content
        assert "content-type: text/plain" in result.content
        assert result.data["status_code"] == 200

    @patch("tools.http_req.httpx.Client")
    def test_post_with_body(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(201, '{"id":1}')
        mock_client_cls.return_value = mock_client

        result = http_request(
            "https://example.com/items",
            method="POST",
            headers={"Content-Type": "application/json"},
            body='{"name":"test"}',
            allow_private_network=True,
        )

        assert result.ok
        assert result.data["status_code"] == 201

    @patch("tools.http_req.httpx.Client")
    def test_put_delete_patch(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(200, "ok")
        mock_client_cls.return_value = mock_client

        for method in ("PUT", "DELETE", "PATCH"):
            mock_client.reset_mock()
            result = http_request("https://example.com/resource", method=method, allow_private_network=True)
            assert result.ok

    def test_invalid_method(self):
        result = http_request("https://example.com", method="INVALID")
        assert not result.ok
        assert "unsupported" in result.content.lower()

    def test_non_http_url(self):
        result = http_request("ftp://example.com/file")
        assert not result.ok
        assert "only http" in result.content.lower()

    @patch("tools.http_req.httpx.Client")
    def test_timeout_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.TimeoutException("timed out")
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com", timeout=5, allow_private_network=True)
        assert not result.ok
        assert "timed out" in result.content.lower()

    @patch("tools.http_req.httpx.Client")
    def test_connection_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.ConnectError("refused")
        mock_client_cls.return_value = mock_client

        result = http_request("https://unreachable.example.com", allow_private_network=True)
        assert not result.ok
        assert "connection error" in result.content.lower()

    @patch("tools.http_req.httpx.Client")
    def test_response_truncation(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        big_body = "x" * (MAX_RESPONSE_SIZE + 5000)
        mock_client.request.return_value = _mock_response(200, big_body)
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com/big", allow_private_network=True)
        assert result.ok
        assert "truncated" in result.content.lower()
        # Now reports bytes, not characters
        assert str(len(big_body.encode("utf-8"))) in result.content

    @patch("tools.http_req.httpx.Client")
    def test_error_status_code_still_ok(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(404, "Not Found")
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com/missing", allow_private_network=True)
        assert result.ok
        assert "404" in result.content

    @patch("tools.http_req.httpx.Client")
    def test_head_request(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(200, "")
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com", method="HEAD", allow_private_network=True)
        assert result.ok

    def test_case_insensitive_method(self):
        with patch("tools.http_req.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.request.return_value = _mock_response()
            mock_client_cls.return_value = mock_client

            result = http_request("https://example.com", method="get", allow_private_network=True)
            assert result.ok

    # SSRF tests
    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_localhost_blocked(self, mock_dns):
        result = http_request("http://localhost:8000/api")
        assert not result.ok
        assert "denied" in result.content.lower()

    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_127_loopback_blocked(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, '', ('127.0.0.1', 0))]
        result = http_request("http://127.0.0.1:8000/api")
        assert not result.ok
        assert "denied" in result.content.lower()

    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_private_10_blocked(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, '', ('10.0.0.1', 0))]
        result = http_request("http://internal.service/api")
        assert not result.ok
        assert "denied" in result.content.lower()

    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_private_192_168_blocked(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, '', ('192.168.1.1', 0))]
        result = http_request("http://router.local/api")
        assert not result.ok
        assert "denied" in result.content.lower()

    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_link_local_169_254_blocked(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, '', ('169.254.169.254', 0))]
        result = http_request("http://metadata.google/latest/meta-data")
        assert not result.ok
        assert "denied" in result.content.lower()

    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_allow_private_bypasses_check(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, '', ('10.0.0.1', 0))]
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(200, "ok")

        with patch("tools.http_req.httpx.Client", return_value=mock_client):
            result = http_request("http://10.0.0.1/api", allow_private_network=True)
            assert result.ok

    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_public_url_passes(self, mock_dns):
        mock_dns.return_value = [(2, 1, 6, '', ('93.184.216.34', 0))]
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(200, "ok")

        with patch("tools.http_req.httpx.Client", return_value=mock_client):
            result = http_request("https://example.com")
            assert result.ok

    @patch("tools.http_req.socket.getaddrinfo")
    def test_ssrf_redirect_to_private_blocked(self, mock_dns):
        """A redirect to a private IP should be blocked."""
        # First DNS resolution: public IP
        # Second DNS resolution (for redirect): private IP
        mock_dns.side_effect = [
            [(2, 1, 6, '', ('93.184.216.34', 0))],  # example.com
            [(2, 1, 6, '', ('10.0.0.1', 0))],  # redirect target
        ]

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.is_redirect = True
        redirect_resp.headers = {"location": "http://internal.local/secret"}

        mock_client.request.return_value = redirect_resp

        with patch("tools.http_req.httpx.Client", return_value=mock_client):
            result = http_request("https://example.com")
            assert not result.ok
            assert "redirect blocked" in result.content.lower()

    @patch("tools.http_req.httpx.Client")
    def test_binary_content_type_omits_body(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(
            200, "", content_type="application/pdf", content=b"\x00" * 348291
        )
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com/file.pdf", allow_private_network=True)
        assert result.ok
        assert "body omitted" in result.content.lower()
        assert "348291" in result.content
        assert "application/pdf" in result.content

    @patch("tools.http_req.httpx.Client")
    def test_utf8_chinese_truncated_by_bytes(self, mock_client_cls):
        """Chinese text truncation should be based on bytes, not characters."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        chinese_text = "你好世界" * 3000  # 4 chars * 3 bytes * 3000 = 36000 bytes
        raw_bytes = chinese_text.encode("utf-8")
        mock_client.request.return_value = _mock_response(
            200, chinese_text, content_type="text/plain; charset=utf-8", content=raw_bytes
        )
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com/chinese", allow_private_network=True)
        assert result.ok
        assert "truncated" in result.content.lower()
        assert str(len(raw_bytes)) in result.content  # reports byte count

    @patch("tools.http_req.httpx.Client")
    def test_response_headers_summary(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = _mock_response(
            200, "ok", headers={"content-length": "2"}
        )
        mock_client_cls.return_value = mock_client

        result = http_request("https://example.com", allow_private_network=True)
        assert result.ok
        assert "content-type:" in result.content
