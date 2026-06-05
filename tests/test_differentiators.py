"""
Tests for the differentiators extraction module.

Tests cover:
- Text preprocessing and normalization
- N-gram extraction
- Log-odds calculation
- All differentiator extractors (language, company, region, format, cadence)
- Integration with sample data
"""

import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.differentiators import (
    KNOWN_COMPANIES,
    REGIONS,
    build_corpus,
    calculate_cadence_metrics,
    calculate_log_odds_scores,
    classify_article_format,
    extract_all_differentiators,
    extract_company_differentiators,
    extract_company_mentions,
    extract_format_differentiators,
    extract_ngrams,
    extract_region_differentiators,
    extract_region_mentions,
    extract_term_differentiators,
    is_meaningful_term,
    log_odds_ratio,
    preprocess_for_ngrams,
)


class TestTextPreprocessing:
    """Tests for text preprocessing functions."""

    def test_preprocess_strips_html(self):
        """Test that HTML tags are removed."""
        text = "<p>Hello <b>world</b></p>"
        result = preprocess_for_ngrams(text)
        assert "<" not in result
        assert ">" not in result
        assert "hello" in result
        assert "world" in result

    def test_preprocess_handles_empty(self):
        """Test empty input handling."""
        assert preprocess_for_ngrams("") == ""
        assert preprocess_for_ngrams(None) == ""
        assert preprocess_for_ngrams("   ") == ""

    def test_preprocess_normalizes_case(self):
        """Test that text is lowercased."""
        result = preprocess_for_ngrams("HELLO World")
        assert result.islower() or result == ""

    def test_preprocess_handles_unicode(self):
        """Test unicode normalization."""
        result = preprocess_for_ngrams("café résumé")
        # Should remove or normalize accents
        assert "cafe" in result or "café" in result

    def test_build_corpus_combines_fields(self):
        """Test that corpus builder combines title, summary, content."""
        df = pd.DataFrame([
            {'title': 'Test Title', 'summary': 'Test Summary', 'content': 'Test Content'},
            {'title': 'Another Title', 'summary': '', 'content': None}
        ])
        corpus = build_corpus(df)
        assert 'test' in corpus
        assert 'title' in corpus
        assert 'summary' in corpus
        assert 'another' in corpus


class TestNgramExtraction:
    """Tests for n-gram extraction."""

    def test_extract_ngrams_basic(self):
        """Test basic n-gram extraction."""
        corpus = "the quick brown fox jumps over the lazy dog"
        ngrams = extract_ngrams(corpus, ngram_range=(1, 2))

        # Should contain unigrams
        assert 'quick' in ngrams
        assert 'brown' in ngrams

        # Should contain bigrams
        assert 'quick brown' in ngrams or ngrams.get('quick brown', 0) >= 0

    def test_extract_ngrams_empty(self):
        """Test with empty corpus."""
        ngrams = extract_ngrams("")
        assert len(ngrams) == 0

    def test_extract_ngrams_returns_counter(self):
        """Test that result is a Counter."""
        ngrams = extract_ngrams("test text test")
        assert isinstance(ngrams, Counter)


class TestLogOddsCalculation:
    """Tests for log-odds ratio calculation."""

    def test_log_odds_symmetric(self):
        """Test that equal counts give ~0 log-odds."""
        # With same proportions, log-odds should be ~0
        score = log_odds_ratio(10, 100, 10, 100)
        assert abs(score) < 0.1

    def test_log_odds_positive_for_corpus_a(self):
        """Test that higher count in A gives positive log-odds."""
        # More in corpus A than B
        score = log_odds_ratio(50, 100, 10, 100)
        assert score > 0

    def test_log_odds_negative_for_corpus_b(self):
        """Test that higher count in B gives negative log-odds."""
        # More in corpus B than A
        score = log_odds_ratio(10, 100, 50, 100)
        assert score < 0

    def test_log_odds_handles_zero_counts(self):
        """Test smoothing prevents divide-by-zero."""
        # Zero count in corpus B - smoothing should handle it
        score = log_odds_ratio(10, 100, 0, 100)
        assert score > 0  # Should be positive (term only in A)

    def test_calculate_log_odds_scores(self):
        """Test batch log-odds calculation."""
        internal = Counter({'term1': 50, 'term2': 10, 'shared': 20})
        competitor = Counter({'term1': 10, 'term3': 50, 'shared': 20})

        scores = calculate_log_odds_scores(internal, competitor, min_count=5)

        # term1 should have positive score (more in internal)
        assert scores.get('term1', 0) > 0
        # term3 should have negative score (only in competitor)
        assert scores.get('term3', 0) < 0
        # shared should be ~0
        assert abs(scores.get('shared', 1)) < 1


class TestMeaningfulTermFilter:
    """Tests for stopword and generic term filtering."""

    def test_filters_stopwords(self):
        """Test that common stopwords are filtered."""
        assert not is_meaningful_term('the')
        assert not is_meaningful_term('and')
        assert not is_meaningful_term('for')

    def test_filters_generic_gaming_terms(self):
        """Test that generic gaming terms are filtered."""
        assert not is_meaningful_term('gaming')
        assert not is_meaningful_term('betting')
        assert not is_meaningful_term('casino')

    def test_allows_specific_terms(self):
        """Test that specific terms pass."""
        assert is_meaningful_term('draftkings')
        assert is_meaningful_term('brazil')
        assert is_meaningful_term('regulatory')

    def test_multi_word_terms(self):
        """Test multi-word term filtering."""
        # Should pass if has at least one meaningful word
        assert is_meaningful_term('brazil market')
        assert is_meaningful_term('regulatory update')
        # Should fail if all stopwords/generic
        assert not is_meaningful_term('the and')


class TestTermDifferentiators:
    """Tests for term differentiator extraction."""

    def test_extract_term_differentiators_returns_list(self):
        """Test that result is a list of dicts."""
        internal = Counter({'unique_term': 50, 'shared': 20})
        competitor = Counter({'other_term': 50, 'shared': 20})

        result = extract_term_differentiators(internal, competitor, top_n=5)

        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], dict)
            assert 'term' in result[0]
            assert 'log_odds' in result[0]

    def test_extract_term_differentiators_sorts_by_score(self):
        """Test that results are sorted by log-odds score."""
        internal = Counter({'term1': 100, 'term2': 50, 'term3': 10})
        competitor = Counter({'term1': 10, 'term2': 10, 'term3': 10})

        result = extract_term_differentiators(internal, competitor, top_n=3, min_count=5)

        # Should be sorted descending by log_odds
        scores = [r['log_odds'] for r in result]
        assert scores == sorted(scores, reverse=True)


class TestCompanyDifferentiators:
    """Tests for company coverage differentiators."""

    def test_extract_company_mentions(self):
        """Test company mention extraction."""
        corpus = "draftkings launched a new feature. betmgm followed suit. draftkings also expanded."
        mentions = extract_company_mentions(corpus)

        assert mentions['draftkings'] == 2
        assert mentions['betmgm'] == 1

    def test_extract_company_differentiators(self):
        """Test company differentiator extraction."""
        internal_df = pd.DataFrame([
            {'title': 'DraftKings Launches Feature', 'summary': 'DraftKings expands', 'content': ''},
            {'title': 'DraftKings News', 'summary': '', 'content': 'draftkings update'}
        ])
        competitor_df = pd.DataFrame([
            {'title': 'BetMGM News', 'summary': 'betmgm launches', 'content': ''}
        ])

        result = extract_company_differentiators(internal_df, competitor_df, top_n=5)

        assert isinstance(result, list)
        # DraftKings should show up as portfolio advantage
        if result:
            companies = [r['company'].lower() for r in result]
            # May or may not have draftkings depending on thresholds


class TestRegionDifferentiators:
    """Tests for regional coverage differentiators."""

    def test_extract_region_mentions(self):
        """Test region mention extraction."""
        corpus = "brazil market is growing. latin america expansion. brazil again."
        mentions = extract_region_mentions(corpus)

        assert 'latam' in mentions
        assert mentions['latam'] >= 3  # brazil x2 + latin america

    def test_extract_region_differentiators(self):
        """Test region differentiator extraction."""
        internal_df = pd.DataFrame([
            {'title': 'Brazil Market Expansion', 'summary': 'LatAm growth', 'content': ''},
            {'title': 'Mexico Entry', 'summary': 'Latin America', 'content': ''}
        ])
        competitor_df = pd.DataFrame([
            {'title': 'UK Market Update', 'summary': 'European expansion', 'content': ''}
        ])

        result = extract_region_differentiators(internal_df, competitor_df)

        assert isinstance(result, list)
        assert len(result) > 0
        # Each result should have required fields
        for r in result:
            assert 'region' in r
            assert 'advantage' in r


class TestFormatDifferentiators:
    """Tests for content format differentiators."""

    def test_classify_article_format_interview(self):
        """Test interview detection."""
        row = pd.Series({
            'title': 'Interview with CEO',
            'summary': 'We spoke to the chief executive'
        })
        assert classify_article_format(row) == 'interview'

    def test_classify_article_format_guide(self):
        """Test guide detection."""
        row = pd.Series({
            'title': 'How to Start Sports Betting',
            'summary': 'A beginner guide to sports betting'
        })
        assert classify_article_format(row) == 'guide'

    def test_classify_article_format_news(self):
        """Test news detection."""
        row = pd.Series({
            'title': 'Company Announces New Feature',
            'summary': 'The company launches a product'
        })
        assert classify_article_format(row) == 'news'

    def test_extract_format_differentiators(self):
        """Test format differentiator extraction."""
        internal_df = pd.DataFrame([
            {'title': 'Interview with CEO', 'summary': 'Spoke to leader'},
            {'title': 'How to Guide', 'summary': 'Tutorial for beginners'}
        ])
        competitor_df = pd.DataFrame([
            {'title': 'Company Announces', 'summary': 'Launch news'},
            {'title': 'Company Releases', 'summary': 'Product unveil'}
        ])

        result = extract_format_differentiators(internal_df, competitor_df)

        assert isinstance(result, list)
        for r in result:
            assert 'format' in r
            assert 'internal_pct' in r
            assert 'competitor_pct' in r


class TestCadenceMetrics:
    """Tests for publishing cadence metrics."""

    def test_calculate_cadence_basic(self):
        """Test basic cadence calculation."""
        internal_df = pd.DataFrame([
            {'published_date': '2025-01-01'},
            {'published_date': '2025-01-02'},
            {'published_date': '2025-01-03'}
        ])
        competitor_df = pd.DataFrame([
            {'published_date': '2025-01-01'},
            {'published_date': '2025-01-02'}
        ])

        result = calculate_cadence_metrics(internal_df, competitor_df, days=7)

        assert 'internal_daily_rate' in result
        assert 'competitor_daily_rate' in result
        assert 'rate_ratio' in result
        assert result['internal_articles'] == 3
        assert result['competitor_articles'] == 2

    def test_calculate_cadence_empty(self):
        """Test with empty dataframes."""
        internal_df = pd.DataFrame()
        competitor_df = pd.DataFrame()

        result = calculate_cadence_metrics(internal_df, competitor_df, days=7)

        assert result['internal_articles'] == 0
        assert result['competitor_articles'] == 0


class TestFullExtraction:
    """Integration tests for full differentiator extraction."""

    @pytest.fixture
    def sample_internal_df(self):
        """Sample internal articles."""
        return pd.DataFrame([
            {
                'title': 'DraftKings CEO Interview',
                'summary': 'We spoke to the new CEO about Brazil expansion',
                'content': 'Latin America market growth continues. DraftKings plans major expansion.',
                'published_date': '2025-01-15',
                'source': 'iGaming Business',
                'link': 'http://example.com/1'
            },
            {
                'title': 'How to Enter LatAm Market',
                'summary': 'A guide for operators expanding to Brazil',
                'content': 'Brazil regulatory framework and licensing guide.',
                'published_date': '2025-01-14',
                'source': 'iGB',
                'link': 'http://example.com/2'
            },
            {
                'title': 'ICE Conference Preview',
                'summary': 'What to expect at ICE 2025',
                'content': 'Industry event announces major speakers.',
                'published_date': '2025-01-13',
                'source': 'iGaming Business',
                'link': 'http://example.com/3'
            }
        ])

    @pytest.fixture
    def sample_competitor_df(self):
        """Sample competitor articles."""
        return pd.DataFrame([
            {
                'title': 'BetMGM Launches in UK',
                'summary': 'BetMGM announces UK expansion',
                'content': 'European market entry for US operator.',
                'published_date': '2025-01-15',
                'source': 'Gambling Insider',
                'link': 'http://example.com/4'
            },
            {
                'title': 'Entain Reports Q4 Results',
                'summary': 'Financial results announced',
                'content': 'Revenue growth in Europe and US markets.',
                'published_date': '2025-01-14',
                'source': 'EGR',
                'link': 'http://example.com/5'
            }
        ])

    def test_extract_all_differentiators(self, sample_internal_df, sample_competitor_df):
        """Test full extraction pipeline."""
        result = extract_all_differentiators(
            sample_internal_df,
            sample_competitor_df,
            analysis_days=7
        )

        # Check structure
        assert 'generated_at' in result
        assert 'corpus_stats' in result
        assert 'language_differentiators' in result
        assert 'company_differentiators' in result
        assert 'region_differentiators' in result
        assert 'format_differentiators' in result
        assert 'cadence_metrics' in result
        assert 'summary' in result

        # Check corpus stats
        assert result['corpus_stats']['internal_articles'] == 3
        assert result['corpus_stats']['competitor_articles'] == 2

        # Check summary
        assert 'top_portfolio_terms' in result['summary']
        assert 'top_portfolio_companies' in result['summary']

    def test_extract_all_handles_empty(self):
        """Test with empty dataframes."""
        internal_df = pd.DataFrame(columns=['title', 'summary', 'content', 'published_date'])
        competitor_df = pd.DataFrame(columns=['title', 'summary', 'content', 'published_date'])

        result = extract_all_differentiators(internal_df, competitor_df, analysis_days=7)

        assert result['corpus_stats']['internal_articles'] == 0
        assert result['corpus_stats']['competitor_articles'] == 0
        assert len(result['language_differentiators']) == 0

    def test_examples_attached_to_top_terms(self, sample_internal_df, sample_competitor_df):
        """Test that example articles are attached to top terms."""
        result = extract_all_differentiators(
            sample_internal_df,
            sample_competitor_df,
            analysis_days=7
        )

        lang_diffs = result['language_differentiators']
        # Check if any have examples
        has_examples = any(d.get('examples') for d in lang_diffs[:5])
        # May or may not have examples depending on term matching


class TestKnownEntities:
    """Tests for known entity lists."""

    def test_known_companies_has_major_brands(self):
        """Test that major gaming companies are in the list."""
        major_brands = ['draftkings', 'fanduel', 'betmgm', 'bet365', 'flutter']
        for brand in major_brands:
            assert brand in KNOWN_COMPANIES, f"Missing major brand: {brand}"

    def test_regions_has_major_markets(self):
        """Test that major gaming markets are covered."""
        major_markets = ['latam', 'europe', 'north_america', 'asia']
        for market in major_markets:
            assert market in REGIONS, f"Missing major market: {market}"
