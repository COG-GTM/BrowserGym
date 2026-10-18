import functools
import threading

CAPTIONING_MODEL_NAME = "Salesforce/blip2-flan-t5-xl"

_load_lock = threading.Lock()


@functools.lru_cache(maxsize=None)
def _load_captioning_fn(device: str, dtype, model_name: str):
    from transformers.utils.logging import (
        disable_progress_bar,
        enable_progress_bar,
        is_progress_bar_enabled,
    )
    from visualwebarena.evaluation_harness.image_utils import get_captioning_fn

    hide_progress_bar = is_progress_bar_enabled()
    if hide_progress_bar:
        disable_progress_bar()
    try:
        return get_captioning_fn(device=device, dtype=dtype, model_name=model_name)
    finally:
        if hide_progress_bar:
            enable_progress_bar()


def get_shared_captioning_fn(device: str, dtype, model_name: str = CAPTIONING_MODEL_NAME):
    """
    Returns the process-wide captioning function for (device, dtype, model_name),
    loading the underlying model on first use only.
    """
    with _load_lock:
        return _load_captioning_fn(device, dtype, model_name)


def lazy_captioning_fn(device: str, dtype, model_name: str = CAPTIONING_MODEL_NAME):
    """
    Returns a captioning function that defers loading the (shared) model until it is
    first called, so episodes whose evaluators never caption an image skip the load.
    """

    def captioning_fn(*args, **kwargs):
        return get_shared_captioning_fn(device, dtype, model_name)(*args, **kwargs)

    return captioning_fn
