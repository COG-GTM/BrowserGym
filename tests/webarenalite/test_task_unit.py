import importlib.resources
import json
import sys
import types
from unittest import mock

import gymnasium as gym
import pytest

import browsergym.webarenalite
from browsergym.webarenalite import config as lite_config
from browsergym.webarenalite.task import WebArenaLiteTask

DUMMY_URLS = {
    "SHOPPING": "http://shopping.test:7770",
    "SHOPPING_ADMIN": "http://shopping-admin.test:7780/admin",
    "REDDIT": "http://reddit.test:9999",
    "GITLAB": "http://gitlab.test:8023",
    "WIKIPEDIA": "http://wikipedia.test:8888",
    "MAP": "http://map.test:3000",
    "HOMEPAGE": "http://homepage.test:4399",
}

PLACEHOLDERS = {
    "__GITLAB__": "gitlab",
    "__REDDIT__": "reddit",
    "__SHOPPING__": "shopping",
    "__SHOPPING_ADMIN__": "shopping_admin",
    "__WIKIPEDIA__": "wikipedia",
    "__MAP__": "map",
}


def _load_lite_configs():
    raw = (
        importlib.resources.files("browsergym.webarenalite")
        .joinpath("test_webarena_lite.raw.json")
        .read_text()
    )
    return json.loads(raw)


def _load_full_webarena_configs():
    import webarena

    return json.loads(importlib.resources.files(webarena).joinpath("test.raw.json").read_text())


LITE_CONFIGS = _load_lite_configs()
LITE_BY_OLD_ID = {conf["old_task_id"]: conf for conf in LITE_CONFIGS}
LITE_OLD_TASK_IDS = sorted(LITE_BY_OLD_ID)
LITE_TEMPLATE_IDS = sorted({conf["intent_template_id"] for conf in LITE_CONFIGS})
LITE_BY_NEW_ID = {conf["task_id"]: conf for conf in LITE_CONFIGS}

# old_task_ids that are also the (new) task_id of a *different* lite config: filtering on
# task_id instead of old_task_id would silently pick the wrong task for these.
COLLIDING_IDS = [
    i for i in LITE_OLD_TASK_IDS if i in LITE_BY_NEW_ID and LITE_BY_NEW_ID[i]["old_task_id"] != i
]

GYM_SAMPLE_IDS = [LITE_OLD_TASK_IDS[0], LITE_OLD_TASK_IDS[-1]] + COLLIDING_IDS[:3]


@pytest.fixture
def wa_env(monkeypatch):
    for key, url in DUMMY_URLS.items():
        monkeypatch.setenv(f"WA_{key}", url)
        # WebArenaInstance copies WA_<KEY> into <KEY>; register it so it gets restored
        monkeypatch.setenv(key, url)
    monkeypatch.setenv("OPENAI_API_KEY", "")


def _expected_config(old_task_id, urls):
    conf_str = json.dumps(LITE_BY_OLD_ID[old_task_id])
    for pattern, url_key in PLACEHOLDERS.items():
        conf_str = conf_str.replace(pattern, urls[url_key])
    return json.loads(conf_str)


def _assert_no_placeholders(conf):
    conf_str = json.dumps(conf)
    for pattern in PLACEHOLDERS:
        assert pattern not in conf_str, f"unsubstituted {pattern} in task {conf['task_id']}"


def test_lite_json_old_task_ids_are_unique():
    old_ids = [conf["old_task_id"] for conf in LITE_CONFIGS]
    assert len(old_ids) == len(set(old_ids))


def test_registered_task_ids_match_lite_json():
    assert len(lite_config.TASK_IDS) == len(set(lite_config.TASK_IDS))
    assert sorted(lite_config.TASK_IDS) == LITE_OLD_TASK_IDS
    assert browsergym.webarenalite.ALL_WEBARENA_TASK_IDS == [
        f"webarenalite.{task_id}" for task_id in lite_config.TASK_IDS
    ]
    for gym_id in browsergym.webarenalite.ALL_WEBARENA_TASK_IDS:
        assert f"browsergym/{gym_id}" in gym.registry


def test_colliding_ids_exist():
    # sanity check that the old_task_id vs task_id regression test below is meaningful
    assert COLLIDING_IDS


@pytest.mark.parametrize("task_id", LITE_OLD_TASK_IDS)
def test_every_old_task_id_resolves_to_exactly_one_config(wa_env, task_id):
    task = WebArenaLiteTask(seed=0, task_id=task_id)

    assert len(task.task_configs) == 1
    conf = task.task_configs[0]
    assert conf["old_task_id"] == task_id
    assert conf == _expected_config(task_id, task.webarena_instance.urls)
    _assert_no_placeholders(conf)


@pytest.mark.parametrize("task_id", COLLIDING_IDS[:5])
def test_task_id_filters_on_old_task_id_not_task_id(wa_env, task_id):
    task = WebArenaLiteTask(seed=0, task_id=task_id)

    assert [conf["task_id"] for conf in task.task_configs] == [LITE_BY_OLD_ID[task_id]["task_id"]]
    assert LITE_BY_NEW_ID[task_id]["task_id"] not in [conf["task_id"] for conf in task.task_configs]


def _first_task_starting_with(placeholder):
    for conf in LITE_CONFIGS:
        if conf["start_url"].startswith(placeholder):
            return conf["old_task_id"]
    return None


SITE_SAMPLE_IDS = {
    pattern: _first_task_starting_with(pattern)
    for pattern in PLACEHOLDERS
    if _first_task_starting_with(pattern) is not None
}


@pytest.mark.parametrize("placeholder", sorted(SITE_SAMPLE_IDS))
def test_start_url_substitution_per_site(wa_env, placeholder):
    task = WebArenaLiteTask(seed=0, task_id=SITE_SAMPLE_IDS[placeholder])
    url = task.webarena_instance.urls[PLACEHOLDERS[placeholder]]
    start_url = task.task_configs[0]["start_url"]

    assert url
    assert start_url.startswith(url)
    # the generic __SHOPPING__ pattern must not clobber __SHOPPING_ADMIN__
    assert "_ADMIN__" not in start_url
    assert "__" not in start_url.split("://", 1)[0]


@pytest.mark.parametrize("intent_template_id", LITE_TEMPLATE_IDS[:10])
def test_intent_template_id_selection(wa_env, intent_template_id):
    task = WebArenaLiteTask(seed=0, intent_template_id=intent_template_id)

    expected = sorted(
        conf["task_id"]
        for conf in LITE_CONFIGS
        if conf["intent_template_id"] == intent_template_id
    )
    assert expected
    assert sorted(conf["task_id"] for conf in task.task_configs) == expected
    for conf in task.task_configs:
        assert conf["intent_template_id"] == intent_template_id
        _assert_no_placeholders(conf)


def test_unknown_old_task_id_raises(wa_env):
    # valid WebArena task id that is not part of WebArena-Lite
    full_ids = {conf["task_id"] for conf in _load_full_webarena_configs()}
    task_id = min(full_ids - set(LITE_OLD_TASK_IDS))

    with pytest.raises(ValueError, match=f"old_task_id={task_id}"):
        WebArenaLiteTask(seed=0, task_id=task_id)


def test_task_id_outside_webarena_raises(wa_env):
    with pytest.raises(ValueError, match="task_id=99999"):
        WebArenaLiteTask(seed=0, task_id=99999)


def test_unknown_intent_template_id_raises(wa_env):
    # valid WebArena template id that is not part of WebArena-Lite
    full_template_ids = {conf["intent_template_id"] for conf in _load_full_webarena_configs()}
    intent_template_id = min(full_template_ids - set(LITE_TEMPLATE_IDS))

    with pytest.raises(ValueError, match=f"intent_template_id={intent_template_id}"):
        WebArenaLiteTask(seed=0, intent_template_id=intent_template_id)


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"task_id": LITE_OLD_TASK_IDS[0], "intent_template_id": LITE_TEMPLATE_IDS[0]}],
)
def test_requires_exactly_one_id(wa_env, kwargs):
    with pytest.raises(ValueError, match="One and only one"):
        WebArenaLiteTask(seed=0, **kwargs)


@pytest.mark.parametrize("task_id", GYM_SAMPLE_IDS)
def test_gym_id_maps_to_old_task_id(wa_env, task_id):
    env = gym.make(f"browsergym/webarenalite.{task_id}")
    try:
        unwrapped = env.unwrapped
        task = unwrapped.task_entrypoint(seed=0, **unwrapped.task_kwargs)
        assert isinstance(task, WebArenaLiteTask)
        assert [conf["old_task_id"] for conf in task.task_configs] == [task_id]
    finally:
        env.close()


def test_setup_uses_selected_config(wa_env, monkeypatch, tmp_path):
    # multi-page start_url, exercises the " |AND| " split
    task_id = next(conf["old_task_id"] for conf in LITE_CONFIGS if " |AND| " in conf["start_url"])
    task = WebArenaLiteTask(seed=0, task_id=task_id)
    expected = _expected_config(task_id, task.webarena_instance.urls)

    routed = []

    def fake_evaluator_router(config_file):
        routed.append(config_file)
        return "evaluator"

    fake_evaluators = types.ModuleType("browsergym.webarenalite.evaluators")
    fake_evaluators.evaluator_router = fake_evaluator_router
    monkeypatch.setitem(sys.modules, "browsergym.webarenalite.evaluators", fake_evaluators)
    monkeypatch.setattr(browsergym.webarenalite, "evaluators", fake_evaluators, raising=False)
    logins = []
    monkeypatch.setattr(task.webarena_instance, "ui_login", lambda site, page: logins.append(site))

    page = mock.MagicMock()
    goal, info = task.setup(page=page)

    assert task.config == expected
    assert goal == expected["intent"]
    assert info == {}
    assert task.evaluator == "evaluator"
    assert routed == [task.config_file]
    with open(task.config_file) as f:
        assert json.load(f) == expected
    assert logins == expected["sites"]
    page.context.set_geolocation.assert_called_once_with(expected["geolocation"])

    start_urls = expected["start_url"].split(" |AND| ")
    assert len(start_urls) > 1
    current = page
    for url in start_urls:
        current.goto.assert_called_once_with(url)
        current = current.context.new_page.return_value
    current.goto.assert_not_called()
