from utils.pagination import get_page_choices, get_total_pages


def test_pagination():
    choices = list(range(25))

    # First page
    result = get_page_choices(choices, 0, 10)
    assert result == list(range(10))

    # Middle page
    result = get_page_choices(choices, 1, 10)
    assert result == list(range(10, 20))

    # Last page partial
    result = get_page_choices(choices, 2, 10)
    assert result == list(range(20, 25))


def test_pagination_edge_cases():
    # Empty choices
    choices = []
    result = get_page_choices(choices, 0, 10)
    assert result == []

    # Page beyond data
    choices = list(range(15))
    result = get_page_choices(choices, 5, 10)
    assert result == []

    # Single item
    choices = ["single"]
    result = get_page_choices(choices, 0, 10)
    assert result == ["single"]


def test_total_pages():
    # Exact pages
    choices = list(range(20))
    result = get_total_pages(choices, 10)
    assert result == 2

    # Partial last page
    choices = list(range(25))
    result = get_total_pages(choices, 10)
    assert result == 3

    # Empty choices
    choices = []
    result = get_total_pages(choices, 10)
    assert result == 0


def test_pagination_consistency():
    choices = list(range(23))
    per_page = 7
    total_pages = get_total_pages(choices, per_page)

    all_items = []
    for page in range(total_pages):
        page_items = get_page_choices(choices, page, per_page)
        all_items.extend(page_items)

    assert all_items == choices


def test_pagination_boundary_conditions():
    # Test negative page numbers - should return empty (negative slice start results in empty)
    choices = list(range(15))
    result = get_page_choices(choices, -1, 10)
    assert result == []

    # Test very large page numbers
    result = get_page_choices(choices, 999, 10)
    assert result == []

    # Test zero per_page (edge case)
    try:
        result = get_total_pages(choices, 0)
        assert False, "Should raise division by zero or similar error"
    except (ZeroDivisionError, ValueError):
        pass


def test_pagination_performance_edge_cases():
    # Large dataset pagination
    large_choices = list(range(10000))

    # First page should be fast
    result = get_page_choices(large_choices, 0, 10)
    assert result == list(range(10))
    assert len(result) == 10

    # Middle page should be fast
    result = get_page_choices(large_choices, 500, 10)
    assert result == list(range(5000, 5010))

    # Last page calculation
    total_pages = get_total_pages(large_choices, 10)
    assert total_pages == 1000

    # Very last page
    result = get_page_choices(large_choices, 999, 10)
    assert result == list(range(9990, 10000))


def test_pagination_different_per_page_sizes():
    choices = list(range(100))

    # Test with different page sizes
    for per_page in [1, 5, 7, 15, 25, 50, 99, 100, 101]:
        total_pages = get_total_pages(choices, per_page)

        # Verify all items are covered
        all_items = []
        for page in range(total_pages):
            page_items = get_page_choices(choices, page, per_page)
            all_items.extend(page_items)

        assert all_items == choices


def test_pagination_single_item_edge_cases():
    # Single item, various page sizes
    choices = ["single_item"]

    assert get_total_pages(choices, 1) == 1
    assert get_total_pages(choices, 10) == 1
    assert get_total_pages(choices, 100) == 1

    assert get_page_choices(choices, 0, 1) == ["single_item"]
    assert get_page_choices(choices, 0, 10) == ["single_item"]
    assert get_page_choices(choices, 1, 10) == []


def test_pagination_exact_multiples():
    # Test when choices exactly match page boundaries
    choices = list(range(20))

    assert get_total_pages(choices, 10) == 2

    # First page
    result = get_page_choices(choices, 0, 10)
    assert result == list(range(10))

    # Second page
    result = get_page_choices(choices, 1, 10)
    assert result == list(range(10, 20))

    # Third page (empty)
    result = get_page_choices(choices, 2, 10)
    assert result == []


def test_pagination_off_by_one_scenarios():
    # Common off-by-one error scenarios

    # 21 items (2 full pages + 1 item)
    choices = list(range(21))
    assert get_total_pages(choices, 10) == 3

    # Last page should have 1 item
    result = get_page_choices(choices, 2, 10)
    assert result == [20]
    assert len(result) == 1

    # 19 items (1 full page + 9 items)
    choices = list(range(19))
    assert get_total_pages(choices, 10) == 2

    # Last page should have 9 items
    result = get_page_choices(choices, 1, 10)
    assert result == list(range(10, 19))
    assert len(result) == 9
