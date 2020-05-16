"""Tests for Fava's main Flask app."""

from textwrap import dedent

import flask
import pytest
import werkzeug.urls
import werkzeug.routing

from fava.application import REPORTS, static_url

FILTER_COMBINATIONS = [
    {"account": "Assets"},
    {"filter": "any(account: Assets)"},
    {"time": "2015", "filter": "#tag1 payee:BayBook"},
]


@pytest.mark.parametrize(
    "report,filters",
    [
        (report, filters)
        for report in REPORTS
        for filters in FILTER_COMBINATIONS
    ],
)
def test_reports(app, test_client, report, filters):
    """The standard reports work without error (content isn't checked here)."""
    with app.test_request_context("/example-beancount-file/"):
        app.preprocess_request()
        url = flask.url_for("report", report_name=report, **filters)

    result = test_client.get(url)
    assert result.status_code == 200


@pytest.mark.parametrize("filters", FILTER_COMBINATIONS)
def test_account_page(app, test_client, filters):
    """Account page works without error."""
    for subreport in ["journal", "balances", "changes"]:
        with app.test_request_context("/example-beancount-file/"):
            app.preprocess_request()
            url = flask.url_for(
                "account",
                name="Assets:US:BofA:Checking",
                subreport=subreport,
                **filters
            )

        result = test_client.get(url)
        assert result.status_code == 200


@pytest.mark.parametrize(
    "url,return_code",
    [("/", 302), ("/asdfasdf/", 404), ("/asdfasdf/asdfasdf/", 404)],
)
def test_urls(test_client, url, return_code):
    """Some URLs return a 404."""
    result = test_client.get(url)
    assert result.status_code == return_code


@pytest.mark.parametrize(
    "referer,jump_link,expect",
    [
        ("/?foo=bar", "/jump?foo=baz", "/?foo=baz"),
        ("/?foo=bar", "/jump?baz=qux", "/?baz=qux&foo=bar"),
        ("/", "/jump?foo=bar&baz=qux", "/?baz=qux&foo=bar"),
        ("/", "/jump?baz=qux", "/?baz=qux"),
        ("/?foo=bar", "/jump?foo=", "/"),
        ("/?foo=bar", "/jump?foo=&foo=", "/?foo=&foo="),
        ("/", "/jump?foo=", "/"),
    ],
)
def test_jump_handler(app, test_client, referer, jump_link, expect):
    """Test /jump handler correctly redirect to the right location.

    Note: according to RFC 2616, Location: header should use an absolute URL.
    """
    result = test_client.get(jump_link, headers=[("Referer", referer)])
    with app.test_request_context():
        get_url = result.headers.get("Location", "")
        expect_url = werkzeug.urls.url_join("http://localhost/", expect)
        assert result.status_code == 302
        assert get_url == expect_url


def test_incognito(app, test_client):
    """Numbers get obfuscated in incognito mode."""
    app.config["INCOGNITO"] = True
    with app.test_request_context("/example-beancount-file/"):
        app.preprocess_request()
        url = flask.url_for("report", report_name="balance_sheet")

    result = test_client.get(url)
    assert result.status_code == 200
    assert "XXX" in result.get_data(True)

    app.config["INCOGNITO"] = False


def test_download_journal(app, test_client):
    """The currently filtered journal can be downloaded."""
    file_content = dedent(
        """\
        ;; -*- mode: org; mode: beancount; -*-

        option "title" "Example Beancount file - Journal Export"

        option "operating_currency" "USD"
        option "name_assets" "Assets"
        option "name_liabilities" "Liabilities"
        option "name_equity" "Equity"
        option "name_income" "Income"
        option "name_expenses" "Expenses"
        plugin "beancount.plugins.auto_accounts"

        2016-05-07 * "Jewel of Morroco" "Eating out alone"
          Liabilities:US:Chase:Slate                       -25.30 USD
          Expenses:Food:Restaurant                          25.30 USD

    """
    )

    with app.test_request_context("/example-beancount-file/"):
        app.preprocess_request()
        url = flask.url_for("download_journal", time="2016-05-07")
    result = test_client.get(url)
    assert result.get_data(True) == file_content
    assert result.headers["Content-Disposition"].startswith(
        'attachment; filename="journal_'
    )
    assert result.headers["Content-Type"] == "application/octet-stream"


def test_static_url(app) -> None:
    """Static URLs have the mtime appended."""
    filename = "app.js"
    with app.test_request_context():
        app.preprocess_request()
        url = static_url(filename)
    assert url.startswith("/static/" + filename)
    assert "?mtime=" in url


def test_load_extension_reports(app, test_client):
    """Extension can register reports."""
    with app.test_request_context("/extension-report-beancount-file/"):
        app.preprocess_request()
        assert flask.g.ledger.extensions.reports == [
            ("PortfolioList", "Portfolio List")
        ]

        url = flask.url_for("extension_report", report_name="PortfolioList")
        result = test_client.get(url)
        assert result.status_code == 200
