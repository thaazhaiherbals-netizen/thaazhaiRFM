"""Run only against a disposable PostgreSQL database named *_check."""

import os

import pytest
from sqlalchemy import text

from apps.api.config import get_settings
from apps.api.db import get_engine
from db.migrate import run


@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_TESTS") != "1", reason="Needs disposable PostgreSQL"
)
def test_migrations_and_seeds_are_repeatable():
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = get_engine()
    assert engine.url.database.endswith("_check"), "Refusing non-test database"
    run(seed=True)
    run(seed=True)
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM products")).scalar_one() == 22
        assert connection.execute(text("SELECT count(*) FROM product_variants")).scalar_one() == 25
        assert connection.execute(text("SELECT count(*) FROM product_aliases")).scalar_one() == 8
        assert connection.execute(text("SELECT count(*) FROM orders")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM schema_migrations")).scalar_one() == 16
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM product_aliases a JOIN product_variants v "
                    "ON v.id = a.variant_id WHERE a.product_id <> v.product_id"
                )
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename IN ('customers', 'orders', 'raw_order_ingestion') "
                    "AND rowsecurity"
                )
            ).scalar_one()
            == 3
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename IN ('meta_ad_accounts', 'meta_campaigns', "
                    "'meta_ad_sets', 'meta_ads', 'meta_insight_sync_runs', "
                    "'raw_meta_insights', 'meta_ad_daily_performance') "
                    "AND rowsecurity"
                )
            ).scalar_one()
            == 7
        )
        assert (
            connection.execute(
                text(
                    "SELECT rowsecurity FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename = 'customer_follow_ups'"
                )
            ).scalar_one()
            is True
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.views "
                    "WHERE table_schema = 'public' AND table_name = 'customer_analysis'"
                )
            ).scalar_one()
            == 1
        )
