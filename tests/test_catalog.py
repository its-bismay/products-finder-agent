"""
tests/test_catalog.py
Automated tests for SQLite catalog loading, mapping, and deterministic filtering.
"""
import sqlite3
import pytest

from shopsense.catalog.loader import (
    _get_connection,
    get_available_columns,
    get_catalog_stats,
    get_distinct_categories,
    get_product_by_id,
    get_products_by_ids,
    load_all_products,
    verify_product_ids,
)
from shopsense.catalog.search import (
    apply_hard_filters,
    get_hard_filtered_ids,
    search_products,
)
from shopsense.schemas import Product, ShoppingIntent


def test_database_loads_and_has_products():
    """Verify the SQLite database connects and contains products."""
    with _get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
    assert count > 0, "Products table should contain records."


def test_schema_mapping_and_string_ids():
    """Verify product IDs are strings and core fields are mapped to Product schema."""
    products = load_all_products()
    assert len(products) > 0
    first = products[0]
    assert isinstance(first.product_id, str), "product_id must be a string."
    assert first.product_name, "product_name must not be empty."
    assert hasattr(first, "price"), "Product must have price attribute."
    assert hasattr(first, "width_cm"), "Product must have width_cm attribute."


def test_get_catalog_stats():
    """Verify get_catalog_stats returns valid database counts."""
    stats = get_catalog_stats()
    assert "total_products" in stats
    assert stats["total_products"] > 0
    assert "categories" in stats
    assert stats["categories"] > 0
    assert "with_images" in stats
    assert "with_price" in stats


def test_get_product_by_id():
    """Test single product retrieval by ID."""
    products = load_all_products()
    test_id = products[0].product_id
    retrieved = get_product_by_id(test_id)
    assert retrieved is not None
    assert retrieved.product_id == test_id
    assert retrieved.display_name == products[0].display_name


def test_get_products_by_ids_preserves_order():
    """Verify batch product retrieval preserves the input ID order."""
    products = load_all_products()
    if len(products) >= 3:
        ids = [products[2].product_id, products[0].product_id, products[1].product_id]
        retrieved = get_products_by_ids(ids)
        retrieved_ids = [p.product_id for p in retrieved]
        assert retrieved_ids == ids


def test_verify_product_ids():
    """Verify that existing IDs are confirmed and invalid ones filtered out."""
    products = load_all_products()
    valid_id = products[0].product_id
    fake_id = "non_existent_fake_id_99999"
    verified = verify_product_ids([valid_id, fake_id])
    assert valid_id in verified
    assert fake_id not in verified


def test_price_filtering():
    """Test price filtering with ShoppingIntent."""
    intent = ShoppingIntent(
        is_shopping_request=True,
        maximum_price=500.0,
    )
    products, _ = search_products(intent, use_semantic=False)
    for p in products:
        if p.price is not None:
            assert p.price <= 500.0, f"Product {p.product_id} price {p.price} exceeds max price 500"


def test_category_filtering():
    """Test category filtering with ShoppingIntent."""
    categories = get_distinct_categories()
    assert len(categories) > 0
    target_category = categories[0]

    intent = ShoppingIntent(
        is_shopping_request=True,
        category=target_category,
    )
    products, _ = search_products(intent, use_semantic=False)
    assert len(products) > 0
    for p in products:
        matches_cat = (
            (p.category_2 and target_category.lower() in p.category_2.lower())
            or (p.category_3 and target_category.lower() in p.category_3.lower())
        )
        assert matches_cat, f"Product {p.product_id} did not match category {target_category}"


def test_dimension_filtering():
    """Test dimension filtering (width and height constraints)."""
    intent = ShoppingIntent(
        is_shopping_request=True,
        maximum_width_cm=50.0,
        maximum_height_cm=60.0,
        dimensions_are_approximate=False,
    )
    ids = get_hard_filtered_ids(intent)
    products = get_products_by_ids(ids)
    for p in products:
        if p.width_cm is not None:
            assert p.width_cm <= 50.0
        if p.height_cm is not None:
            assert p.height_cm <= 60.0


def test_empty_results_honesty():
    """Test that queries with impossible criteria return empty results honestly."""
    intent = ShoppingIntent(
        is_shopping_request=True,
        maximum_price=1.0,  # Below minimum price in catalog (39 INR)
    )
    products, _ = search_products(intent, use_semantic=False)
    assert len(products) == 0, "No products should be returned below 1 INR."


def test_sql_queries_are_parameterized():
    """Ensure hard filters produce parameterized tuples, not string interpolations."""
    intent = ShoppingIntent(
        is_shopping_request=True,
        category="Vases",
        maximum_price=1000.0,
    )
    where_sql, params = apply_hard_filters(intent)
    assert "?" in where_sql
    assert 1000.0 in params
    assert "%Vases%" in params
