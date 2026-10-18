import sys
import types

import pytest

from browsergym.visualwebarena import captioning


@pytest.fixture
def fake_get_captioning_fn(monkeypatch):
    calls = []

    def get_captioning_fn(device, dtype, model_name):
        calls.append((device, dtype, model_name))

        def caption_images(images, prompt=None, max_new_tokens=32):
            return [f"{model_name}@{device}:{image}" for image in images]

        return caption_images

    image_utils = types.ModuleType("visualwebarena.evaluation_harness.image_utils")
    image_utils.get_captioning_fn = get_captioning_fn
    monkeypatch.setitem(sys.modules, "visualwebarena.evaluation_harness.image_utils", image_utils)

    progress_bar = {"enabled": True}
    hf_logging = types.ModuleType("transformers.utils.logging")
    hf_logging.is_progress_bar_enabled = lambda: progress_bar["enabled"]
    hf_logging.disable_progress_bar = lambda: progress_bar.update(enabled=False)
    hf_logging.enable_progress_bar = lambda: progress_bar.update(enabled=True)
    monkeypatch.setitem(sys.modules, "transformers.utils.logging", hf_logging)

    captioning._load_captioning_fn.cache_clear()
    yield calls
    captioning._load_captioning_fn.cache_clear()


def test_lazy_captioning_fn_does_not_load_model_until_called(fake_get_captioning_fn):
    captioning.lazy_captioning_fn(device="cpu", dtype="float32")

    assert fake_get_captioning_fn == []


def test_captioning_model_loaded_once_across_episodes(fake_get_captioning_fn):
    model_name = captioning.CAPTIONING_MODEL_NAME
    episode_fns = [captioning.lazy_captioning_fn(device="cpu", dtype="float32") for _ in range(5)]

    captions = [fn(["img.png"]) for fn in episode_fns]

    assert fake_get_captioning_fn == [("cpu", "float32", model_name)]
    assert captions == [[f"{model_name}@cpu:img.png"]] * 5


def test_captioning_cache_keyed_by_device_dtype_and_model(fake_get_captioning_fn):
    captioning.lazy_captioning_fn(device="cpu", dtype="float32")(["a"])
    captioning.lazy_captioning_fn(device="cuda", dtype="float16")(["a"])
    captioning.lazy_captioning_fn(device="cpu", dtype="float32", model_name="other/model")(["a"])
    captioning.lazy_captioning_fn(device="cpu", dtype="float32")(["a"])

    assert fake_get_captioning_fn == [
        ("cpu", "float32", captioning.CAPTIONING_MODEL_NAME),
        ("cuda", "float16", captioning.CAPTIONING_MODEL_NAME),
        ("cpu", "float32", "other/model"),
    ]


def test_progress_bar_restored_after_load(fake_get_captioning_fn):
    hf_logging = sys.modules["transformers.utils.logging"]

    captioning.get_shared_captioning_fn(device="cpu", dtype="float32")

    assert hf_logging.is_progress_bar_enabled()
