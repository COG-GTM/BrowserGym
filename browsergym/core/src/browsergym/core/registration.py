from collections.abc import Callable
from functools import partial
from typing import Any

import gymnasium as gym

from .env import BrowserEnv
from .task import AbstractBrowserTask


class frozen_partial:
    """
    Freeze some keyword arguments of a function.

    """

    def __init__(self, func: Callable[..., Any], **frozen_kwargs: Any) -> None:
        self.func = func
        self.frozen_kwargs = frozen_kwargs

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # check overlap between kwargs and frozen_kwargs
        clashing_kwargs = set(self.frozen_kwargs) & set(kwargs)  # key set intersection
        if clashing_kwargs:
            raise ValueError(f"Illegal attempt to override frozen parameters {clashing_kwargs}.")
        # merge the two dicts
        kwargs = kwargs | self.frozen_kwargs

        return self.func(*args, **kwargs)


def register_task(
    id: str,
    task_class: type[AbstractBrowserTask],
    task_kwargs: dict[str, Any] = {},
    default_task_kwargs: dict[str, Any] = {},
    nondeterministic: bool = True,
    *args: Any,
    **kwargs: Any,
) -> None:
    """
    Registers a browser task as a gym environment with its unique id.

    Args:
        id: the id of the task to register (will be prepended by "browsergym/").
        task_class: the task class to register.
        task_kwargs: frozen task arguments (can not be overloaded at environment creation time).
        task_kwargs_default: default task arguments (can be overloaded at environment creation time).
        nondeterministic: whether the task cannot be guaranteed deterministic transitions.
        *args: additional sequential arguments for either the gym or the browsergym environment.
        *kwargs: additional keyword arguments for either the gym or the browsergym environment.
    """
    if task_kwargs and default_task_kwargs:
        # check overlap between frozen and default task_kwargs
        clashing_kwargs = set(task_kwargs) & set(default_task_kwargs)  # key set intersection
        if clashing_kwargs:
            raise ValueError(
                f"Illegal attempt to register Browsergym environment {id} with both frozen and default values for task parameters {clashing_kwargs}."
            )

    task_entrypoint: Callable[..., AbstractBrowserTask] = task_class

    # freeze task_kwargs (cannot be overriden at environment creation)
    task_entrypoint = frozen_partial(task_class, **task_kwargs)

    # pre-set default_task_kwargs (can be overriden at environment creation)
    task_entrypoint = partial(task_entrypoint, **default_task_kwargs)

    gym.register(
        id=f"browsergym/{id}",
        entry_point=lambda *env_args, **env_kwargs: BrowserEnv(
            task_entrypoint, *env_args, **env_kwargs
        ),
        nondeterministic=nondeterministic,
        *args,
        **kwargs,
    )
