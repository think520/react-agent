from scripts.check_test_doubles import find_violations


def test_new_test_files_do_not_add_provider_doubles():
    assert find_violations() == []
