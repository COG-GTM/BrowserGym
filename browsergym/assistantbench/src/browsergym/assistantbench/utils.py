import contextlib
import json
import logging
import os
import pathlib
import stat
import time
import uuid

if os.name == "nt":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)

LOCK_MAX_WAIT = 10  # seconds a writer waits for the lock before giving up
LOCK_POLL_INTERVAL = 0.1  # seconds


def _try_lock(fd: int) -> bool:
    try:
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    if os.name == "nt":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def _file_lock(lock_file_path: pathlib.Path):
    """
    Exclusive inter-process lock backed by an OS advisory lock (flock / msvcrt.locking).

    The kernel drops the lock when the holder closes the file or dies, so a crash or an
    exception can never leave a stale lock behind. The lock file itself is intentionally
    never deleted: unlinking it would let two processes lock two different inodes.
    """
    try:
        # read-write: NFS emulates flock with POSIX locks, which need a writable fd
        fd = os.open(lock_file_path, os.O_RDWR | os.O_CREAT, 0o666)
    except PermissionError:
        # lock file created by another user without write access for us; local flock
        # works on a read-only fd
        fd = os.open(lock_file_path, os.O_RDONLY)
    try:
        start_time = time.time()
        logged_wait = False
        while not _try_lock(fd):
            seconds_waited = time.time() - start_time
            if seconds_waited >= LOCK_MAX_WAIT:
                raise RuntimeError(
                    f"Lock file could not be acquired after {seconds_waited} seconds ({lock_file_path})"
                )
            if not logged_wait:
                logger.info(f"Waiting for lock file to be released: {lock_file_path}")
                logged_wait = True
            time.sleep(LOCK_POLL_INTERVAL)
        logger.info(f"Lock file acquired: {lock_file_path}")
        try:
            yield
        finally:
            _unlock(fd)
            logger.info(f"Lock file released: {lock_file_path}")
    finally:
        os.close(fd)


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
    tmp_path = os.path.join(directory, f".{os.path.basename(file_path)}.{uuid.uuid4().hex}.tmp")
    # same default mode as open(file_path, "w") (0o666 minus umask)
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "w") as f:
            if os.path.exists(file_path):
                os.chmod(tmp_path, stat.S_IMODE(os.stat(file_path).st_mode))
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
    """
    lock_file_path = pathlib.Path(file_path).with_suffix(".lock")
    with _file_lock(lock_file_path):
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
