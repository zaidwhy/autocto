from autocto.architectural_debt import analyze_repo
from autocto.imports import fan_in_from_graph, resolve_imports


def test_same_stem_in_two_packages_resolves_to_the_one_named():
    graph = resolve_imports(
        {
            "a/util.py": "",
            "b/util.py": "",
            "main.py": "from a.util import helper\n",
        }
    )
    assert graph["main.py"] == {"a/util.py"}


def test_python_import_statement_and_package_init():
    graph = resolve_imports(
        {
            "pkg/__init__.py": "",
            "pkg/core.py": "",
            "app.py": "import pkg.core\nimport pkg\n",
        }
    )
    assert graph["app.py"] == {"pkg/core.py", "pkg/__init__.py"}


def test_from_package_import_submodule_links_the_submodule_file():
    graph = resolve_imports(
        {
            "pkg/__init__.py": "",
            "pkg/sub.py": "",
            "app.py": "from pkg import sub\n",
        }
    )
    assert graph["app.py"] == {"pkg/__init__.py", "pkg/sub.py"}


def test_relative_imports():
    graph = resolve_imports(
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from . import b\nfrom .c import thing\nfrom ..top import x\n",
            "pkg/b.py": "",
            "pkg/c.py": "",
            "top.py": "",
        }
    )
    # `..top` from pkg/a.py leaves the package to the repo root, where top.py lives.
    assert graph["pkg/a.py"] == {"pkg/__init__.py", "pkg/b.py", "pkg/c.py", "top.py"}


def test_src_layout_resolves_through_the_package_root():
    graph = resolve_imports(
        {
            "src/mylib/__init__.py": "",
            "src/mylib/x.py": "from mylib.y import z\n",
            "src/mylib/y.py": "",
            "tests/test_x.py": "from mylib.x import f\n",
        }
    )
    assert graph["src/mylib/x.py"] == {"src/mylib/y.py"}
    assert graph["tests/test_x.py"] == {"src/mylib/x.py"}


def test_external_modules_and_non_statements_give_no_edge():
    graph = resolve_imports(
        {
            "util.py": "",
            "a.py": 'import os\nimport requests\n"""import util"""\n# import util\n',
        }
    )
    assert graph["a.py"] == set()


def test_unparseable_python_file_contributes_no_edges_but_stays_a_key():
    graph = resolve_imports({"util.py": "", "broken.py": "def (:\nimport util\n"})
    assert graph["broken.py"] == set()


def test_self_import_is_not_an_edge():
    assert resolve_imports({"pkg/__init__.py": "", "pkg/a.py": "import pkg.a\n"})["pkg/a.py"] == set()


def test_js_relative_specifiers_extensions_and_index():
    graph = resolve_imports(
        {
            "web/app.ts": (
                "import a from './a';\n"
                "import b from './b.js';\n"
                "import c from './lib';\n"
                "import d from '../shared/d';\n"
                "import React from 'react';\n"
            ),
            "web/a.tsx": "",
            "web/b.ts": "",
            "web/lib/index.ts": "",
            "shared/d.js": "",
        }
    )
    assert graph["web/app.ts"] == {"web/a.tsx", "web/b.ts", "web/lib/index.ts", "shared/d.js"}


def test_js_require_reexport_and_dynamic_import():
    graph = resolve_imports(
        {
            "i.js": "const a = require('./a');\nexport { x } from './b';\nconst c = () => import('./c');\n",
            "a.js": "",
            "b.js": "",
            "c.js": "",
        }
    )
    assert graph["i.js"] == {"a.js", "b.js", "c.js"}


def test_js_specifier_leaving_the_repo_is_external():
    assert resolve_imports({"a.js": "import x from '../../outside';\n"})["a.js"] == set()


def test_fan_in_from_graph_counts_distinct_importers():
    graph = {"a.py": {"c.py"}, "b.py": {"c.py", "a.py"}, "c.py": set()}
    assert fan_in_from_graph(graph) == {"a.py": 1, "b.py": 0, "c.py": 2}


def test_analyze_repo_no_longer_invents_a_cycle_from_a_shared_stem(tmp_path):
    # With stem matching, x/util.py importing `a.util` also linked y/util.py, and
    # y/util.py importing `x.util` linked x/util.py: a false two-file cycle.
    for d in ("a", "x", "y"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "a" / "util.py").write_text("", encoding="utf-8")
    (tmp_path / "x" / "util.py").write_text("from a.util import f\n", encoding="utf-8")
    (tmp_path / "y" / "util.py").write_text("from x.util import g\n", encoding="utf-8")

    report = analyze_repo(tmp_path)

    assert report.cycles == []
