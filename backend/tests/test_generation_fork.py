import inspect


def test_generation_source_contains_kind_fork():
    """The stream_artifacts endpoint source must include kind-specific branches."""
    import backend.routers.artifacts as artifacts_module

    src = inspect.getsource(artifacts_module)
    assert (
        'kind == "template"' in src or "kind == 'template'" in src
    ), "template branch missing"
    assert (
        'kind == "hybrid"' in src or "kind == 'hybrid'" in src
    ), "hybrid branch missing"


def test_generation_source_imports_render_template():
    """Template rendering is delegated to template_service.render_template."""
    import backend.routers.artifacts as artifacts_module

    src = inspect.getsource(artifacts_module)
    assert "render_template" in src, "render_template import or call missing"


def test_generation_source_selects_kind_and_template_id():
    """The artifact_types SELECT must include kind + template_id."""
    import backend.routers.artifacts as artifacts_module

    src = inspect.getsource(artifacts_module)
    assert (
        "kind" in src and "template_id" in src
    ), "kind/template_id not pulled from artifact_types"
