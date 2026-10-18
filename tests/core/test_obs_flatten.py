from bs4 import BeautifulSoup

from browsergym.utils.obs import flatten_axtree_to_str, flatten_dom_to_str


def _ax_node(node_id, role, name=None, child_ids=(), **extra):
    node = {"nodeId": node_id, "role": {"value": role}, "childIds": list(child_ids)}
    if name is not None:
        node["name"] = {"value": name}
    node.update(extra)
    return node


def test_flatten_axtree_to_str_joins_lines_in_dfs_order():
    axtree = {
        "nodes": [
            _ax_node("1", "RootWebArea", "Page", ["2", "3", "missing", "1"], browsergym_id="a"),
            # skipped node: its children are printed at the parent's depth
            _ax_node("2", "generic", "", ["4", "5"]),
            _ax_node("3", "LineBreak", "\n"),
            _ax_node("4", "button", "Submit", ["6"], browsergym_id="b"),
            _ax_node("5", "link", "Home", browsergym_id="c"),
            # redundant static text is skipped, leaving an empty subtree
            _ax_node("6", "StaticText", "Submit"),
        ]
    }

    assert (
        flatten_axtree_to_str(axtree)
        == "[a] RootWebArea 'Page'\n\t[b] button 'Submit'\n\t[c] link 'Home'"
    )
    assert flatten_axtree_to_str(axtree, remove_redundant_static_text=False) == (
        "[a] RootWebArea 'Page'\n\t[b] button 'Submit'\n\t\tStaticText 'Submit'\n\t[c] link 'Home'"
    )


def test_flatten_axtree_to_str_only_skipped_nodes_is_empty():
    axtree = {"nodes": [_ax_node("1", "generic", "", ["2"]), _ax_node("2", "LineBreak", "x")]}

    assert flatten_axtree_to_str(axtree) == ""


def test_flatten_axtree_to_str_deep_tree():
    depth = 200
    nodes = [
        _ax_node(str(i), "group", f"g{i}", [str(i + 1)] if i + 1 < depth else [])
        for i in range(depth)
    ]

    expected = "\n".join("\t" * i + f"group 'g{i}'" for i in range(depth))
    assert flatten_axtree_to_str({"nodes": nodes}) == expected


def test_flatten_dom_to_str_keeps_order_with_iframes():
    strings = ["#document", "HTML", "BODY", "P", "#text", "hello", "IFRAME", "bid", "f1", "world"]
    s = {v: i for i, v in enumerate(strings)}

    def doc(node_types, names, values, parents, attributes, content_documents=()):
        return {
            "nodes": {
                "nodeType": node_types,
                "nodeName": [s[n] for n in names],
                "nodeValue": [s[v] if v is not None else -1 for v in values],
                "parentIndex": parents,
                "attributes": [[s[a] for a in attrs] for attrs in attributes],
                "contentDocumentIndex": {
                    "index": [idx for idx, _ in content_documents],
                    "value": [value for _, value in content_documents],
                },
            }
        }

    dom_snapshot = {
        "strings": strings,
        "documents": [
            doc(
                [9, 1, 1, 1, 3, 1],
                ["#document", "HTML", "BODY", "P", "#text", "IFRAME"],
                [None, None, None, None, "hello", None],
                [-1, 0, 1, 2, 3, 2],
                [[], [], [], [], [], ["bid", "f1"]],
                content_documents=[(5, 1)],
            ),
            doc(
                [9, 1, 1, 3],
                ["#document", "HTML", "BODY", "#text"],
                [None, None, None, "world"],
                [-1, 0, 1, 2],
                [[], [], [], []],
            ),
        ],
    }

    inner = BeautifulSoup("<html><body>world</body></html>", "lxml").prettify()
    expected = BeautifulSoup(
        f'<html><body><p>hello</p><iframe bid="f1">{inner}</iframe></body></html>', "lxml"
    ).prettify()
    assert flatten_dom_to_str(dom_snapshot) == expected
