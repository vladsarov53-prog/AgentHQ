"""Tests for the digest formatter with category grouping."""
import json

from src.bot.formatter import (
    format_digest,
    format_digest_cards,
    format_instant,
    _get_article_section,
    _dedup_articles,
    MAX_DIGEST_ARTICLES,
)


def _article(
    importance=7,
    source="Test Source",
    tags='["models"]',
    title_ru="Тест",
    summary_ru="Описание",
    url="https://example.com/article",
):
    return {
        "id": 1,
        "title": "Test Article",
        "title_ru": title_ru,
        "summary_ru": summary_ru,
        "source_name": source,
        "url": url,
        "tags": tags,
        "importance_score": importance,
    }


class TestFormatDigest:
    def test_empty_articles(self):
        result = format_digest([], "05 April 2026")
        assert len(result) == 1
        assert "нет" in result[0].lower()

    def test_filters_low_importance(self):
        articles = [_article(importance=3)]
        result = format_digest(articles, "05 April 2026")
        assert "значимых" in result[0].lower() or "нет" in result[0].lower()

    def test_includes_high_importance(self):
        articles = [_article(importance=9)]
        result = format_digest(articles, "05 April 2026")
        combined = "".join(result)
        assert "Тест" in combined

    def test_max_articles_limit(self):
        articles = [
            _article(importance=8, url=f"https://a.com/{i}", title_ru=f"Уникальная статья {i}")
            for i in range(15)
        ]
        result = format_digest(articles, "05 April 2026")
        combined = "".join(result)
        assert "1." in combined
        # Should not exceed MAX_DIGEST_ARTICLES
        assert f"{MAX_DIGEST_ARTICLES + 1}." not in combined

    def test_numbered_format(self):
        articles = [_article(importance=8)]
        result = format_digest(articles, "05 April 2026")
        combined = "".join(result)
        assert "1." in combined

    def test_header_present(self):
        articles = [_article(importance=8)]
        result = format_digest(articles, "05 April 2026")
        assert "AI-дайджест" in result[0]

    def test_source_count_in_footer(self):
        articles = [
            _article(importance=8, source="Source A", url="https://a.com/1"),
            _article(importance=7, source="Source B", url="https://b.com/2", title_ru="Другая статья"),
        ]
        result = format_digest(articles, "05 April 2026")
        combined = "".join(result)
        assert "2 источников" in combined or "2 источник" in combined

    def test_top_news_section(self):
        articles = [
            _article(title_ru="Суперважная", importance=9),
            _article(title_ru="Обычная", importance=6, url="https://a.com/2"),
        ]
        result = format_digest(articles, "05 April 2026")
        text = "\n".join(result)
        assert "ГЛАВНОЕ" in text
        assert "Суперважная" in text

    def test_category_grouping(self):
        articles = [
            _article(title_ru="Продукт", tags='["products"]', importance=7, url="https://a.com/1"),
            _article(title_ru="Исследование", tags='["research"]', importance=6, url="https://a.com/2"),
        ]
        result = format_digest(articles, "05 April 2026")
        text = "\n".join(result)
        assert "ПРОДУКТЫ" in text
        assert "ИССЛЕДОВАНИЯ" in text

    def test_why_matters_for_top(self):
        articles = [
            _article(
                title_ru="Мегановость",
                summary_ru="Описание\n- Это меняет индустрию",
                importance=9,
            ),
        ]
        result = format_digest(articles, "05 April 2026")
        text = "\n".join(result)
        assert "Почему важно" in text

    def test_read_original_link(self):
        articles = [_article(importance=8)]
        result = format_digest(articles, "05 April 2026")
        text = "\n".join(result)
        assert "Читать оригинал" in text

    def test_dedup_in_digest(self):
        articles = [
            _article(title_ru="Claude 4 released", importance=8),
            _article(title_ru="Claude 4 released Anthropic", importance=7, url="https://a.com/2"),
        ]
        result = format_digest(articles, "05 April 2026")
        text = "\n".join(result)
        assert text.count("Claude 4") == 1

    def test_split_long_messages(self):
        articles = [
            _article(
                title_ru=f"Длинная статья {i}",
                summary_ru="A" * 300,
                importance=7,
                url=f"https://a.com/{i}",
            )
            for i in range(10)
        ]
        result = format_digest(articles, "05 April 2026")
        for msg in result:
            assert len(msg) <= 4000


class TestFormatDigestCards:
    def test_returns_digest_cards(self):
        articles = [_article(importance=7)]
        cards = format_digest_cards(articles, "05 April 2026")
        assert len(cards) >= 1
        assert cards[0].text
        assert cards[0].image_url is None


class TestFormatInstant:
    def test_contains_title_and_link(self):
        result = format_instant(_article())
        assert "Тест" in result
        assert "https://example.com/article" in result

    def test_contains_source(self):
        result = format_instant(_article(source="OpenAI Blog"))
        assert "OpenAI Blog" in result

    def test_html_escaping(self):
        article = _article(title_ru="<script>alert('xss')</script>")
        result = format_instant(article)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_read_original_link(self):
        result = format_instant(_article())
        assert "Читать оригинал" in result

    def test_with_why_matters(self):
        article = _article(summary_ru="Описание\n- Это меняет всё")
        result = format_instant(article)
        assert "Почему важно" in result


class TestGetArticleSection:
    def test_products_tag(self):
        article = _article(tags='["products"]')
        assert _get_article_section(article) == "products"

    def test_research_tag(self):
        article = _article(tags='["research"]')
        assert _get_article_section(article) == "research"

    def test_agentic_tags(self):
        for tag in ["agentic", "mcp_a2a", "llm_engineering"]:
            article = _article(tags=json.dumps([tag]))
            assert _get_article_section(article) == "agentic"

    def test_no_tags(self):
        article = _article(tags='[]')
        assert _get_article_section(article) == "other"

    def test_safety_goes_to_other(self):
        article = _article(tags='["safety"]')
        assert _get_article_section(article) == "other"


class TestDedupArticles:
    def test_removes_similar(self):
        articles = [
            _article(title_ru="Claude 4 released by Anthropic", importance=8),
            _article(title_ru="Claude 4 released", importance=7),
        ]
        result = _dedup_articles(articles)
        assert len(result) == 1

    def test_keeps_different(self):
        articles = [
            _article(title_ru="Claude 4 released", importance=8),
            _article(title_ru="GPT-5 benchmarks results", importance=7),
        ]
        result = _dedup_articles(articles)
        assert len(result) == 2
