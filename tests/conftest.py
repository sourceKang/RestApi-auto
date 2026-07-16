def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "methodology: offline PQA methodology coverage and gap-accountability checks",
    )
