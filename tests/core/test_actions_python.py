import pytest

from browsergym.core.action.python import PythonActionSet


ACTIONS_TO_TEST = [
    (
        """\
a = 0
""",
        """\
a = 0
""",
    ),
    (
        """\
```
a = 0
```
""",
        """\
a = 0
""",
    ),
    (
        """\
```python
a = 0
```
""",
        """\
a = 0
""",
    ),
    (
        """\
```python
a = 0
```
This is an explanation
```python
b = 3
```
More explanations
""",
        """\
a = 0

b = 3
""",
    ),
    (
        """\
Here is the code:
```python
a = 0
```
""",
        """\
a = 0
""",
    ),
    (
        """\

  ```python
a = 0
```
""",
        """\
a = 0
""",
    ),
    (
        """\
I will set a.
```
a = 0
```
Then b is unchanged.""",
        """\
a = 0
""",
    ),
    (
        """\
```python
a = 0
```""",
        """\
a = 0
""",
    ),
    (
        """\
Step one:
```python
a = 0
```
Step two:
```
b = 3
```
Done.
""",
        """\
a = 0

b = 3
""",
    ),
    (
        """\
send_message_to_user('''Example:
```python
page.get_by_role("button", name="Delete").click()
```
''')
""",
        """\
send_message_to_user('''Example:
```python
page.get_by_role("button", name="Delete").click()
```
''')
""",
    ),
]


@pytest.mark.parametrize("action,expected_code", ACTIONS_TO_TEST)
def test_action_cleaning(action, expected_code):
    action_set = PythonActionSet()
    code = action_set.to_python_code(action)

    assert code == expected_code
