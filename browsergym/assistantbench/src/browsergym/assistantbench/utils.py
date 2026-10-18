import json
import logging
import os
import pathlib
import shutil
import time
import uuid

logger = logging.getLogger(__name__)


def add_prediction_to_jsonl(
    file_path: str, task_id: str, prediction: object, override_if_exists: bool
) -> None:
    """
    Multiprocessing-safe file write.
    """
    # resolve symlinks, so that the target file is updated and aliases share the same lock
    file_path = os.path.realpath(file_path)
    lock_file_path = pathlib.Path(file_path).with_suffix(".lock")
    lock_max_wait = 10  # 10 seconds

    # Acquire lock (atomic file creation)
    start_time = time.time()
    while True:
        try:
            fd = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write("lock")
            break
        except FileExistsError:
            # give up if max wait time reached
            seconds_waited = time.time() - start_time
            if seconds_waited >= lock_max_wait:
                raise RuntimeError(
                    f"Lock file could not be acquired after {seconds_waited} seconds ({lock_file_path})"
                )
            # wait for lock release
            logger.info(f"Waiting for lock file to be released: {lock_file_path}")
            time.sleep(1)  # 1 sec

    logger.info(f"Lock file acquired: {lock_file_path}")

    try:
        # Load existing data, if any
        data = []
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                data.extend([json.loads(line) for line in f if line.strip()])  # Skip empty lines

        # Check if task_id already exists
        existing_record = next((entry for entry in data if entry["id"] == task_id), None)

        # Add or update the record
        if not existing_record:
            # Add new record
            data.append({"id": task_id, "answer": prediction})
        elif override_if_exists:
            # Update existing record
            existing_record["answer"] = prediction
        else:
            raise ValueError(
                f"Prediction for task ID {repr(task_id)} already exists in file {file_path}."
            )

        # Write data to a unique temporary file, then atomically replace the output file
        output_path = pathlib.Path(file_path)
        tmp_file_path = output_path.with_name(f".prediction-{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp_file_path, "x") as f:
                for entry in data:
                    f.write(json.dumps(entry) + "\n")
            if output_path.exists():
                shutil.copymode(output_path, tmp_file_path)
            os.replace(tmp_file_path, output_path)
        except BaseException:
            tmp_file_path.unlink(missing_ok=True)
            raise

    finally:
        # Release lock (remove file), even if an error occurred
        os.remove(lock_file_path)
        logger.info(f"Lock file released: {lock_file_path}")
