from src.processing.dedup import normalize_url, compute_content_hash


class TestNormalizeUrl:
    def test_strips_www(self):
        assert "https://example.com/page" == normalize_url("https://www.example.com/page")

    def test_strips_tracking_params(self):
        url = "https://example.com/article?id=1&utm_source=twitter&utm_medium=social"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=1" in result

    def test_strips_trailing_slash(self):
        assert normalize_url("https://example.com/page/") == normalize_url("https://example.com/page")

    def test_strips_fragment(self):
        assert normalize_url("https://example.com/page#section") == normalize_url("https://example.com/page")

    def test_normalizes_reddit(self):
        old = normalize_url("https://old.reddit.com/r/MachineLearning/post")
        new = normalize_url("https://new.reddit.com/r/MachineLearning/post")
        plain = normalize_url("https://reddit.com/r/MachineLearning/post")
        assert old == new == plain

    def test_lowercases_hostname(self):
        assert normalize_url("https://EXAMPLE.COM/Page") == normalize_url("https://example.com/Page")

    def test_forces_https(self):
        result = normalize_url("http://example.com/page")
        assert result.startswith("https://")

    def test_strips_fbclid(self):
        url = "https://example.com/post?fbclid=abc123&ref=share"
        result = normalize_url(url)
        assert "fbclid" not in result
        assert "ref" not in result

    def test_preserves_meaningful_params(self):
        url = "https://arxiv.org/abs/2401.12345?v=2"
        result = normalize_url(url)
        assert "v=2" in result


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("Test Title", "Test content here")
        h2 = compute_content_hash("Test Title", "Test content here")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_content_hash("Test Title", "content")
        h2 = compute_content_hash("test title", "content")
        assert h1 == h2

    def test_different_titles_different_hash(self):
        h1 = compute_content_hash("Title A", "same content")
        h2 = compute_content_hash("Title B", "same content")
        assert h1 != h2

    def test_uses_first_500_chars(self):
        content = "x" * 600
        h1 = compute_content_hash("title", content)
        h2 = compute_content_hash("title", content[:500] + "DIFFERENT")
        assert h1 == h2
