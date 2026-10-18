import json
import logging
import os
import pathlib
import socket
import tempfile
import time
import uuid

logger = logging.getLogger(__name__)

LOCK_MAX_WAIT = 10  # seconds a writer waits for the lock before giving up
LOCK_STALE_AFTER = 60  # seconds after which a lock is considered abandoned
LOCK_POLL_INTERVAL = 0.1  # seconds


def _read_lock(lock_file_path: pathlib.Path) -> str:
    with open(lock_file_path, "r") as f:
        return f.read()


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        # os.kill(pid, 0) sends CTRL_C_EVENT on Windows, rely on lock age instead
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _lock_is_stale(lock_file_path: pathlib.Path, content: str) -> bool:
    try:
        owner = json.loads(content)
    except ValueError:
        owner = None
    if (
        isinstance(owner, dict)
        and owner.get("host") == socket.gethostname()
        and isinstance(owner.get("pid"), int)
        and not _pid_alive(owner["pid"])
    ):
        return True
    age = time.time() - os.stat(lock_file_path).st_mtime
    return age >= LOCK_STALE_AFTER


def _break_stale_lock(lock_file_path: pathlib.Path, observed_content: str) -> None:
    # Atomically move the lock aside so concurrent waiters cannot both break it.
    tomb = lock_file_path.with_name(f"{lock_file_path.name}.stale-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        os.rename(lock_file_path, tomb)
    except FileNotFoundError:
        return
    try:
        if _read_lock(tomb) != observed_content:
            # the lock was re-acquired between our check and the rename, hand it back
            try:
                os.link(tomb, lock_file_path)
            except OSError:
                logger.warning(f"Could not restore lock file {lock_file_path}")
        else:
            logger.warning(f"Removed stale lock file {lock_file_path} ({observed_content!r})")
    finally:
        os.remove(tomb)


def _acquire_lock(lock_file_path: pathlib.Path) -> str:
    token = json.dumps(
        {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created": time.time(),
            "nonce": uuid.uuid4().hex,
        }
    )
    start_time = time.time()
    logged_wait = False
    while True:
        try:
            fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                content = _read_lock(lock_file_path)
                if _lock_is_stale(lock_file_path, content):
                    _break_stale_lock(lock_file_path, content)
                    continue
            except FileNotFoundError:
                continue  # released in the meantime, retry immediately

            seconds_waited = time.time() - start_time
            if seconds_waited >= LOCK_MAX_WAIT:
                raise RuntimeError(
                    f"Lock file could not be acquired after {seconds_waited} seconds ({lock_file_path})"
                )
            if not logged_wait:
                logger.info(f"Waiting for lock file to be released: {lock_file_path}")
                logged_wait = True
            time.sleep(LOCK_POLL_INTERVAL)
            continue

        try:
            with os.fdopen(fd, "w") as f:
                f.write(token)
        except BaseException:
            os.remove(lock_file_path)
            raise
        logger.info(f"Lock file acquired: {lock_file_path}")
        return token


def _release_lock(lock_file_path: pathlib.Path, token: str) -> None:
    try:
        if _read_lock(lock_file_path) != token:
            logger.warning(f"Lock file {lock_file_path} is no longer owned by this process")
            return
        os.remove(lock_file_path)
    except FileNotFoundError:
        logger.warning(f"Lock file {lock_file_path} disappeared before release")
        return
    logger.info(f"Lock file released: {lock_file_path}")


def _load_jsonl(file_path: str) -> list:
    data = []
    if not os.path.exists(file_path):
        return data
    with open(file_path, "r") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue  # Skip empty lines
            try:
                data.append(json.loads(line))
            except ValueError as e:
                raise ValueError(f"Invalid JSON on line {line_no} of {file_path}: {e}") from e
    return data


def _write_jsonl_atomic(file_path: str, data: list) -> None:
    # Write to a temp file in the same directory, then atomically swap it in, so a crash
    # mid-write never leaves a truncated output file behind.
    directory = os.path.dirname(os.path.abspath(file_path))
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=f".{os.path.basename(file_path)}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            for entry in data:
                f.write(json.dumps(entry) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
        raise


def add_prediction_to_jsonl(
    file_path: str, task_id: str, prediction: object, override_if_exists: bool
) -> None:
    """
    Multiprocessing-safe file write.

    Raises ValueError if a prediction for task_id already exists and override_if_exists is False.
    The lock file is always released, and locks abandoned by dead processes are reclaimed.
    """
    lock_file_path = pathlib.Path(file_path).with_suffix(".lock")
    token = _acquire_lock(lock_file_path)
    try:
        data = _load_jsonl(file_path)

        existing_record = next(
            (entry for entry in data if isinstance(entry, dict) and entry.get("id") == task_id),
            None,
        )

        if not existing_record:
            data.append({"id": task_id, "answer": prediction})
        elif override_if_exists:
            existing_record["answer"] = prediction
        else:
            raise ValueError(
                f"Prediction for task ID {repr(task_id)} already exists in file {file_path}."
            )

        _write_jsonl_atomic(file_path, data)
    finally:
        _release_lock(lock_file_path, token)
