import base64
import io
import socket
import threading
import PIL.Image
import requests

from typing import Literal

# (connect, read) timeouts in seconds for out-of-browser goal image downloads
IMAGE_DOWNLOAD_TIMEOUT = (10, 60)
# wall-clock limit in seconds for the whole download (the read timeout only bounds idle gaps)
IMAGE_DOWNLOAD_DEADLINE = 120


def _download_image_content(image_url: str, state: dict) -> None:
    try:
        with requests.get(image_url, stream=True, timeout=IMAGE_DOWNLOAD_TIMEOUT) as response:
            state["response"] = response
            if response.status_code != 200:
                raise ValueError(
                    f"Could not download image from url {image_url} (status code {response.status_code})"
                )
            content = io.BytesIO()
            for chunk in response.iter_content(chunk_size=8 * 1024):
                if state["cancelled"].is_set():
                    return
                content.write(chunk)
            state["content"] = content.getvalue()
    except BaseException as e:
        state["error"] = e


def _abort_download(response) -> None:
    # Response.close() would block on the reader lock held by the worker, so shut the socket instead
    raw = getattr(response, "raw", None)
    connection_sock = getattr(getattr(raw, "_connection", None), "sock", None)
    # http.client drops connection.sock for non keep-alive responses; the body reader still holds it
    body_reader = getattr(getattr(raw, "_fp", None), "fp", None)
    reader_sock = getattr(getattr(body_reader, "raw", None), "_sock", None)
    for sock in (connection_sock, reader_sock):
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def image_url_to_pil_image(image_url: str) -> PIL.Image:
    if not image_url.startswith("http"):
        raise ValueError(f"Unexpected image URL: {image_url}")
    state = {"cancelled": threading.Event()}
    worker = threading.Thread(target=_download_image_content, args=(image_url, state), daemon=True)
    worker.start()
    worker.join(IMAGE_DOWNLOAD_DEADLINE)
    if worker.is_alive():
        state["cancelled"].set()
        _abort_download(state.get("response"))
        raise requests.exceptions.Timeout(
            f"Could not download image from url {image_url} within {IMAGE_DOWNLOAD_DEADLINE} seconds"
        )
    if "error" in state:
        raise state["error"]
    img = PIL.Image.open(io.BytesIO(state["content"]))
    return img


def data_uri_to_pil_image(data_uri: str) -> PIL.Image:
    if data_uri.startswith("data:image/png;base64,"):
        image_data = base64.b64decode(data_uri.removeprefix("data:image/png;base64,"))
    elif data_uri.startswith("data:image/jpeg;base64,"):
        image_data = base64.b64decode(data_uri.removeprefix("data:image/jpeg;base64,"))
    else:
        raise ValueError(f"Unexpected image encoding: {data_uri}")
    img = PIL.Image.open(io.BytesIO(image_data))
    return img


def pil_image_to_data_uri(image: PIL.Image, format: Literal["png", "jpeg"] = "png") -> str:
    assert format in ("png", "jpeg")
    with io.BytesIO() as image_buffer:
        image.save(image_buffer, format=format.upper())
        byte_data = image_buffer.getvalue()
    image_b64 = base64.b64encode(byte_data).decode("utf-8")
    image_b64 = f"data:image/{format};base64," + image_b64
    return image_b64
